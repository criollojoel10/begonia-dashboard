"""
Begonia Dashboard — product identity.

Single source of truth for the user-visible name, subtitle and upstream
attribution, so the web UI, the OpenAPI metadata and the systemd unit stay
consistent after the Lavender → Begonia rebrand.

Begonia Dashboard is a fork of Lavender by minhazul73 (MIT). The upstream
credit is a license requirement: do not remove it.
"""

APP_NAME = "Begonia Dashboard"
APP_SHORT_NAME = "Begonia"
APP_SUBTITLE = "Redmi Note 8 Pro"
APP_IDENTITY = "Vivi-AI Infrastructure"

UPSTREAM_NAME = "Lavender"
UPSTREAM_AUTHOR = "minhazul73"
UPSTREAM_URL = "https://github.com/minhazul73/lavender"
UPSTREAM_LICENSE = "MIT"

PROJECT_URL = "https://github.com/criollojoel10/begonia-dashboard"

DERIVATION_NOTICE = (
    f"{APP_NAME} is derived from {UPSTREAM_NAME} by {UPSTREAM_AUTHOR} "
    f"({UPSTREAM_URL}), distributed under the {UPSTREAM_LICENSE} license. "
    "The original copyright notice and license text are preserved unchanged."
)

SHORT_DESCRIPTION = (
    "Linux mobile monitoring and administration dashboard optimized for the "
    "Xiaomi Redmi Note 8 Pro (begonia, MediaTek Helio G90T / MT6785) on "
    "Arch Linux ARM and Kupfer Linux. Runs on any Linux."
)

DESCRIPTION = f"{SHORT_DESCRIPTION} {DERIVATION_NOTICE}"

# Deployment identity (kept in sync with systemd/begonia-dashboard.service)
SERVICE_NAME = "begonia-dashboard"
INSTALL_DIR = "/opt/begonia-dashboard"

# Badges rendered in the sidebar/topbar. The architecture badge is resolved at
# render time from the detected machine, never hardcoded (see dashboard.main).
STATIC_BADGES = ("LIVE", "SYSTEMD", "TAILSCALE", "VIVI-AI")
