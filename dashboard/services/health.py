"""
Overall device health.

Combines the signals the dashboard already collects into a single
GREEN / YELLOW / RED verdict with an itemised reason list, so the overview
page can answer "is anything wrong?" in one glance instead of making the
operator read six widgets.

This is a heuristic, not a monitoring system: every threshold comes from
``dashboard.config`` and every check degrades to "unknown" instead of
failing when a sensor is missing.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from dashboard.config import (
    HEALTH_PSI_WARN,
    HEALTH_THERMAL_CRIT_C,
    HEALTH_THERMAL_WARN_C,
    HEALTH_ZRAM_WARN_RATIO,
    MEMORY_PRESSURE_THRESHOLD,
    THERMAL_WARN_THRESHOLD,
)
from dashboard.platforms import detect_platform, list_thermal_zones
from dashboard.services.openclaw_scratch import format_scratch, get_openclaw_scratch
from dashboard.services.pressure import get_pressure
from dashboard.services.storage import get_disk_usage
from dashboard.services.vivi import get_vivi_services
from dashboard.services.zram import get_zram

_LEVEL_RANK = {"ok": 0, "unknown": 0, "warn": 1, "bad": 2}


def _read_text(path: str) -> Optional[str]:
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as handle:
            return handle.read()
    except OSError:
        return None


def _memory_usage() -> Dict[str, object]:
    raw = _read_text("/proc/meminfo") or ""
    values: Dict[str, int] = {}
    for line in raw.splitlines():
        if ":" not in line:
            continue
        key, rest = line.split(":", 1)
        parts = rest.split()
        if parts:
            try:
                values[key.strip()] = int(parts[0])
            except ValueError:
                continue

    total = values.get("MemTotal", 0)
    available = values.get("MemAvailable", 0)
    used = max(total - available, 0)
    ratio = (used / total) if total else 0.0
    return {"total_kb": total, "available_kb": available, "used_kb": used, "ratio": round(ratio, 4)}


def _thermal_summary() -> Dict[str, object]:
    """Hottest readable thermal zone, in degrees Celsius."""
    hottest_type: Optional[str] = None
    hottest_c: Optional[float] = None

    for zone in list_thermal_zones():
        zone_type = zone["type"]
        # Thermal zones are matched by kernel name; the friendly label is only
        # for display and must never be used for path building.
        for name in _zone_dir_names(zone_type):
            raw = _read_text(f"/sys/class/thermal/{name}/temp")
            if not raw:
                continue
            try:
                temp_c = int(raw.strip().split()[0]) / 1000.0
            except (ValueError, IndexError):
                continue
            if hottest_c is None or temp_c > hottest_c:
                hottest_c, hottest_type = temp_c, zone_type
            break

    return {"hottest_c": hottest_c, "hottest_zone": hottest_type}


def _zone_dir_names(zone_type: str) -> List[str]:
    import os

    base = "/sys/class/thermal"
    try:
        names = sorted(os.listdir(base))
    except OSError:
        return []
    matches = []
    for name in names:
        if not name.startswith("thermal_zone"):
            continue
        value = (_read_text(f"{base}/{name}/type") or "").strip()
        if value == zone_type:
            matches.append(name)
    return matches


def _storage_summary() -> Dict[str, object]:
    worst: Optional[Dict[str, object]] = None
    try:
        disks = get_disk_usage() or []
    except Exception:
        return {"worst_percent": None, "mount": None}

    for disk in disks:
        # dashboard.services.storage reports pct_num (int) plus use_pct ("34%").
        percent = disk.get("pct_num")
        if percent is None:
            percent = str(disk.get("use_pct") or "").rstrip("%") or None
        if percent is None:
            continue
        try:
            percent_f = float(percent)
        except (TypeError, ValueError):
            continue
        if worst is None or percent_f > float(worst["percent"]):  # type: ignore[index]
            worst = {
                "percent": percent_f,
                "mount": disk.get("mount") or disk.get("mountpoint") or disk.get("target"),
            }

    return {"worst_percent": worst["percent"] if worst else None,
            "mount": worst["mount"] if worst else None}


def compute_health() -> Dict[str, object]:
    """Return ``{status, checks, summary}`` with status in green/yellow/red."""
    checks: List[Dict[str, object]] = []

    def add(key: str, label: str, level: str, detail: str, value: object = None) -> None:
        checks.append({
            "key": key,
            "label": label,
            "level": level,
            "detail": detail,
            "value": value,
        })

    # Memory
    memory = _memory_usage()
    ratio = float(memory["ratio"])
    if ratio >= MEMORY_PRESSURE_THRESHOLD:
        add("memory", "Memory", "bad", f"{ratio * 100:.0f}% used", memory)
    elif ratio >= MEMORY_PRESSURE_THRESHOLD - 0.10:
        add("memory", "Memory", "warn", f"{ratio * 100:.0f}% used", memory)
    else:
        add("memory", "Memory", "ok", f"{ratio * 100:.0f}% used", memory)

    # zram compression (informational: a small ratio is normal on cold data)
    zram = get_zram()
    if zram.get("available"):
        swap = zram.get("swap") or {}
        total = int(swap.get("total_bytes") or 0)
        used = int(swap.get("used_bytes") or 0)
        swap_ratio = (used / total) if total else 0.0
        level = "warn" if swap_ratio >= HEALTH_ZRAM_WARN_RATIO else "ok"
        ratio_txt = f", ratio {zram['ratio']}:1" if zram.get("ratio") else ""
        add("zram", "zram swap", level,
            f"{swap_ratio * 100:.0f}% used{ratio_txt}", zram)
    else:
        add("zram", "zram swap", "unknown", "no zram device", None)

    # PSI
    pressure = get_pressure()
    if pressure.get("available"):
        summary = pressure.get("summary") or {}
        mem_full = summary.get("memory_full_avg60")
        io_full = summary.get("io_full_avg60")
        worst = max((v for v in (mem_full, io_full) if isinstance(v, (int, float))), default=None)
        if worst is None:
            add("pressure", "Stall pressure", "unknown", "no PSI samples", pressure)
        elif worst >= HEALTH_PSI_WARN * 2:
            add("pressure", "Stall pressure", "bad", f"{worst:.1f}% stalled (60s avg)", pressure)
        elif worst >= HEALTH_PSI_WARN:
            add("pressure", "Stall pressure", "warn", f"{worst:.1f}% stalled (60s avg)", pressure)
        else:
            add("pressure", "Stall pressure", "ok", f"{worst:.1f}% stalled (60s avg)", pressure)
    else:
        add("pressure", "Stall pressure", "unknown", "PSI unavailable in kernel", None)

    # Thermal
    thermal = _thermal_summary()
    hottest = thermal.get("hottest_c")
    warn_c = min(HEALTH_THERMAL_WARN_C, THERMAL_WARN_THRESHOLD / 1000.0)
    if hottest is None:
        add("thermal", "Thermal", "unknown", "no thermal zone readable", None)
    elif float(hottest) >= HEALTH_THERMAL_CRIT_C:
        add("thermal", "Thermal", "bad", f"{hottest:.0f} °C ({thermal['hottest_zone']})", thermal)
    elif float(hottest) >= warn_c:
        add("thermal", "Thermal", "warn", f"{hottest:.0f} °C ({thermal['hottest_zone']})", thermal)
    else:
        add("thermal", "Thermal", "ok", f"{hottest:.0f} °C ({thermal['hottest_zone']})", thermal)

    # Storage
    storage = _storage_summary()
    worst_disk = storage.get("worst_percent")
    if worst_disk is None:
        add("storage", "Storage", "unknown", "no mount statistics", None)
    elif float(worst_disk) >= 95:
        add("storage", "Storage", "bad", f"{worst_disk:.0f}% on {storage['mount']}", storage)
    elif float(worst_disk) >= 85:
        add("storage", "Storage", "warn", f"{worst_disk:.0f}% on {storage['mount']}", storage)
    else:
        add("storage", "Storage", "ok", f"{worst_disk:.0f}% on {storage['mount']}", storage)

    # Vivi-AI workloads. Only the required units gate the verdict: an optional
    # unit (usb tethering and its DHCP helper) is idle until someone acts, and a
    # permanently YELLOW board for that reason trains the reader to ignore it.
    # A failed unit is still "bad" whatever its role.
    vivi = get_vivi_services()
    failed = int(vivi.get("failed_count") or 0)
    required_active = int(vivi.get("required_active_count") or 0)
    required_total = int(vivi.get("required_count") or 0)
    optional_idle = int(vivi.get("optional_idle_count") or 0)
    idle_note = f", {optional_idle} optional idle" if optional_idle else ""
    if not vivi.get("available"):
        add("vivi", "Vivi-AI", "unknown", "no configured unit found", vivi)
    elif failed:
        add("vivi", "Vivi-AI", "bad", f"{failed} unit(s) failed", vivi)
    elif required_total and required_active < required_total:
        add("vivi", "Vivi-AI", "warn",
            f"{required_active}/{required_total} required active{idle_note}", vivi)
    else:
        add("vivi", "Vivi-AI", "ok", f"{required_active} active{idle_note}", vivi)

    # OpenClaw plugin-capture scratch. Never "bad": a large tree is normal while
    # the gateway is working, so this only ever degrades the verdict to YELLOW.
    scratch = get_openclaw_scratch()
    if not scratch.get("available"):
        add("openclaw_scratch", "OpenClaw scratch", "unknown", "not present", scratch)
    else:
        detail = format_scratch(scratch)
        if scratch.get("truncated"):
            detail += " (measurement capped)"
        add("openclaw_scratch", "OpenClaw scratch",
            str(scratch.get("level") or "ok"), detail, scratch)

    worst_rank = max(_LEVEL_RANK.get(str(check["level"]), 0) for check in checks) if checks else 0
    status = {0: "green", 1: "yellow", 2: "red"}[worst_rank]

    platform = detect_platform()
    failing = [check["key"] for check in checks if check["level"] in ("warn", "bad")]

    return {
        "status": status,
        "checks": checks,
        "platform": platform.key,
        "summary": {
            "worst": [check["label"] for check in checks if check["level"] == "bad"],
            "degraded": [check["label"] for check in checks if check["level"] == "warn"],
            "failing_keys": failing,
        },
    }
