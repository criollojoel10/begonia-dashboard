"""
OpenClaw scratch directory monitoring.

OpenClaw captures plugin sources under
``<stateDir>/tmp/plugin-captures/<instanceId>`` while a capture is alive. Every
gateway run copies the whole ``acpx`` extension tree several times, so a healthy
run legitimately holds a few gigabytes until the process exits (OpenClaw has no
total disk quota and only reclaims on clean exit or on the next startup).

That makes this directory a useful operational signal: it is expected to be
non-empty while the gateway is working, but a surprising size or a pile of
instance directories means scratch from a dirty shutdown was left behind. The
health check treats it as a warning, never a failure — see
``docs/10-openclaw-scratch-disk.md`` in stack-arm.

Everything degrades to ``available: False`` when the directory is missing, so
this is harmless on machines that do not run OpenClaw.
"""
from __future__ import annotations

import os
from typing import Dict, List, Optional

from dashboard.config import (
    OPENCLAW_SCRATCH_DIR,
    OPENCLAW_SCRATCH_WARN_BYTES,
    OPENCLAW_SCRATCH_INSTANCE_WARN,
)

_INSTANCE_PREFIX = "captures"


def _dir_size(path: str, budget_bytes: int) -> Dict[str, object]:
    """Total size of ``path`` without following symlinks.

    Stops summing once ``budget_bytes`` is exceeded so a runaway directory never
    makes the health endpoint walk gigabytes of native binaries on every call.
    """
    total = 0
    truncated = False
    for root, dirs, files in os.walk(path, followlinks=False):
        # Do not descend into symlinked directories: they can point outside the
        # scratch tree and would double-count (or loop).
        dirs[:] = [d for d in dirs if not os.path.islink(os.path.join(root, d))]
        for name in files:
            file_path = os.path.join(root, name)
            try:
                total += os.stat(file_path, follow_symlinks=False).st_size
            except OSError:
                continue
            if total >= budget_bytes:
                return {"bytes": total, "truncated": True}
    return {"bytes": total, "truncated": truncated}


def get_openclaw_scratch() -> Dict[str, object]:
    """Size and instance count of the OpenClaw plugin-capture scratch tree."""
    path = os.path.expanduser(OPENCLAW_SCRATCH_DIR)

    if not os.path.isdir(path):
        return {
            "available": False,
            "path": path,
            "bytes": 0,
            "instances": [],
            "instance_count": 0,
            "truncated": False,
        }

    instances: List[Dict[str, object]] = []
    try:
        entries = sorted(os.listdir(path))
    except OSError:
        entries = []

    for name in entries:
        instance_path = os.path.join(path, name)
        if not os.path.isdir(instance_path):
            continue
        measured = _dir_size(instance_path, OPENCLAW_SCRATCH_WARN_BYTES)
        instances.append({
            "instance": name,
            "bytes": measured["bytes"],
            "truncated": measured["truncated"],
        })

    instances.sort(key=lambda item: int(item["bytes"]), reverse=True)  # type: ignore[arg-type]
    total = sum(int(item["bytes"]) for item in instances)
    warn_bytes = OPENCLAW_SCRATCH_WARN_BYTES

    if total >= warn_bytes:
        level = "warn"
    elif len(instances) >= OPENCLAW_SCRATCH_INSTANCE_WARN:
        # Several instances usually means the previous one never got reclaimed.
        level = "warn"
    else:
        level = "ok"

    return {
        "available": True,
        "path": path,
        "bytes": total,
        "warn_bytes": warn_bytes,
        "instances": instances,
        "instance_count": len(instances),
        "warn_instance_count": OPENCLAW_SCRATCH_INSTANCE_WARN,
        "level": level,
        "truncated": any(bool(item["truncated"]) for item in instances),
    }


def _fmt_bytes(value: int) -> str:
    size = float(value)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{size:.1f} TB"


def format_scratch(scratch: Optional[Dict[str, object]] = None) -> str:
    """Short human string such as ``4.0 GB across 1 instance``."""
    data = scratch if scratch is not None else get_openclaw_scratch()
    if not data.get("available"):
        return "not present"
    size = _fmt_bytes(int(data.get("bytes") or 0))
    count = int(data.get("instance_count") or 0)
    return f"{size} across {count} instance{'s' if count != 1 else ''}"
