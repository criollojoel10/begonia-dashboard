#!/bin/bash
# SPDX-License-Identifier: Apache-2.0
# Clean flash for begonia: verified Kupfer 7.1.0 boot + Plasma Mobile rootfs.
# Wipes userdata only. persist/modemst1/modemst2/fsg/fsc/nvram are never touched.
#
#   sudo BOOT_IMG=/path/boot-7.1.0.img ROOTFS=/path/rootfs-plasma.img.sparse \
#        scripts/flash-kupfer-plasma.sh
set -euo pipefail
cd "$(dirname "$0")/.."

FB=${FASTBOOT:-/home/joel/Projects/luma-begonia/tools/platform-tools/fastboot}
SERIAL=${SERIAL:-gqbqpbgawcqc8dpz}
BOOT_IMG=${BOOT_IMG:-/home/joel/Projects/luma-begonia/recovery-local/boot-7.1.0.img}
ROOTFS=${ROOTFS:-/home/joel/begonia-clean/rootfs-plasma.img.sparse}
VBMETA=${VBMETA:-/home/joel/Projects/luma-begonia/out/vbmeta-flags2.img}
BOOT_SHA=17b347242e639e656c8738210175d372747974b16373d7d240658edc042c39a1

[ -f "$ROOTFS" ] || { echo "missing $ROOTFS" >&2; exit 1; }
[ "$(sha256sum "$BOOT_IMG" | cut -d' ' -f1)" = "$BOOT_SHA" ] ||
    { echo "boot image hash mismatch" >&2; exit 1; }

echo "== target"
$FB -s "$SERIAL" getvar product
$FB -s "$SERIAL" getvar unlocked

echo "== wipe userdata + cache"
$FB -s "$SERIAL" -w

echo "== boot (Kupfer 7.1.0, verified)"
$FB -s "$SERIAL" flash boot "$BOOT_IMG"

echo "== userdata (rootfs label kupfer_root)"
time $FB -s "$SERIAL" flash userdata "$ROOTFS"

echo "== vbmeta (verification disabled)"
$FB -s "$SERIAL" flash vbmeta "$VBMETA"

echo "== reboot"
$FB -s "$SERIAL" reboot
