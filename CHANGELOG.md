# Changelog

All notable changes to **PulseMonitor** are documented in this file.
This project adheres to [Semantic Versioning](https://semver.org/).

## [1.2.2] - 2026-11-02

### Added
- **Prominent Hostname Display & Multi-Node Tab Identification**:
  - Added a dedicated glowing **Hostname badge** (`#header-hostname-badge`) in the top header and a **Host** pill in the system metadata bar.
  - Dynamically prefixes the browser tab title with `[hostname] PulseMonitor` so multiple open server tabs (`pocser01`, `pocetac`, workstation) are immediately distinguishable.
- **Comprehensive Documentation & Screenshot**:
  - Updated `README.md` with dashboard preview screenshot (`docs/dashboard-preview.png`), API reference table, architecture layout, and complete multi-platform installation instructions.

## [1.2.1] - 2026-11-02

### Added
- **Copyright Footer & Open-Source GitHub Links**:
  - Added Copyright (`© 2026 EJICDON`) and open-source download link (`https://github.com/EJICDON/pulsemonitor`) to the Web Dashboard footer, top navigation bar, and native macOS Menu Bar app (`⌘G`).
- **Remote Deployment Enhancements**:
  - Added `/deploy.sh` and `/dist` endpoints for one-line LAN/Tailscale deployment and automatic `$HOME` permission normalization for SSH key auth.

### Fixed
- Fixed `/proc/cpuinfo` parsing priority on multi-core Linux Xeon/EPYC servers so `model name` is always matched before numeric `model` IDs.

## [1.2.0] - 2026-11-02

### Added
- **Virtual Machines (VM) Resource Allocation & Real-Time Usage Monitoring**:
  - Added `VMCollector` engine in `app.py` supporting **KVM / QEMU** (`qemu-system-*` cmdline inspection for `-name`, `-smp` vCPUs, and `-m` allocated RAM), **libvirt (`virsh`)**, **Proxmox VE (`qm list`)**, **Canonical Multipass**, **VirtualBox (`VBoxHeadless`)**, **VMware**, **Parallels**, and **Apple Virtualization.framework**.
  - Added 3 Host-to-VM Resource Allocation Overview cards tracking:
    - **vCPU Provisioning vs. Host Logical Cores** (including overcommit percentage & live host CPU load consumed by VMs).
    - **VM Memory Provisioning vs. Actual Physical RAM Usage (RSS)** (with dual-layer progress bar and host unallocated RAM headroom).
    - **Hypervisor Instance Summary** (Running, Stopped, Total VMs, and active hypervisor engines).
  - Added Per-VM Resource Allocation & Live Usage table with individual vCPU load bars, actual RSS vs. allocated RAM bars, host CPU share, and VM uptime.
  - Added interactive **"Preview Sample VMs"** mode in the Web UI to preview Home Lab multi-VM telemetry on hosts without active VMs.

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
