# 🚀 PulseMonitor v1.2.1 — Release Notes

**PulseMonitor** is a lightweight, zero-lag, real-time system and Home Lab monitoring dashboard built with **FastAPI**, **psutil**, **WebSockets**, and **Chart.js**. Designed for **Ubuntu / Debian Home Lab servers**, **Docker**, and **macOS** (with a native Menu Bar & Dock companion app), it provides instant visibility into host hardware telemetry and Virtual Machine (VM) resource allocation vs. live utilization.

🔗 **Open-Source Repository & Downloads**: [https://github.com/EJICDON/pulsemonitor](https://github.com/EJICDON/pulsemonitor)

---

## 🆕 What's New in v1.2.1

- **Open-Source Copyright Footer & GitHub Quick Links**:
  - Added a dedicated Copyright (`© 2026 EJICDON · Open-Source MIT License`) and open-source download bar at the bottom of the Web Dashboard (`https://github.com/EJICDON/pulsemonitor`).
  - Added a one-click **GitHub** button in the top navigation bar and a `⭐ Open Source on GitHub (EJICDON/pulsemonitor)` (`⌘G`) shortcut inside the native macOS Menu Bar app.
- **Improved Linux Multi-Socket Xeon / EPYC CPU Model Detection**:
  - Fixed `/proc/cpuinfo` parsing priority on x86_64 Linux servers so `model name` (e.g., `Intel(R) Xeon(R) CPU`) is always matched before numeric `model` IDs.
- **Streamlined LAN / Tailscale Remote Deployment (`/deploy.sh`)**:
  - Enhanced `/deploy.sh` to automatically fix home directory permissions (`chmod go-w $HOME`) for strict SSH daemon configurations and seamlessly hot-reload `v1.2.1` on remote Ubuntu servers.

---

## ✨ Core Features Overview (v1.0.0 – v1.2.1)

### 1. Real-Time Hardware Telemetry & Historical Trends
- **Instant Chart Hydration**: Backed by an in-memory 120-second ring buffer (`/api/history`) and live `/ws/metrics` WebSocket streaming (`0.5s`, `1.0s`, `2.0s`, `5.0s` sampling intervals with Pause/Resume controls).
- **4 Primary KPI Cards**:
  - **CPU Utilization**: Overall usage (`%`), physical & logical core counts, User / System / Idle split, `1m / 5m / 15m` Load Averages, and Linux CPU package thermal sensor (`°C`) support (`coretemp`, `k10temp`, `cpu_thermal`).
  - **Physical Memory (RAM & Swap)**: Used vs. total capacity, available memory, Swap usage, and visual allocation bar (`Wired/Buffers`, `Active`, `Cached/Inactive`, `Available`).
  - **Disk & Storage I/O**: Live read/write throughput (`KB/s` / `MB/s`), `IOPS`, and mounted volume capacity bars (automatically filtering Linux `snap`/`squashfs`, `overlay`, `tmpfs`, `/dev/loop*` and macOS synthetic sub-volumes).
  - **Network Throughput**: Real-time Download (`↓`) and Upload (`↑`) bandwidth curves, cumulative RX/TX totals, packet counts, and active IPv4 NIC badges.
- **Per-Core Load Grid & Top Active Processes**:
  - Individual utilization bars for all logical CPU cores with color-coded load thresholds.
  - Live **Top 8 Active Processes** sorted by CPU usage.

### 2. Virtual Machines (VM) Resource Allocation & Live Usage Monitoring
- **Multi-Hypervisor Auto-Discovery**:
  - Supports **KVM / QEMU** (`qemu-system-*` process inspection for `-name`, `-smp` vCPUs, and `-m` allocated memory), **libvirt (`virsh`)**, **Proxmox VE (`qm list`)**, **Canonical Multipass**, **VirtualBox (`VBoxHeadless`)**, **VMware**, **Parallels**, and **Apple Virtualization.framework**.
- **Host vs. VM Provisioning Overview**:
  - **vCPU Provisioning vs. Host Cores**: Tracks total allocated vCPUs against physical/logical host cores (including **Overcommit %** calculation) alongside real-time host CPU consumed by active VMs.
  - **VM Memory Provisioning vs. Actual Usage (RSS)**: Compares total provisioned VM RAM, actual resident physical memory (`RSS`) consumed by running VMs, and unallocated host RAM headroom.
  - **Per-VM Live Telemetry Table**: Displays each VM's state (`Running` / `Stopped`), provisioned vCPUs & live guest load bar, actual used RSS vs. allocated memory bar, host CPU share, and uptime.
  - **Built-in Demo Preview Mode**: One-click **"Preview Sample VMs"** button to preview multi-VM Home Lab telemetry on hosts without active VMs.

### 3. Multi-Platform Packaging & Deployment
- **Ubuntu / Debian Native `.deb` Installer (`pulsemonitor_1.2.1_all.deb`)**:
  - Installs to `/opt/pulsemonitor`, configures an isolated Python virtual environment, registers the `pulsemonitor.service` `systemd` unit for automatic startup on boot, and provides the `/usr/local/bin/pulsemonitor` CLI utility (`status`, `start`, `stop`, `restart`, `logs`, `url`, `version`).
- **Ubuntu / Linux One-Step Script Tarball (`pulsemonitor-ubuntu-1.2.1.tar.gz`)**:
  - Includes `linux/install_ubuntu.sh` and `linux/uninstall_ubuntu.sh` for any Linux distribution.
- **Docker & Docker Compose**:
  - Pre-configured `Dockerfile` and `docker-compose.yml` with `network_mode: host` and `pid: host` for accurate host-level monitoring.
- **macOS Native Menu Bar & Dock App (`PulseMonitor.app`)**:
  - Built natively with Swift (`AppKit` + `WebKit`), displaying live `⚡ CPU% · RAM%` in the macOS top Menu Bar and a dedicated native desktop window on Dock click.

---

## 📦 Installation & Quick Start

### Option A: Ubuntu / Debian `.deb` Package (Recommended for Home Lab)
```bash
sudo apt update
sudo apt install -y ./pulsemonitor_1.2.1_all.deb
pulsemonitor status
```

### Option B: Portable Linux Tarball
```bash
tar -xzf pulsemonitor-ubuntu-1.2.1.tar.gz
cd pulsemonitor
sudo bash linux/install_ubuntu.sh
```

### Option C: Docker Compose
```bash
docker compose up -d --build
```

Once started, open **`http://<server-ip>:8788`** in your browser.

---

## 📋 Release Assets (`v1.2.1`)
- `pulsemonitor_1.2.1_all.deb` — Native Debian / Ubuntu installer package (`systemd` + CLI included)
- `pulsemonitor-ubuntu-1.2.1.tar.gz` — Portable Linux installer bundle & Docker configuration
- `Source code (zip / tar.gz)` — Full source including macOS native Menu Bar app (`macos_app/`)

---
*Copyright © 2026 EJICDON · Open-Source under the MIT License — [https://github.com/EJICDON/pulsemonitor](https://github.com/EJICDON/pulsemonitor)*
