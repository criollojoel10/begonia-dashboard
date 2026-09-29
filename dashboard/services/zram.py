"""
zram swap metrics.

Reads ``/sys/block/zram*/mm_stat`` (compressed-swap accounting) and
``/proc/swaps``. This matters on mobile devices where zram is the memory
relief valve: the useful number is not "swap free" but the compression ratio
and how much physical RAM the compressed pages actually occupy.
"""
from __future__ import annotations

import os
from typing import Dict, List, Optional

# mm_stat column order (Documentation/admin-guide/blockdev/zram.rst)
_MM_STAT_FIELDS = (
    "orig_data_size",
    "compr_data_size",
    "mem_used_total",
    "mem_limit",
    "mem_used_max",
    "same_pages",
    "pages_compacted",
    "huge_pages",
)


def _read_text(path: str) -> Optional[str]:
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as handle:
            return handle.read()
    except OSError:
        return None


def _read_int(path: str, default: int = 0) -> int:
    raw = _read_text(path)
    if not raw:
        return default
    try:
        return int(raw.strip().split()[0])
    except (ValueError, IndexError):
        return default


def list_devices() -> List[str]:
    root = "/sys/block"
    if not os.path.isdir(root):
        return []
    return sorted(
        (name for name in os.listdir(root) if name.startswith("zram")),
        key=lambda name: int(name[4:]) if name[4:].isdigit() else 0,
    )


def _read_mm_stat(device: str) -> Dict[str, int]:
    raw = _read_text(f"/sys/block/{device}/mm_stat")
    if not raw:
        return {}
    values = raw.split()
    out: Dict[str, int] = {}
    for index, field in enumerate(_MM_STAT_FIELDS):
        if index >= len(values):
            break
        try:
            out[field] = int(values[index])
        except ValueError:
            continue
    return out


def read_swap_summary() -> Dict[str, int]:
    """Parse /proc/swaps into totals (in bytes)."""
    total = used = 0
    raw = _read_text("/proc/swaps") or ""
    for line in raw.splitlines()[1:]:
        parts = line.split()
        if len(parts) < 5:
            continue
        try:
            total += int(parts[2]) * 1024
            used += int(parts[3]) * 1024
        except ValueError:
            continue
    return {"total_bytes": total, "used_bytes": used, "free_bytes": max(total - used, 0)}


def get_zram() -> Dict[str, object]:
    """Aggregate zram metrics across every zram device."""
    devices: List[Dict[str, object]] = []
    totals = {
        "disk_bytes": 0,
        "orig_bytes": 0,
        "compr_bytes": 0,
        "mem_used_bytes": 0,
        "mem_limit_bytes": 0,
    }

    for device in list_devices():
        stat = _read_mm_stat(device)
        disk_bytes = _read_int(f"/sys/block/{device}/disksize")
        entry: Dict[str, object] = {
            "device": device,
            "disk_bytes": disk_bytes,
            "orig_bytes": stat.get("orig_data_size", 0),
            "compr_bytes": stat.get("compr_data_size", 0),
            "mem_used_bytes": stat.get("mem_used_total", 0),
            "mem_limit_bytes": stat.get("mem_limit", 0),
            "same_pages": stat.get("same_pages", 0),
        }
        orig = int(entry["orig_bytes"])  # type: ignore[arg-type]
        compr = int(entry["compr_bytes"])  # type: ignore[arg-type]
        entry["ratio"] = round(orig / compr, 2) if compr else None

        for key, source in (
            ("disk_bytes", "disk_bytes"),
            ("orig_bytes", "orig_bytes"),
            ("compr_bytes", "compr_bytes"),
            ("mem_used_bytes", "mem_used_bytes"),
            ("mem_limit_bytes", "mem_limit_bytes"),
        ):
            totals[key] += int(entry[source])  # type: ignore[arg-type]

        devices.append(entry)

    swap = read_swap_summary()
    ratio = (
        round(totals["orig_bytes"] / totals["compr_bytes"], 2)
        if totals["compr_bytes"]
        else None
    )

    return {
        "available": bool(devices),
        "devices": devices,
        "device_count": len(devices),
        "disk_bytes": totals["disk_bytes"],
        "orig_bytes": totals["orig_bytes"],
        "compr_bytes": totals["compr_bytes"],
        "mem_used_bytes": totals["mem_used_bytes"],
        "mem_limit_bytes": totals["mem_limit_bytes"],
        "ratio": ratio,
        "swap": swap,
    }
