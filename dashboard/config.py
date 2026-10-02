"""
Runtime configuration for Begonia Dashboard.

Begonia defaults intentionally differ from upstream Lavender: the dashboard
performs privileged operations (systemd, packages, processes, power), so it
binds to loopback on its own port instead of 0.0.0.0:8080. Publish it through
Tailscale Serve rather than exposing the port — see docs/deployment.md.

Every value can be overridden from the environment so the same tree can run
unmodified on non-Begonia machines.
"""
import os
from urllib.parse import urlsplit

from dashboard.branding import APP_NAME  # noqa: F401  (re-exported for callers)


def _env(*names: str, default: str = "") -> str:
    """Return the first non-empty environment value among ``names``."""
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return default


def _env_int(*names: str, default: int) -> int:
    raw = _env(*names)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(*names: str, default: float) -> float:
    raw = _env(*names)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_flag(*names: str, default: bool = False) -> bool:
    raw = _env(*names)
    if not raw:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


# ===== Network =====
# Loopback by default: this UI can restart services, kill processes and
# install packages. Reach it over Tailscale (tailscale serve) or an SSH tunnel.
HOST = _env("BEGONIA_HOST", "DASHBOARD_HOST", default="127.0.0.1")
PORT = _env_int("BEGONIA_PORT", "DASHBOARD_PORT", default=8787)
DEBUG = _env_flag("BEGONIA_DEBUG", "DASHBOARD_DEBUG", default=False)

# Optional link to the separate personal fitness service. Reject non-HTTPS URLs
# and embedded credentials before passing this value to the template.
VIVI_FITNESS_URL = _env("VIVI_FITNESS_URL").strip()
if VIVI_FITNESS_URL:
    try:
        _vivi_url = urlsplit(VIVI_FITNESS_URL)
        if (
            _vivi_url.scheme.lower() != "https"
            or not _vivi_url.netloc
            or _vivi_url.username is not None
            or _vivi_url.password is not None
        ):
            VIVI_FITNESS_URL = ""
    except ValueError:
        VIVI_FITNESS_URL = ""

# Application version (SemVer: < 1.0 indicates development / pre-release status)
APP_VERSION = "0.1.0"


# Sudo commands that need elevation (documented limitation)
SUDO_COMMANDS = {
    "systemctl_system": ["sudo", "systemctl"],
    "apk_upgrade": ["sudo", "apk", "upgrade"],
    "apk_add": ["sudo", "apk", "add"],
    "apk_del": ["sudo", "apk", "del"],
    "pacman_upgrade": ["sudo", "pacman", "-Syu", "--noconfirm"],
    "pacman_add": ["sudo", "pacman", "-S", "--noconfirm"],
    "pacman_del": ["sudo", "pacman", "-R", "--noconfirm"],
    "reboot": ["sudo", "systemctl", "reboot"],
    "poweroff": ["sudo", "systemctl", "poweroff"],
    "suspend": ["sudo", "systemctl", "suspend"],
    "kill": ["sudo", "kill", "-9"],  # Some processes need root to kill
}

# Thermal threshold (millidegrees C) — warn above this
THERMAL_WARN_THRESHOLD = 70000  # 70°C

# Memory pressure threshold (fraction of RAM used)
MEMORY_PRESSURE_THRESHOLD = 0.85

# Number of lines for logs
LOG_LINES = 50

# Top N processes
TOP_PROCESSES = 20

# Top N directories for du
TOP_DIRS = 10

# ===== SSE Live Monitoring =====
# Default SSE poll intervals (ms) — each metric has its own
SSE_CPU_INTERVAL_MS = 1000      # CPU freq: every 1s
SSE_RAM_INTERVAL_MS = 3000      # RAM: every 3s
SSE_THERMAL_INTERVAL_MS = 5000  # Thermal: every 5s
SSE_BATTERY_INTERVAL_MS = 3000  # Battery: every 3s
SSE_NETWORK_INTERVAL_MS = 2000  # Network rate: every 2s
SSE_ZRAM_INTERVAL_MS = 3000     # zram swap: every 3s
SSE_PRESSURE_INTERVAL_MS = 2000  # PSI pressure: every 2s
SSE_PLATFORM_INTERVAL_MS = 15000  # CPU clusters: every 15s (rarely changes)
SSE_VIVI_INTERVAL_MS = 5000     # Vivi-AI services: every 5s

# Rolling buffer sizes (number of datapoints kept per metric)
SSE_CPU_BUFFER = 30
SSE_RAM_BUFFER = 20
SSE_THERMAL_BUFFER = 20
SSE_BATTERY_BUFFER = 30
SSE_NETWORK_BUFFER = 30
SSE_ZRAM_BUFFER = 30
SSE_PRESSURE_BUFFER = 30
SSE_PLATFORM_BUFFER = 10
SSE_VIVI_BUFFER = 20

# ===== Platform profile =====
# "auto" picks a known profile (e.g. begonia) from the device tree when it
# matches, and falls back to a generic Linux profile otherwise.
PLATFORM_PROFILE = _env("BEGONIA_PLATFORM", default="auto")

# ===== Health thresholds =====
HEALTH_THERMAL_WARN_C = _env_float("BEGONIA_THERMAL_WARN_C", default=70.0)
HEALTH_THERMAL_CRIT_C = _env_float("BEGONIA_THERMAL_CRIT_C", default=80.0)
HEALTH_ZRAM_WARN_RATIO = _env_float("BEGONIA_ZRAM_WARN_RATIO", default=0.9)
HEALTH_PSI_WARN = _env_float("BEGONIA_PSI_WARN", default=10.0)

# ===== OpenClaw scratch directory =====
# OpenClaw copies its plugin sources under <stateDir>/tmp/plugin-captures while
# a capture is alive. A gateway run legitimately holds a few GB there, so the
# health check only warns when the tree grows past the budget below or when
# several instances pile up (a sign that a dirty shutdown left scratch behind).
OPENCLAW_SCRATCH_DIR = _env("BEGONIA_OPENCLAW_SCRATCH", default="~/.openclaw/tmp/plugin-captures")
OPENCLAW_SCRATCH_WARN_BYTES = _env_int(
    "BEGONIA_OPENCLAW_SCRATCH_WARN_BYTES", default=6 * 1024 * 1024 * 1024
)
OPENCLAW_SCRATCH_INSTANCE_WARN = _env_int("BEGONIA_OPENCLAW_SCRATCH_INSTANCES", default=2)

# ===== Host watchlist surfaced in the dashboard =====
# Missing units are reported as "not installed" instead of failing the panel.
# Keep this list in sync with the units that really run on begonia
# (systemctl list-units / systemctl --user list-units); a stale entry shows up
# as a permanent "not installed" row. See docs/08-begonia-dashboard.md.
#
# Coverage: every unit enabled on begonia is listed here, so nothing enabled
# hides from the watchlist. The complete systemd inventory (installed or not,
# 129 units) is always available on the /services page regardless.
# Deliberately excluded, all of them plumbing with nothing to act on:
# getty@.service (console login template), systemd-tmpfiles-reset and other
# boot-time oneshots, and the user-session units wireplumber / xdg-user-dirs
# (desktop plumbing, inactive; the user bus itself is watched via dbus-broker).
#
# "optional": true marks a unit that is installed and reported but idle in
# normal operation, because it only matters when someone acts (tethering a
# phone, plugging a cable) or because the kernel makes it a permanent skip
# (haveged: ConditionKernelVersion=<5.6 is unmet on this 6.16 kernel).
# Optional units never degrade the health verdict while they are merely
# inactive; a unit in state "failed" still does.
VIVI_SERVICES = [
    # user manager (joel)
    {"unit": "openclaw-gateway.service", "scope": "user", "label": "OpenClaw Gateway"},
    {"unit": "opencode-free-proxy.service", "scope": "user", "label": "OpenCode Free Proxy"},
    {"unit": "opencode-run-bridge.service", "scope": "user", "label": "OpenCode Run Bridge"},
    {"unit": "dbus-broker.service", "scope": "user", "label": "User D-Bus"},
    # system manager
    {"unit": "opencode-web.service", "scope": "system", "label": "OpenCode Server"},
    {"unit": "vivi-fitness.service", "scope": "system", "label": "Vivi Fitness"},
    {"unit": "nginx.service", "scope": "system", "label": "Nginx"},
    {"unit": "tailscaled.service", "scope": "system", "label": "Tailscale"},
    {"unit": "sshd.service", "scope": "system", "label": "SSH"},
    {"unit": "NetworkManager.service", "scope": "system", "label": "Network"},
    {"unit": "NetworkManager-wait-online.service", "scope": "system", "label": "Network Wait Online"},
    {"unit": "NetworkManager-dispatcher.service", "scope": "system", "label": "Network Dispatcher", "optional": True},
    {"unit": "systemd-resolved.service", "scope": "system", "label": "DNS Resolver"},
    {"unit": "systemd-timesyncd.service", "scope": "system", "label": "Time Sync"},
    {"unit": "unudhcpd.service", "scope": "system", "label": "USB Tethering DHCP", "optional": True},
    {"unit": "usb-tethering.service", "scope": "system", "label": "USB Tethering", "optional": True},
    {"unit": "begonia-dashboard.service", "scope": "system", "label": "Dashboard"},
    {"unit": "begonia-firewall.service", "scope": "system", "label": "Firewall (nftables)"},
    {"unit": "display-off.service", "scope": "system", "label": "Backlight Off (headless)"},
    {"unit": "mediatek-wifi.service", "scope": "system", "label": "Wi-Fi (mediatek)"},
    {"unit": "haveged.service", "scope": "system", "label": "Entropy (haveged, legacy)", "optional": True},
]

# ===== Auth & Session Settings =====
# The UI binds to loopback and is published with `tailscale serve` (tailnet
# only), so on begonia the login gate is off by default: every request is served
# as a local, already elevated session for the unit user (see
# dashboard.auth.deps.get_auto_session). Set BEGONIA_AUTH=1 through
# /etc/begonia-dashboard.env or a systemd drop-in to restore the PAM login flow
# without touching code.
AUTH_ENABLED = _env_flag("BEGONIA_AUTH", "DASHBOARD_AUTH", default=False)
SESSION_COOKIE_NAME = "begonia_session"
SESSION_MAX_IDLE_MINUTES = _env_int("BEGONIA_SESSION_MAX_IDLE_MINUTES", default=60)
ADMIN_ELEVATION_TIMEOUT_MINUTES = _env_int("BEGONIA_ELEVATION_TIMEOUT_MINUTES", default=15)
SESSION_SECRET_KEY = _env(
    "BEGONIA_SECRET_KEY",
    "DASHBOARD_SECRET_KEY",
    default="rn7-dashboard-secret-key-default-2026",
)
PAM_SERVICE = _env("PAM_SERVICE", default="login")

# Rate Limiting
LOGIN_RATE_LIMIT = "10/minute"
