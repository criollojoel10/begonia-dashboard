"""
Begonia-specific live collectors (zram, PSI pressure, platform, Vivi-AI).

Kept out of :mod:`dashboard.services.live` so the upstream collectors stay
readable and the fork's additions are easy to spot and to remove.
"""
from __future__ import annotations

from dashboard.config import (
    SSE_PLATFORM_BUFFER,
    SSE_PLATFORM_INTERVAL_MS,
    SSE_PRESSURE_BUFFER,
    SSE_PRESSURE_INTERVAL_MS,
    SSE_VIVI_BUFFER,
    SSE_VIVI_INTERVAL_MS,
    SSE_ZRAM_BUFFER,
    SSE_ZRAM_INTERVAL_MS,
)
from dashboard.platforms import get_platform_info
from dashboard.services.live import MetricCollector
from dashboard.services.pressure import get_pressure
from dashboard.services.vivi import get_vivi_services
from dashboard.services.zram import get_zram


class ZramCollector(MetricCollector):
    """Compressed swap usage, sampled at :data:`SSE_ZRAM_INTERVAL_MS`."""

    def __init__(self, interval_ms: int = SSE_ZRAM_INTERVAL_MS,
                 history_size: int = SSE_ZRAM_BUFFER) -> None:
        super().__init__(interval_ms, history_size, buffer_key="zram")

    async def collect(self) -> dict:
        return get_zram()

    def _on_sample(self, sample: dict) -> None:
        ratio = sample.get("ratio")
        if isinstance(ratio, (int, float)):
            self._buffer.append(float(ratio))


class PressureCollector(MetricCollector):
    """PSI stall time, sampled at :data:`SSE_PRESSURE_INTERVAL_MS`."""

    def __init__(self, interval_ms: int = SSE_PRESSURE_INTERVAL_MS,
                 history_size: int = SSE_PRESSURE_BUFFER) -> None:
        super().__init__(interval_ms, history_size, buffer_key="pressure")

    async def collect(self) -> dict:
        return get_pressure()

    def _on_sample(self, sample: dict) -> None:
        summary = sample.get("summary") or {}
        value = summary.get("memory_full_avg60")
        if isinstance(value, (int, float)):
            self._buffer.append(float(value))


class PlatformCollector(MetricCollector):
    """CPU clusters / SoC identity. Changes rarely, so it polls slowly."""

    def __init__(self, interval_ms: int = SSE_PLATFORM_INTERVAL_MS,
                 history_size: int = SSE_PLATFORM_BUFFER) -> None:
        super().__init__(interval_ms, history_size, buffer_key="platform")

    async def collect(self) -> dict:
        return get_platform_info()


class ViviCollector(MetricCollector):
    """Status of the Vivi-AI workloads (systemd units)."""

    def __init__(self, interval_ms: int = SSE_VIVI_INTERVAL_MS,
                 history_size: int = SSE_VIVI_BUFFER) -> None:
        super().__init__(interval_ms, history_size, buffer_key="vivi")

    async def collect(self) -> dict:
        return get_vivi_services()

    def _on_sample(self, sample: dict) -> None:
        # History tracks how many units are up, which is what a sparkline of
        # "is the local AI stack alive" should show.
        active = sample.get("active_count")
        if isinstance(active, int):
            self._buffer.append(float(active))
