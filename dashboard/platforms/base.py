"""
Generic Linux platform detection.

This module never assumes a specific board. It reads what the kernel exposes:

* ``/proc/device-tree`` (or ``/sys/firmware/devicetree/base``) for the board
  model and ``compatible`` strings on ARM devices;
* ``/sys/devices/system/cpu/cpufreq/policy*`` for the CPU frequency domains,
  which is what actually defines the big.LITTLE cluster layout;
* the kernel's thermal-zone names.

The Begonia profile (:mod:`dashboard.platforms.begonia`) layers friendlier
labels on top; if it does not match, the generic profile is used and the
dashboard still works.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

CPU_ROOT = "/sys/devices/system/cpu"
DEVICE_TREE_ROOTS = (
    "/proc/device-tree",
    "/sys/firmware/devicetree/base",
)


@dataclass(frozen=True)
class CpuCluster:
    """One cpufreq policy / frequency domain."""

    policy: str
    cpus: Tuple[int, ...]
    governor: str
    cur_khz: int
    min_khz: int
    max_khz: int
    label: str = ""
    role: str = "generic"  # "efficiency" | "performance" | "generic"

    def as_dict(self) -> Dict[str, object]:
        return {
            "policy": self.policy,
            "cpus": list(self.cpus),
            "cpu_count": len(self.cpus),
            "governor": self.governor,
            "cur_khz": self.cur_khz,
            "min_khz": self.min_khz,
            "max_khz": self.max_khz,
            "label": self.label,
            "role": self.role,
        }


@dataclass(frozen=True)
class PlatformProfile:
    """A device profile. ``generic`` is the fallback for unknown hardware."""

    key: str
    name: str
    device: Optional[str] = None
    soc: Optional[str] = None
    soc_short: Optional[str] = None
    family: Optional[str] = None
    thermal_labels: Dict[str, str] = field(default_factory=dict)
    notes: Tuple[str, ...] = ()
    is_generic: bool = True


GENERIC_PROFILE = PlatformProfile(key="generic", name="Generic Linux")


# ---------------------------------------------------------------------------
# Low-level readers
# ---------------------------------------------------------------------------

def _read_text(path: str) -> Optional[str]:
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as handle:
            return handle.read()
    except (OSError, UnicodeError):
        return None


def _read_int_file(path: str, default: int = 0) -> int:
    raw = _read_text(path)
    if not raw:
        return default
    try:
        return int(raw.strip().split()[0])
    except (ValueError, IndexError):
        return default


def read_device_tree() -> Dict[str, object]:
    """Return the device-tree model and ``compatible`` strings.

    Both properties may be missing on x86 or on kernels without DT support,
    in which case the values are empty.
    """
    root = next((r for r in DEVICE_TREE_ROOTS if os.path.isdir(r)), None)
    if not root:
        return {"root": None, "model": None, "compatible": ()}

    model_raw = _read_text(os.path.join(root, "model"))
    model = model_raw.replace("\x00", "").strip() if model_raw else None

    compat_raw = _read_text(os.path.join(root, "compatible")) or ""
    compatible = tuple(c for c in compat_raw.split("\x00") if c.strip())

    return {"root": root, "model": model, "compatible": compatible}


def read_cpu_clusters() -> List[CpuCluster]:
    """Discover cpufreq frequency domains and their CPU members.

    The cluster layout is read from the kernel, never hardcoded: the Redmi
    Note 8 Pro exposes ``policy0`` (6 LITTLE cores) and ``policy6`` (2 big
    cores), but other boards expose a different split or a single policy.
    """
    cpufreq = os.path.join(CPU_ROOT, "cpufreq")
    if not os.path.isdir(cpufreq):
        return []

    policies = sorted(
        (name for name in os.listdir(cpufreq) if name.startswith("policy")),
        key=lambda name: int(name[6:]) if name[6:].isdigit() else 0,
    )

    raw: List[Dict[str, object]] = []
    for policy in policies:
        base = os.path.join(cpufreq, policy)
        if not os.path.isdir(base):
            continue

        affected = _read_text(os.path.join(base, "affected_cpus")) or ""
        if not affected:
            affected = _read_text(os.path.join(base, "related_cpus")) or ""
        cpus = tuple(sorted(int(c) for c in affected.split() if c.strip().isdigit()))
        if not cpus:
            continue

        raw.append({
            "policy": policy,
            "cpus": cpus,
            "governor": (_read_text(os.path.join(base, "scaling_governor")) or "").strip(),
            "cur_khz": _read_int_file(os.path.join(base, "scaling_cur_freq")),
            "min_khz": _read_int_file(os.path.join(base, "cpuinfo_min_freq"))
            or _read_int_file(os.path.join(base, "scaling_min_freq")),
            "max_khz": _read_int_file(os.path.join(base, "cpuinfo_max_freq"))
            or _read_int_file(os.path.join(base, "scaling_max_freq")),
        })

    if not raw:
        return []

    # Label the fastest cluster "performance" (big) only when the kernel
    # actually exposes two different frequency ceilings; everything lower is
    # "efficiency" (LITTLE). A single domain — or several domains that all top
    # out at the same frequency, as on most x86 laptops — stays generic so the
    # UI never claims a big.LITTLE split that does not exist.
    peaks = {int(item["max_khz"]) for item in raw}
    peak = max(peaks)
    big_little = len(raw) > 1 and len(peaks) > 1

    clusters: List[CpuCluster] = []
    for item in raw:
        max_khz = int(item["max_khz"])
        if not big_little:
            role, label = "generic", "CPU cluster"
        elif max_khz == peak:
            role, label = "performance", "Performance cluster (big)"
        else:
            role, label = "efficiency", "Efficiency cluster (LITTLE)"

        clusters.append(CpuCluster(
            policy=str(item["policy"]),
            cpus=tuple(item["cpus"]),  # type: ignore[arg-type]
            governor=str(item["governor"]),
            cur_khz=int(item["cur_khz"]),
            min_khz=int(item["min_khz"]),
            max_khz=max_khz,
            label=label,
            role=role,
        ))

    return clusters


def list_thermal_zones() -> List[Dict[str, str]]:
    """Return ``{type, label}`` for every thermal zone the kernel exposes."""
    zones: List[Dict[str, str]] = []
    base = "/sys/class/thermal"
    if not os.path.isdir(base):
        return zones
    for name in sorted(os.listdir(base)):
        if not name.startswith("thermal_zone"):
            continue
        zone_type = (_read_text(os.path.join(base, name, "type")) or "").strip()
        if not zone_type:
            continue
        zones.append({"type": zone_type, "label": zone_type})
    return zones


# ---------------------------------------------------------------------------
# Profile resolution
# ---------------------------------------------------------------------------

def _known_profiles() -> List[PlatformProfile]:
    """Import known device profiles lazily to avoid circular imports."""
    from dashboard.platforms import begonia

    return [begonia.PROFILE]


def detect_platform(forced_key: Optional[str] = None) -> PlatformProfile:
    """Resolve the running platform to a profile.

    ``forced_key`` (config ``PLATFORM_PROFILE``) short-circuits detection;
    ``"auto"`` or ``None`` means "detect, fall back to generic".
    """
    if forced_key and forced_key != "auto":
        for profile in _known_profiles():
            if profile.key == forced_key:
                return profile
        return GENERIC_PROFILE

    tree = read_device_tree()
    model = (tree.get("model") or "")
    compatible = tree.get("compatible") or ()

    for profile in _known_profiles():
        matcher = getattr(profile, "matches", None)
        if callable(matcher) and matcher(str(model), tuple(compatible)):
            return profile

    return GENERIC_PROFILE


def get_platform_info(forced_key: Optional[str] = None) -> Dict[str, object]:
    """Full platform snapshot for templates and API responses."""
    profile = detect_platform(forced_key)

    clusters = read_cpu_clusters()
    zones = list_thermal_zones()
    for zone in zones:
        zone["label"] = profile.thermal_labels.get(zone["type"], zone["type"])

    info: Dict[str, object] = {
        "key": profile.key,
        "name": profile.name,
        "device": profile.device,
        "soc": profile.soc,
        "soc_short": profile.soc_short,
        "family": profile.family,
        "is_generic": profile.is_generic,
        "notes": list(profile.notes),
        "cpu_clusters": [cluster.as_dict() for cluster in clusters],
        "thermal_zones": zones,
    }

    if not profile.is_generic:
        info["display"] = f"{profile.device or profile.name} · {profile.soc_short or profile.soc or ''}".strip(" ·")
    else:
        tree = read_device_tree()
        info["display"] = (tree.get("model") or profile.name) if tree.get("model") else profile.name

    return info
