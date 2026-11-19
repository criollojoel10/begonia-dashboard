#!/bin/bash
# SPDX-License-Identifier: Apache-2.0
# Build a clean Arch Linux ARM + Kupfer 7.1.0 + Plasma Mobile rootfs for begonia.
# Run as root from the repository root. aarch64 binaries run through qemu-user binfmt.
#
#   sudo KERNEL_PKG=/path/linux-mt6785-7.1.0-1-aarch64.pkg.tar.xz \
#        FIRMWARE_DIR=/path/mt6785-mainline-firmware \
#        ALARM_TARBALL=/path/alarm-aarch64.tar.gz \
#        scripts/build-kupfer-plasma-rootfs.sh
set -euo pipefail
cd "$(dirname "$0")/.."

ALARM_TARBALL=${ALARM_TARBALL:-/home/joel/alarm-begonia/alarm-aarch64.tar.gz}
KERNEL_PKG=${KERNEL_PKG:-/home/joel/Projects/luma-begonia/recovery-local/linux-mt6785-7.1.0-1-aarch64.pkg.tar.xz}
FIRMWARE_DIR=${FIRMWARE_DIR:-/tmp/mt6785-fw}       # mediatek/ + novatek/
OUT=${OUT:-/home/joel/begonia-clean/rootfs-plasma.img}
SIZE=${SIZE:-10G}
MNT=${MNT:-/mnt/kroot}
MIRROR=${MIRROR:-https://ca.us.mirror.archlinuxarm.org}

[ "$(id -u)" = 0 ] || { echo "run as root" >&2; exit 1; }
[ -f "$ALARM_TARBALL" ] && [ -f "$KERNEL_PKG" ] || { echo "missing inputs" >&2; exit 1; }

cleanup() {
    ps -eo pid,args | awk '/[g]pg-agent --homedir/ {print $1}' | xargs -r kill -9 || true
    umount -l -R "$MNT" 2>/dev/null || true
}
trap cleanup EXIT

cleanup
rm -f "$OUT"
truncate -s "$SIZE" "$OUT"
mkfs.ext4 -q -F -L kupfer_root "$OUT"
mount -o loop "$OUT" "$MNT"

echo "== base + kernel + firmware"
tar -xzf "$ALARM_TARBALL" -C "$MNT" --numeric-owner
tar -xJf "$KERNEL_PKG" -C "$MNT" --overwrite --numeric-owner
mkdir -p "$MNT/lib/firmware"
cp -a "$FIRMWARE_DIR"/. "$MNT/lib/firmware"/

# /etc/resolv.conf is a symlink to /run/systemd/resolve in the ALARM tarball.
rm -f "$MNT/etc/resolv.conf"
printf 'nameserver 1.1.1.1\nnameserver 9.9.9.9\n' >"$MNT/etc/resolv.conf"
cat >"$MNT/etc/pacman.d/mirrorlist" <<EOF
Server = $MIRROR/\$arch/\$repo
Server = https://mirrors.ocf.berkeley.edu/archlinuxarm/\$arch/\$repo
EOF
ln -sf /proc/self/mounts "$MNT/etc/mtab"

mount --bind /dev "$MNT/dev"
mount -t proc proc "$MNT/proc"
mount -t sysfs sys "$MNT/sys"
mount --bind /dev/pts "$MNT/dev/pts" 2>/dev/null || true

echo "== packages"
chroot "$MNT" /bin/bash -euo pipefail -c '
pacman-key --init
pacman-key --populate archlinuxarm
pacman -Syy --noconfirm --disable-sandbox
pacman -Su  --noconfirm --disable-sandbox
pacman -S --noconfirm --needed --disable-sandbox \
    plasma-mobile plasma-workspace plasma-nano kwin sddm \
    plasma-nm plasma-pa plasma-settings kscreen powerdevil \
    bluedevil bluez bluez-utils kclock kweather milou konsole \
    plasma-keyboard qt6-wayland \
    networkmanager wpa_supplicant wireless-regdb iw \
    mesa mesa-utils noto-fonts noto-fonts-emoji \
    pipewire pipewire-pulse wireplumber \
    xdg-desktop-portal xdg-desktop-portal-kde \
    sudo nano
'

echo "== configuration"
chroot "$MNT" /bin/bash -euo pipefail -c '
depmod 7.1.0
echo begonia > /etc/hostname
ln -sf /usr/share/zoneinfo/America/Bogota /etc/localtime
sed -i "s/^#es_CO.UTF-8/es_CO.UTF-8/; s/^#en_US.UTF-8/en_US.UTF-8/" /etc/locale.gen
locale-gen
echo LANG=es_CO.UTF-8 > /etc/locale.conf
cat > /etc/fstab <<EOF
LABEL=kupfer_root  /      ext4   rw,noatime  0 1
tmpfs              /tmp   tmpfs  defaults,nosuid  0 0
EOF
id alarm >/dev/null 2>&1 || useradd -m -G wheel -s /bin/bash alarm
usermod -aG wheel,video,render,audio,network,input,storage,lp,rfkill alarm
echo "alarm:alarm" | chpasswd
echo "root:alarm"  | chpasswd
echo "%wheel ALL=(ALL:ALL) NOPASSWD: ALL" > /etc/sudoers.d/10-wheel
chmod 440 /etc/sudoers.d/10-wheel
systemctl disable sddm
'

echo "== wifi service"
cat >"$MNT/usr/local/sbin/begonia-wifi" <<'EOF'
#!/bin/bash
# Power on the MT6785 combo (WMT) and wait for wlan0. The char node wants
# the literal byte "1" (printf, not echo); firmware only downloads after it.
set -u
modprobe wmt_drv || exit 1
n=0
while [ ! -e /dev/wmtWifi ] && [ "$n" -lt 30 ]; do n=$((n+1)); sleep 1; done
modprobe wlan_gen4m || exit 1
printf 1 > /dev/wmtWifi || exit 1
n=0
while [ ! -d /sys/class/net/wlan0 ] && [ "$n" -lt 20 ]; do n=$((n+1)); sleep 1; done
[ -d /sys/class/net/wlan0 ]
EOF
chmod 755 "$MNT/usr/local/sbin/begonia-wifi"
cat >"$MNT/etc/systemd/system/begonia-conn.service" <<'EOF'
[Unit]
Description=MediaTek MT6785 internal WiFi (wmt_drv + wlan_gen4m)
After=systemd-modules-load.service
Before=NetworkManager.service bluetooth.service
StartLimitIntervalSec=0

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/local/sbin/begonia-wifi
TimeoutStartSec=120
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

echo "== usb gadget"
cat >"$MNT/usr/local/sbin/luma-usb-gadget" <<'EOF'
#!/bin/bash
set -e
modprobe libcomposite || true
modprobe u_ether || true
modprobe usb_f_ecm || true
g=/sys/kernel/config/usb_gadget/luma
mkdir -p "$g"; cd "$g"
echo 0x1d6b > idVendor; echo 0x0104 > idProduct
mkdir -p strings/0x409 configs/c.1/strings/0x409
echo "Begonia Kupfer" > strings/0x409/product
echo "Luma" > strings/0x409/manufacturer
echo "debug" > configs/c.1/strings/0x409/configuration
mkdir -p functions/ecm.usb0
ln -sf functions/ecm.usb0 configs/c.1/ 2>/dev/null || true
udc=$(ls /sys/class/udc | head -n1)
[ -n "$udc" ] && echo "$udc" > UDC
ip link set usb0 up
ip addr add 172.16.42.1/24 dev usb0 || true
EOF
chmod 755 "$MNT/usr/local/sbin/luma-usb-gadget"
cat >"$MNT/etc/systemd/system/luma-usb-gadget.service" <<'EOF'
[Unit]
Description=USB gadget networking for diagnostics
DefaultDependencies=no
After=sysinit.target
Wants=sysinit.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/local/sbin/luma-usb-gadget

[Install]
WantedBy=multi-user.target
EOF

echo "== ssh + autologin"
mkdir -p "$MNT/root/.ssh" "$MNT/home/alarm/.ssh"
install -m 600 "${SSH_PUBKEY:-$HOME/.ssh/id_ed25519.pub}" "$MNT/root/.ssh/authorized_keys"
install -m 600 -o 1000 -g 1000 "${SSH_PUBKEY:-$HOME/.ssh/id_ed25519.pub}" "$MNT/home/alarm/.ssh/authorized_keys"
sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin yes/' "$MNT/etc/ssh/sshd_config"
mkdir -p "$MNT/etc/systemd/system/getty@tty1.service.d"
cat >"$MNT/etc/systemd/system/getty@tty1.service.d/autologin.conf" <<'EOF'
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin alarm --noclear %I $TERM
EOF
cat >>"$MNT/home/alarm/.bash_profile" <<'EOF'

# Plasma Mobile on the phone console (tty1)
if [ "$(tty)" = "/dev/tty1" ] && [ -z "${WAYLAND_DISPLAY:-}" ]; then
    exec /usr/lib/plasma-dbus-run-session-if-needed /usr/bin/startplasmamobile
fi
EOF

chroot "$MNT" /bin/bash -c 'systemctl enable NetworkManager sshd bluetooth begonia-conn luma-usb-gadget'

echo "== finalize"
rm -rf "$MNT/var/cache/pacman/pkg"/* "$MNT/tmp"/* 2>/dev/null || true
cleanup
trap - EXIT
e2fsck -fy "$OUT" | tail -2 || true
tune2fs -c0 -i0 "$OUT" >/dev/null
rm -f "$OUT.sparse"
img2simg "$OUT" "$OUT.sparse"
ls -lh "$OUT.sparse"
sha256sum "$OUT.sparse"
