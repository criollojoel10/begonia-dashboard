"""
PSI (Pressure Stall Information) metrics.

Reads ``/proc/pressure/{cpu,memory,io}``. PSI reports the share of time tasks
were stalled waiting for a resource, which is far more actionable than a
plain utilisation percentage on a phone-class SoC: it shows whether the
device is actually contended (memory reclaim, I/O thrash) or merely busy.

Kernels built without ``CONFIG_PSI`` do not expose these files; the reader
reports ``available: False`` instead of failing.
"""
from __future__ import annotations

from typing import Dict, Optional


PSI_RESOURCES = ("cpu", "memory", "io")


def _read(path: str) -> Optional[str]:
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as handle:
            return handle.read()
    except OSError:
        return None


def _parse_line(line: str) -> Optional[Dict[str, float]]:
    """Parse ``some avg10=0.66 avg60=0.66 avg300=1.56 total=1596325463``."""
    parts = line.split()
    if not parts:
        return None
    out: Dict[str, float] = {}
    for part in parts[1:]:
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        try:
            out[key] = float(value)
        except ValueError:
            continue
    return out or None


def get_pressure() -> Dict[str, object]:
    """Return ``{resource: {available, some, full}}`` for cpu, memory and io."""
    result: Dict[str, object] = {"available": False}

    for resource in PSI_RESOURCES:
        path = f"/proc/pressure/{resource}"
        raw = _read(path)
        if raw is None:
            result[resource] = {"available": False}
            continue

        entry: Dict[str, object] = {"available": True}
        for line in raw.splitlines():
            stripped = line.strip()
            if stripped.startswith("some"):
                entry["some"] = _parse_line(stripped)
            elif stripped.startswith("full"):
                entry["full"] = _parse_line(stripped)

        if "some" in entry or "full" in entry:
            result["available"] = True
        result[resource] = entry

    # Convenience scalars for the overview widgets and health calculation.
    memory = result.get("memory") or {}
    io = result.get("io") or {}
    cpu = result.get("cpu") or {}
    result["summary"] = {
        "memory_some_avg60": _avg(memory, "some", "avg60"),
        "memory_full_avg60": _avg(memory, "full", "avg60"),
        "io_full_avg60": _avg(io, "full", "avg60"),
        "cpu_some_avg60": _avg(cpu, "some", "avg60"),
    }

    return result


def _avg(entry: object, kind: str, field: str) -> Optional[float]:
    if not isinstance(entry, dict) or not entry.get("available"):
        return None
    block = entry.get(kind)
    if not isinstance(block, dict):
        return None
    value = block.get(field)
    return float(value) if isinstance(value, (int, float)) else None
