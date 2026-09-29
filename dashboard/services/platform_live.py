"""
Platform snapshot helpers shared by the API and the templates.

Keeps the ``PLATFORM_PROFILE`` override from ``dashboard.config`` in one place
so ``/api/system/platform``, the sidebar header and the overview card always
agree on which device they think they are running on.
"""
from __future__ import annotations

from typing import Dict

from dashboard.config import PLATFORM_PROFILE
from dashboard.platforms import get_platform_info


def get_platform_snapshot() -> Dict[str, object]:
    """Detected platform plus the CPU cluster labels resolved for display."""
    info = get_platform_info(PLATFORM_PROFILE)
    info["profile_override"] = PLATFORM_PROFILE
    return info
