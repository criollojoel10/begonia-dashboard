#!/usr/bin/env bash
# begonia-hardware-audit.sh — auditoría de SOLO LECTURA del hardware del
# Redmi Note 8 Pro (begonia, MediaTek MT6785 / Helio G90T) bajo Arch Linux ARM.
#
# No escribe nada en el sistema: solo lee /proc, /sys, /etc y ejecuta comandos
# de consulta (lsblk, findmnt, ip, systemctl --list/--failed).
#
# Uso:
#   bash scripts/begonia-hardware-audit.sh > begonia-hardware-audit.txt 2>&1
#
# El resultado alimenta el perfil de plataforma (dashboard/platforms/begonia.py):
# agrupación big/LITTLE, etiquetas de thermal zones, zram y detección de SoC.

set -u

section() { printf '\n=== %s ===\n' "$1"; }

section "DATE"
date -Is

section "UNAME"
uname -a

section "OS RELEASE"
cat /etc/os-release 2>/dev/null || true

section "DEVICE TREE MODEL"
tr -d '\0' < /proc/device-tree/model 2>/dev/null || true
echo

section "DEVICE TREE COMPATIBLE"
tr '\0' '\n' < /proc/device-tree/compatible 2>/dev/null || true

section "CPUINFO"
cat /proc/cpuinfo

section "CPU POLICIES"
for p in /sys/devices/system/cpu/cpufreq/policy*; do
    [ -d "$p" ] || continue
    echo "--- $p ---"
    for f in affected_cpus related_cpus scaling_driver \
             scaling_available_governors scaling_governor \
             scaling_available_frequencies scaling_cur_freq \
             scaling_min_freq scaling_max_freq \
             cpuinfo_min_freq cpuinfo_max_freq; do
        if [ -r "$p/$f" ]; then
            printf '%s=' "$f"
            tr '\n' ' ' < "$p/$f"
            echo
        fi
    done
done

section "MEMORY"
cat /proc/meminfo

section "ZRAM"
zramctl 2>/dev/null || true
swapon --show 2>/dev/null || true

section "PRESSURE (PSI)"
for f in cpu memory io; do
    echo "--- /proc/pressure/$f ---"
    cat "/proc/pressure/$f" 2>/dev/null || echo "unavailable"
done

section "POWER SUPPLY"
for d in /sys/class/power_supply/*; do
    [ -d "$d" ] || continue
    echo "--- $d ---"
    for f in "$d"/*; do
        [ -f "$f" ] || continue
        [ -r "$f" ] || continue
        printf '%s=' "$(basename "$f")"
        head -c 300 "$f" 2>/dev/null
        echo
    done
done

section "THERMAL ZONES"
for z in /sys/class/thermal/thermal_zone*; do
    [ -d "$z" ] || continue
    printf -- '--- %s ---\n' "$z"
    printf 'type='; cat "$z/type" 2>/dev/null || true; echo
    printf 'temp='; cat "$z/temp" 2>/dev/null || true; echo
    for f in mode policy trip_point_0_temp trip_point_0_type; do
        [ -r "$z/$f" ] && { printf '%s=' "$f"; cat "$z/$f"; }
    done
done

section "HWMON"
for h in /sys/class/hwmon/hwmon*; do
    [ -d "$h" ] || continue
    echo "--- $h ---"
    printf 'name='; cat "$h/name" 2>/dev/null || true; echo
    for f in "$h"/*; do
        [ -f "$f" ] || continue
        [ -r "$f" ] || continue
        case "$(basename "$f")" in
            name) continue ;;
        esac
        printf '%s=' "$(basename "$f")"
        head -c 300 "$f" 2>/dev/null
        echo
    done
done

section "BLOCK DEVICES"
lsblk -e7 -o NAME,KNAME,TYPE,SIZE,FSTYPE,FSVER,LABEL,UUID,MOUNTPOINTS 2>/dev/null || lsblk

section "FILESYSTEMS"
findmnt -R -o TARGET,SOURCE,FSTYPE,OPTIONS,USE%,AVAIL 2>/dev/null || findmnt

section "NETWORK LINKS"
ip -details -statistics link 2>/dev/null || true

section "ADDRESSES"
ip address 2>/dev/null || true

section "ROUTES"
ip route 2>/dev/null || true
ip -6 route 2>/dev/null || true

section "SYSTEMD FAILED"
systemctl --failed --no-pager 2>/dev/null || true

section "USER SYSTEMD FAILED"
systemctl --user --failed --no-pager 2>/dev/null || true

section "RUNNING SERVICES"
systemctl list-units --type=service --state=running --no-pager 2>/dev/null || true

section "USER SERVICES (joel)"
systemctl --user list-units --type=service --state=running --no-pager 2>/dev/null || true
