# Changelog

All notable changes to **PulseMonitor** are documented in this file.
This project adheres to [Semantic Versioning](https://semver.org/).

## [1.1.0] - 2026-11-02

### Added
- **Ubuntu / Debian Home Lab Support**:
  - Added `.deb` package builder (`linux/build_linux_packages.py`) producing `pulsemonitor_<version>_all.deb`.
  - Added one-step Ubuntu installer (`linux/install_ubuntu.sh`) and uninstaller (`linux/uninstall_ubuntu.sh`).
  - Added `systemd` service unit (`pulsemonitor.service`) and `pulsemonitor` CLI management command (`status`, `start`, `stop`, `restart`, `logs`, `url`, `version`).
  - Added `Dockerfile` and `docker-compose.yml` with host PID and network namespace support.
- **Linux Hardware Telemetry**:
  - Added CPU model detection from `/proc/cpuinfo` and OS distro detection from `/etc/os-release`.
  - Added CPU package thermal sensor reading (`coretemp`, `k10temp`, `cpu_thermal`).
  - Filtered synthetic Linux mounts (`squashfs`, `tmpfs`, `overlay`, `/dev/loop*`) from disk volume cards.
- **English Localization & Version Control**:
  - Converted Web UI, macOS Menu Bar app, and Linux CLI/installer scripts to English.
  - Added single-source `VERSION` file, `scripts/release.sh`, and GitHub Actions CI/Release workflow (`.github/workflows/release.yml`).

## [1.0.0] - 2026-11-01

### Added
- Initial release of **PulseMonitor** real-time local system monitoring dashboard (`FastAPI` + `psutil` + `WebSocket` + `Chart.js`).
- Real-time KPI cards and 60-point historical time-series charts for CPU, Memory, Disk I/O, and Network throughput.
- Per-core CPU utilization grid, memory allocation bar, disk partition cards, active IPv4 interfaces, and top 8 active processes table.
- Native macOS Menu Bar & Dock application (`PulseMonitor.app`) written in Swift (`AppKit` + `WebKit`).
