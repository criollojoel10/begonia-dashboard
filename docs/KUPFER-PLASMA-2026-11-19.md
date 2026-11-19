# Kupfer + kernel 7.1.0 + Plasma Mobile en begonia (instalación limpia 2026-11-19)

Reinstalación limpia del Xiaomi Redmi Note 8 Pro (`begonia`, MT6785 / Helio G90T) con:

| pieza | valor verificado en hardware |
|---|---|
| kernel | `7.1.0` (Kupfer vendor, clang 23, `#1 SMP PREEMPT`) |
| rootfs | Arch Linux ARM (`aarch64`), label `kupfer_root`, ext4 10 GiB |
| escritorio | Plasma Mobile **6.8.3** (`startplasmamobile`, KWin Wayland) |
| WiFi | `wlan_gen4m` + `wmt_drv` + `mtk-vendor-btif`, `wlan0` con escaneo real |
| GPU | panfrost sobre `13040000.gpu` (Mali-G76), KWin con `renderD128` abierto |
| pantalla | `card1-DSI-1` connected, 1080×2340 |

Todo lo que sigue está medido en el dispositivo tras el flasheo, no deducido.

## Artefactos

```
boot:    recovery-local/boot-7.1.0.img
         sha256 17b347242e639e656c8738210175d372747974b16373d7d240658edc042c39a1
         64 MiB exactos, header v2, page 2048, cmdline con earlymodules (lm36274_bl,
         lm363x-regulator, novatek-nvt-ts-spi, panel-novatek-nt36672a, ti-lmu)
rootfs:  rootfs-plasma.img.sparse
         sha256 72926379d8ba6ff569670db121e42880f68c81d0374ef1a68cc180f9ded1774d
         6,7 GiB sparse (10 GiB ext4, 6,0 GiB usados)
vbmeta:  vbmeta-flags2.img (avbtool --flags 2, verificación desactivada)
rollback boot 6.16: recovery-local/aboot-6.16.img
```

El boot de 7.1.0 es el que ya estaba validado en el arranque de octubre (`docs/50` de
stack-arm). No se regeneró: se reutiliza byte a byte para no reintroducir el bootloop de
las imágenes de bring-up.

## Qué se construyó y por qué

1. **Base**: tarball oficial Arch Linux ARM (`alarm-aarch64.tar.gz`).
2. **Kernel**: se extrae `linux-mt6785-7.1.0-1-aarch64.pkg.tar.xz` sobre el rootfs
   (`/boot` y `/usr/lib/modules/7.1.0` + `extramodules-7.1mt6785`) y `depmod 7.1.0`.
3. **Firmware WMT**: el paquete del kernel no trae los blobs del combo. Se instalan desde
   `mt6785-mainline/firmware` (commit `33aa9fe1db0079945fa272e42f04db732489319d`):
   `mediatek/{WMT_SOC.cfg,soc1_0_*,WIFI_RAM_CODE_soc1_0_2a_1.bin,wifi.cfg}.zst` y
   `novatek/nt36672a_begonia_csot.bin.zst`. Sin `WMT_SOC.cfg` + `soc1_0_*` la radio no
   enciende; sin el blob de novatek el táctil falla al subir firmware.
4. **Plasma Mobile**: `plasma-mobile plasma-workspace plasma-nano kwin sddm plasma-nm
   plasma-pa plasma-settings kscreen powerdevil bluedevil kclock kweather milou konsole
   plasma-keyboard qt6-wayland networkmanager wpa_supplicant wireless-regdb iw mesa
   pipewire wireplumber xdg-desktop-portal-kde`.
5. **Arranque de sesión**: getty autologin en `tty1` + `startplasmamobile`. Se descarta
   SDDM como gestor (se deja instalado pero deshabilitado): el patrón de autologin ya
   estaba probado en este mismo equipo con Phosh (`begonia-linux/docs/UI-PHOSH.md`).
   `startplasmamobile` crea sesión logind real (clase `user`, seat0), que es lo que KWin
   necesita para DRM.

## WiFi interno: el detalle que costaba el arranque

Los módulos solos **no** encienden la radio. El nodo `/dev/wmtWifi` espera el byte `1`
literal (`printf 1`, no `echo`), y sólo después baja el firmware y aparece `wlan0`.
Secuencia portada de `overlay/device/device-mt6785-xiaomi-begonia/mediatek-wifi.sh`
(repo `criollojoel10/begonia-kupfer-linux`):

```
modprobe wmt_drv
esperar /dev/wmtWifi
modprobe wlan_gen4m
printf 1 > /dev/wmtWifi
esperar /sys/class/net/wlan0
```

Queda en `/usr/local/sbin/begonia-wifi` + `begonia-conn.service`
(`Restart=on-failure`, `TimeoutStartSec=120`, antes de NetworkManager).

Evidencia tras reiniciar (sin tocar nada a mano):

```
[    7.628424] wlan_gen4m: ... wlan0 / wlan1 / p2p0 / ap0 creados
iw dev wlan0 scan -> 36 BSS
nmcli: CLARO_JOEL:wlan0 connected, IP4 192.168.100.76/24
```

`usb0` se deja **unmanaged** en NetworkManager (`99-unmanaged-usb0.conf`) para que no
compita con el gadget: la IP `172.16.42.1/24` y la ruta por defecto
(`via 172.16.42.2 metric 50`) las pone `luma-usb-gadget`. Así el SSH de rescate no
depende de NM y, cuando el USB se desconecta, la ruta de WiFi toma el relevo.

## GPU

```
[ 5.213359] panfrost 13040000.gpu: Features: L2:0x07130206 ...
[ 5.263588] [drm] Initialized panfrost 1.6.0 for 13040000.gpu on minor 0
/sys/class/drm/card1-DSI-1/status = connected
/proc/<kwin_wayland>/fd -> renderD128 (6 descriptores)
```

KWin corre sobre KMS/panfrost; no hay llvmpipe en la sesión.

## Red: compartir el WiFi del portátil por USB

El gadget ECM del teléfono crea `usb0` con `172.16.42.1/24`. En el portátil la interfaz
aparece como `enp4s0f3u2` (nombre por ruta USB, no `usb0`).

Perfil NetworkManager en el teléfono (`usb-share`): `172.16.42.1/24`, gateway
`172.16.42.2`, DNS `1.1.1.1,9.9.9.9`, `ipv6.method ignore`, autoconnect.

En el portátil, `begonia-usb-nat.service` (`scripts/host/`) activa
`net.ipv4.ip_forward` y añade:

```
iptables -I FORWARD 1 -i enp4s0f3u2 -j ACCEPT
iptables -I FORWARD 1 -o enp4s0f3u2 -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT
iptables -t nat -A POSTROUTING -s 172.16.42.0/24 -o wlan0 -j MASQUERADE
```

Con eso el teléfono sale a Internet por el WiFi del portátil (probado: `ping 1.1.1.1`,
`https://archlinuxarm.org` → 200).

## Actualizaciones

`pacman -Syu` en este kernel falla con:

```
error: restricting filesystem access failed because Landlock is not supported by the kernel!
```

El kernel 7.1.0 no tiene Landlock; hay que usar `--disable-sandbox`:

```
pacman -Syu --noconfirm --disable-sandbox
```

Tras la instalación limpia el sistema ya estaba al día (`there is nothing to do`).

## Credenciales

```
usuario: alarm   contraseña: alarm   (wheel, NOPASSWD en sudo)
root:             contraseña: alarm
SSH por USB:      ssh root@172.16.42.1
```

Cambiar ambas contraseñas en el primer arranque (`passwd`).

## Reproducir

```sh
# 1) rootfs (root, qemu-user binfmt para aarch64)
sudo scripts/build-kupfer-plasma-rootfs.sh

# 2) flasheo (borra userdata; NO toca persist/modemst1/modemst2/fsg/fsc/nvram)
sudo scripts/flash-kupfer-plasma.sh

# 3) red compartida en el portátil
sudo install -m755 scripts/host/begonia-usb-nat /usr/local/sbin/
sudo install -m644 scripts/host/begonia-usb-nat.service /etc/systemd/system/
sudo systemctl enable --now begonia-usb-nat
```

## Brillo y batería (2026-11-19)

### Brillo: funciona

```
/sys/class/backlight/lm36274-backlight  max=1879
powerdevil BrightnessControl            min=0 max=10000
setBrightness(1500) -> brightness=1200 (verificado en sysfs)
```

El control de Plasma escribe en el backlight a través de powerdevil; no hace falta udev
extra. El único detalle es que, con la pantalla en `DPMS=Off` por inactividad, los
valores que se leen del sysfs no reflejan lo que se pide (es el dimming, no un fallo).
Con la pantalla encendida el mapeo es correcto.

Default persistido: `800/1879` (~43 %) en
`/var/lib/systemd/backlight/platform-11007000.i2c-platform-lm36274-backlight.5.auto:backlight:lm36274-backlight`
(`systemd-backlight@backlight:lm36274-backlight` lo restaura en cada arranque).

### Batería: no hay gauge en el kernel 7.1.0

`/sys/class/power_supply` sólo expone `mt6360-chg` (TYPE=USB, `ONLINE`, `voltage_now`)
y el `tcpm-source`. No hay nodo `battery` ni `capacity`, y `CONFIG_*GAUGE*` no está en
el kernel que corre. UPower sólo ve "line power"; Plasma no puede mostrar porcentaje.

Lo que existe para maniobrar (API de GitLab, `glab api`):

- Proyecto `mt6785-mainline/linux` (GitLab `gitlab.postmarketos.org`, id 780).
- Rama **`battery-downstream`**: trae el stack completo importado del vendor:
  - `power: supply: mt6359p-gauge: Import from downstream` y renombrado a `mt6359-gauge`
  - `power: supply: mtk-battery*: Import from downstream`
  - `mfd: mt6397-core: Add support for gauge on MT6359 PMICs`
  - `rtc: mt6397: Implement nvmem`
  - `iio: adc: mt6359-auxadc: Switch to IIO_CHAN_INFO_PROCESSED`
  - `power: supply: mt6360_charger: Provide state updates for battery from charger`
  - `arm64: dts: mt6785-xiaomi-begonia: Enable pmic fuel gauge and battery manager`
    (nodo `battery-manager` + `mt6359_gauge` + perfiles `battery0_profile_t*`)
- Esa rama está basada en **6.16**, no en 7.1: `mt6359-gauge.c` da 404 en `7.1` y el
  compare inverso arrastra decenas de miles de commits. **No está mergeada.**

Para tener porcentaje real en Plasma hay dos caminos, ambos requieren reconstruir el
boot image:

1. **Rebasar la serie de batería sobre `7.1`** + los parches conn/WiFi de Kupfer y
   recompilar `linux-mt6785` (lo correcto a futuro).
2. **Construir sobre `battery-downstream` (6.16)** + la serie conn de 6.16 (lo que ya
   funcionaba antes del salto a 7.1), aceptando volver a 6.16.

Mientras tanto, el único dato de batería disponible es el canal IIO `batt_v` del
MT6359 (`/sys/bus/iio/devices/iio:device0/in_voltage12_raw`, `_scale` = 6300), que hoy
es crudo porque el cambio a `IIO_CHAN_INFO_PROCESSED` vive justamente en la rama de
batería. Serviría para una estimación por voltaje, nunca para el indicador nativo.

## Problemas conocidos

- **Batería**: sin gauge (ver arriba); `power_supply` sólo expone cargador USB.
- **SDDM**: instalado pero deshabilitado; el arranque va por getty autologin.
- **Panel/táctil Tianma**: el DTB de esta unidad es CSOT
  (`xiaomi,begonia-csot-nt36672a`), así que el nombre que pide el kernel es
  `novatek/nt36672a_begonia_csot.bin`. Se conservan ambos blobs; si algún día se cambia
  de panel, hay que alinear DTB y blob.
- **`linux-mt6785` no está registrado en pacman**: se extrae el paquete sobre el rootfs.
  `pacman -Syu` no lo toca (ni lo actualiza); para cambiar de kernel hay que reconstruir
  el boot image.
- **Landlock**: el kernel 7.1.0 no lo soporta, así que cualquier operación de pacman
  necesita `--disable-sandbox` (el sandbox de pacman 7.x no está disponible).

## Estado final verificado (2026-11-19 11:23, tras reinicio limpio)

```
uname -r                      7.1.0
systemctl --failed            0
card1-DSI-1/status            connected
panfrost                      Initialized panfrost 1.6.0 for 13040000.gpu
kwin_wayland                  renderD128 abierto (6 fds)
plasmashell                   PID 628, sesión Wayland activa
wlan0                         CLARO_JOEL connected, 192.168.100.76/24
/dev/input/event3             táctil novatek (spi1.0) registrado
internet por USB              ping 1.1.1.1 OK, https://archlinuxarm.org 200
```

## Rollback

```sh
fastboot flash boot recovery-local/aboot-6.16.img   # vuelve al 6.16.4 validado
```

El `userdata` es el rootfs: para volver al sistema anterior hace falta su imagen. El
sistema previo a esta instalación se borró a petición del dueño; no hay copia de datos.
