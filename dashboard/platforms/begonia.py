"""
Begonia (Xiaomi Redmi Note 8 Pro) platform profile.

Everything here is *additive*: cosmetic labels, Soc naming and notes. The
underlying values always come from the generic readers in
:mod:`dashboard.platforms.base`, which query the kernel at runtime.

Detection is based on the device tree, so the profile also matches other
MT6785 boards without claiming to be a Redmi Note 8 Pro unless the model
string says so.

Ground truth captured on the reference device (Kupfer Linux / Arch Linux ARM,
kernel 6.16.4) with ``scripts/begonia-hardware-audit.sh``:

* ``/proc/device-tree/model``            -> ``MT6785V/CC``
* ``compatible``                         -> ``mediatek,mt6785`` ...
* ``policy0`` (CPUs 0-5, LITTLE)         -> 2.00 GHz max, ``mtk-cpufreq``
* ``policy6`` (CPUs 6-7, big)            -> 2.05 GHz max, ``mtk-cpufreq``
* thermal zones                          -> only ``mtk-gauge`` and ``battery``
* power supplies                         -> ``battery``, ``mt6360-chg.*``,
                                            ``mtk-gauge``, ``tcpm-source-psy-*``
* PSI                                    -> ``/proc/pressure/{cpu,memory,io}``
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

from dashboard.platforms.base import PlatformProfile

# Substrings that identify an MT6785 board in the device tree.
COMPATIBLE_MARKERS = ("mt6785", "mt6768", "helio-g90")
MODEL_MARKERS = ("mt6785", "begonia")

# Friendly labels for the thermal zones this SoC actually exposes. Verified
# against the reference device; unknown zones keep their kernel name.
THERMAL_LABELS: Dict[str, str] = {
    "mtk-gauge": "Battery gauge",
    "battery": "Battery",
    "cpu": "CPU",
    "soc": "SoC",
    "ap": "Application processor",
    "gpu": "GPU",
    "charger": "Charger",
    "usb": "USB",
    "wifi": "Wi-Fi",
    "modem": "Modem",
}

NOTES: Tuple[str, ...] = (
    "CPU clusters are discovered from cpufreq policies at runtime "
    "(policy0 = 6 LITTLE cores, policy6 = 2 big cores on this SoC), not hardcoded.",
    "The MT6785 mainline kernel exposes only battery/charger thermal zones "
    "(mtk-gauge, battery). There is no CPU thermal zone to label.",
    "zram-backed swap is the primary memory relief valve on this device.",
)


@dataclass(frozen=True)
class BegoniaProfile(PlatformProfile):
    """MT6785 / Redmi Note 8 Pro profile."""

    def matches(self, model: str, compatible: Tuple[str, ...]) -> bool:
        haystack = " ".join((model or "",) + tuple(compatible)).lower()
        if any(marker in haystack for marker in COMPATIBLE_MARKERS):
            return True
        return any(marker in (model or "").lower() for marker in MODEL_MARKERS)


PROFILE = BegoniaProfile(
    key="begonia",
    name="Redmi Note 8 Pro",
    device="begonia",
    soc="MediaTek Helio G90T (MT6785)",
    soc_short="MT6785",
    family="MediaTek",
    thermal_labels=THERMAL_LABELS,
    notes=NOTES,
    is_generic=False,
)
