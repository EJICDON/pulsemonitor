# PulseMonitor ⚡

**PulseMonitor** is a lightweight, real-time system and Home Lab monitoring dashboard powered by **FastAPI**, **psutil**, **WebSockets**, and **Chart.js**. It runs seamlessly on **Ubuntu / Debian Home Lab servers**, **Docker**, and **macOS** (with a native Menu Bar & Dock companion app).

---

## ✨ Key Features

- **Zero-Lag WebSocket Streaming**: Instant chart hydration via `/api/history` (rolling 120-second ring buffer) followed by live `/ws/metrics` updates (`0.5s`, `1.0s`, `2.0s`, or `5.0s` intervals).
- **Comprehensive Hardware Telemetry**:
  - **CPU**: Total utilization, user/system/idle breakdown, `1m / 5m / 15m` load averages, per-core load bars, and CPU thermal sensor readings (`°C`) on Linux servers.
  - **Memory (RAM & Swap)**: Used, Available, Wired/Kernel Buffers, Active, and Cached/Inactive breakdown.
  - **Disk & Storage I/O**: Live read/write throughput (`KB/s` / `MB/s`), `IOPS`, and clean physical partition capacity bars (automatically filtering out Linux `snap`/`loop`/`overlay` and macOS synthetic volumes).
  - **Network**: Real-time Download (`↓`) and Upload (`↑`) bandwidth curves, cumulative RX/TX bytes, packet counts, and active IPv4 NIC badges.
  - **Top Processes**: Live Top 8 active processes sorted by CPU utilization.
- **Multi-Platform Deployment**:
  - **Ubuntu / Debian `.deb` Package** with `systemd` auto-start service and `pulsemonitor` CLI tool.
  - **Docker & Docker Compose** with `network_mode: host` and `pid: host`.
  - **Native macOS Menu Bar & Dock App (`PulseMonitor.app`)** written in Swift.

---

## 🚀 Quick Start

### 1. Ubuntu / Debian Home Lab Server (`.deb` Package)

Build or download `pulsemonitor_<version>_all.deb` from **GitHub Releases**, then install on your Ubuntu server:

```bash
# Build .deb and .tar.gz packages locally:
python3 linux/build_linux_packages.py

# Copy to your Home Lab server and install:
scp dist/pulsemonitor_1.1.0_all.deb user@<homelab-ip>:~/
ssh user@<homelab-ip> "sudo apt update && sudo apt install -y ./pulsemonitor_1.1.0_all.deb"
```

Once installed, manage the service using the built-in CLI:

```bash
pulsemonitor status    # Check systemd status and LAN URL
pulsemonitor logs      # Tail live service logs
pulsemonitor restart   # Restart service
pulsemonitor stop      # Stop service
pulsemonitor version   # Show installed version
```

Open `http://<homelab-ip>:8788` from any browser on your LAN.

---

### 2. Ubuntu / Linux One-Step Script Installer

```bash
tar -xzf dist/pulsemonitor-ubuntu-1.1.0.tar.gz
cd pulsemonitor
sudo bash linux/install_ubuntu.sh
```

To uninstall:

```bash
sudo bash linux/uninstall_ubuntu.sh
```

---

### 3. Docker Compose (Home Lab Container)

```bash
docker compose up -d --build
```

---

### 4. Local Development & macOS Native Menu Bar App

Run directly with the startup script:

```bash
./run.sh
```

Build the native macOS Menu Bar & Dock application (`PulseMonitor.app`):

```bash
./macos_app/build_app.sh
open PulseMonitor.app
```

---

## 🏷️ Version Control & GitHub Releases

The project version is tracked in [`VERSION`](VERSION).

To release a new version (which automatically updates `VERSION`, rebuilds the `.deb` & `.tar.gz` artifacts, creates a Git commit, and tags `vX.Y.Z`):

```bash
./scripts/release.sh 1.2.0 "Describe your new feature or fix"
git push origin main --follow-tags
```

When a `v*.*.*` tag is pushed to GitHub, the GitHub Actions workflow (`.github/workflows/release.yml`) automatically builds and attaches `pulsemonitor_<version>_all.deb` and `pulsemonitor-ubuntu-<version>.tar.gz` to a new **GitHub Release**.
# pulsemonitor
# pulsemonitor
# pulsemonitor
