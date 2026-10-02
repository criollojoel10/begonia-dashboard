"""
Vivi-AI workload overview.

Begonia runs the Vivi-AI stack (OpenClaw Gateway, `opencode serve`, Tailscale,
sshd) split between the system manager and the user manager. This service
reports a compact status row per unit so the dashboard can show whether the
local AI infrastructure is up without shelling into the device.

Units are configured in ``dashboard.config.VIVI_SERVICES``. Missing units are
reported as ``installed: False`` rather than raising, so the panel keeps
working on machines that do not run the stack at all. A unit marked
``optional`` in that list is reported the same way but excluded from the
required/active counters, because it idles until someone acts on the hardware it
watches.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from dashboard.config import VIVI_SERVICES
from dashboard.dependencies import run_command


_SHOW_PROPERTIES = (
    "LoadState",
    "ActiveState",
    "SubState",
    "UnitFileState",
    "MainPID",
    "MemoryCurrent",
    "NRestarts",
    "ActiveEnterTimestamp",
)

# ``systemctl show`` exits 0 even for a unit that does not exist, reporting
# LoadState=not-found. Only that load state counts as "not installed": a unit
# that exists but is stopped is still a configured workload.
_NOT_FOUND = {"not-found", "masked", ""}

_STATE_SEVERITY = {
    "failed": "bad",
    "inactive": "idle",
    "activating": "warn",
    "deactivating": "warn",
    "reloading": "warn",
    "active": "ok",
}


def _systemctl_cmd(scope: str, *args: str) -> List[str]:
    cmd = ["systemctl"]
    if scope == "user":
        cmd.append("--user")
    cmd.extend(args)
    return cmd


def _show_unit(unit: str, scope: str) -> Optional[Dict[str, str]]:
    code, out, _err = run_command(
        _systemctl_cmd(scope, "show", "--no-pager", f"--property={','.join(_SHOW_PROPERTIES)}", unit),
        timeout=10,
    )
    if code != 0 or not out:
        return None

    props: Dict[str, str] = {}
    for line in out.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            props[key.strip()] = value.strip()
    return props


def _to_int(value: Optional[str]) -> Optional[int]:
    if value is None:
        return None
    try:
        number = int(value)
    except ValueError:
        return None
    # systemd reports "n/a" as a very large unsigned value for some properties.
    if number >= 2 ** 63:
        return None
    return number


def get_vivi_services(services: Optional[List[Dict[str, str]]] = None) -> Dict[str, object]:
    """Return per-unit status for the configured Vivi-AI workloads."""
    configured = services if services is not None else VIVI_SERVICES
    entries: List[Dict[str, object]] = []

    for spec in configured:
        unit = spec["unit"]
        scope = spec.get("scope", "system")
        label = spec.get("label", unit)
        # Optional units are real, but only idle in normal operation (a unit tied
        # to hardware or a manual action). They are reported and shown, never
        # counted as a degraded workload.
        optional = bool(spec.get("optional", False))

        props = _show_unit(unit, scope)
        load_state = (props or {}).get("LoadState", "")
        if props is None or load_state in _NOT_FOUND:
            entries.append({
                "unit": unit,
                "scope": scope,
                "label": label,
                "optional": optional,
                "installed": False,
                "state": (props or {}).get("ActiveState") or "unknown",
                "severity": "idle",
                "memory_bytes": None,
                "restarts": None,
                "main_pid": None,
                "since": None,
            })
            continue

        state = props.get("ActiveState", "unknown")
        entries.append({
            "unit": unit,
            "scope": scope,
            "label": label,
            "optional": optional,
            "installed": True,
            "state": state,
            "sub_state": props.get("SubState"),
            "unit_file_state": props.get("UnitFileState"),
            "severity": _STATE_SEVERITY.get(state, "idle"),
            "memory_bytes": _to_int(props.get("MemoryCurrent")),
            "restarts": _to_int(props.get("NRestarts")),
            "main_pid": _to_int(props.get("MainPID")),
            "since": props.get("ActiveEnterTimestamp") or None,
        })

    installed = [entry for entry in entries if entry["installed"]]
    active = [entry for entry in installed if entry["state"] == "active"]
    # A failed unit is a fact worth surfacing even when optional, so failed_count
    # stays over every installed unit; only the "N/M active" warn uses required.
    failed = [entry for entry in installed if entry["state"] == "failed"]
    required = [entry for entry in installed if not entry["optional"]]
    required_active = [entry for entry in required if entry["state"] == "active"]
    optional_idle = [
        entry for entry in installed if entry["optional"] and entry["state"] != "active"
    ]

    return {
        "available": bool(installed),
        "count": len(entries),
        "installed_count": len(installed),
        "active_count": len(active),
        "required_count": len(required),
        "required_active_count": len(required_active),
        "optional_idle_count": len(optional_idle),
        "failed_count": len(failed),
        "services": entries,
    }
