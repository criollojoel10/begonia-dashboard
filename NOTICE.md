# Begonia Dashboard

Begonia Dashboard is a Linux mobile monitoring and administration dashboard optimized for the
Xiaomi Redmi Note 8 Pro, codename `begonia`, running Arch Linux ARM or Kupfer Linux.

This project is derived from Lavender by minhazul73:

https://github.com/minhazul73/lavender

Lavender is distributed under the MIT License. The original license and copyright notice are
preserved in this repository, and the upstream link is rendered in the dashboard sidebar and on the
sign-in screen.

## Begonia-specific adaptations

- Xiaomi Redmi Note 8 Pro hardware detection (device tree `MT6785V/CC`)
- MediaTek Helio G90T / MT6785 CPU cluster discovery (6 LITTLE + 2 big)
- Arch Linux ARM and Kupfer Linux integration
- zram compressed-swap monitoring and PSI stall pressure
- Mobile battery, charger and thermal zone discovery
- Vivi-AI service monitoring (OpenClaw Gateway, OpenCode Server, Tailscale, SSH)
- Begonia visual identity (petroleum blue / cyan / violet)
- Hardened single-unit systemd deployment published over Tailscale Serve

## Upstream features preserved

Native PAM authentication, Cockpit-style administrative elevation, distro-agnostic package
management (`apk`, `apt`, `pacman`, `dnf`), systemd service management, storage and mount overview,
process management, network diagnostics and live SSE metric streaming.

## License

MIT. See [LICENSE](LICENSE).
