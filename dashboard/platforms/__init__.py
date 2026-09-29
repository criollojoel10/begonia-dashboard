"""Hardware platform profiles.

Two layers, deliberately separated:

* :mod:`dashboard.platforms.base` — generic Linux readers (device tree,
  cpufreq policies, thermal zones). Everything here must keep working on any
  Linux, including x86 laptops.
* :mod:`dashboard.platforms.begonia` — an enrichment layer that only adds
  cosmetic labels and notes when the running device really is a Redmi Note 8
  Pro (``begonia`` / MT6785).

Nothing in this package may hardcode a sensor path that the generic layer
could discover.
"""
from dashboard.platforms.base import (  # noqa: F401
    CpuCluster,
    PlatformProfile,
    detect_platform,
    get_platform_info,
    list_thermal_zones,
    read_cpu_clusters,
    read_device_tree,
)
