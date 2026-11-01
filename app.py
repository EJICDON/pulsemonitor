import asyncio
import os
import platform
import socket
import subprocess
import time
from collections import deque
from datetime import datetime
from typing import Any, Dict, List, Optional

import psutil
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
VERSION_FILE = os.path.join(BASE_DIR, "VERSION")


def get_app_version() -> str:
    try:
        with open(VERSION_FILE, "r", encoding="utf-8") as f:
            return f.read().strip() or "1.1.0"
    except Exception:
        return "1.1.0"


APP_VERSION = get_app_version()
app = FastAPI(title="PulseMonitor · Home Lab & System Dashboard", version=APP_VERSION)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Store up to 120 data points of historical metrics (~2 minutes at 1s interval)
HISTORY_MAX_LEN = 120
metrics_history: deque = deque(maxlen=HISTORY_MAX_LEN)


def get_cpu_brand() -> str:
    """Retrieve human-readable CPU brand string across Linux (Ubuntu) and macOS."""
    sys_name = platform.system()
    if sys_name == "Linux":
        try:
            with open("/proc/cpuinfo", "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if line.lower().startswith("model name"):
                        parts = line.split(":", 1)
                        if len(parts) > 1 and parts[1].strip():
                            return parts[1].strip()
                    elif line.lower().startswith("hardware") or line.lower().startswith("model"):
                        parts = line.split(":", 1)
                        if len(parts) > 1 and parts[1].strip():
                            return parts[1].strip()
        except Exception:
            pass
    elif sys_name == "Darwin":
        try:
            out = subprocess.check_output(
                ["sysctl", "-n", "machdep.cpu.brand_string"],
                stderr=subprocess.DEVNULL,
                text=True,
            ).strip()
            if out:
                return out
        except Exception:
            pass
    return platform.processor() or platform.machine()


def get_os_pretty_name() -> str:
    """Retrieve distro pretty name on Linux (e.g., Ubuntu 24.04 LTS) or macOS version."""
    sys_name = platform.system()
    if sys_name == "Linux":
        try:
            with open("/etc/os-release", "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if line.startswith("PRETTY_NAME="):
                        val = line.split("=", 1)[1].strip().strip('"').strip("'")
                        return f"{val} ({platform.machine()})"
        except Exception:
            pass
        return f"Linux {platform.release()} ({platform.machine()})"
    elif sys_name == "Darwin":
        mac_ver = platform.mac_ver()[0]
        if mac_ver:
            return f"macOS {mac_ver} ({platform.machine()})"
    return f"{sys_name} {platform.release()} ({platform.machine()})"


def get_cpu_temperature() -> Optional[float]:
    """Read primary CPU/SoC package temperature on Linux Home Lab servers if available."""
    if not hasattr(psutil, "sensors_temperatures"):
        return None
    try:
        temps = psutil.sensors_temperatures()
        if not temps:
            return None
        # Priority sensor keys on Ubuntu/Linux (Intel coretemp, AMD k10temp, Raspberry Pi cpu_thermal, nvme)
        preferred = ["coretemp", "k10temp", "zenpower", "cpu_thermal", "acpitz", "Package id 0"]
        for key in preferred:
            if key in temps and temps[key]:
                for entry in temps[key]:
                    if entry.current and entry.current > 0:
                        return round(float(entry.current), 1)
        # Fallback to first valid temperature sensor
        for entries in temps.values():
            for entry in entries:
                if entry.current and entry.current > 0:
                    return round(float(entry.current), 1)
    except Exception:
        pass
    return None


CPU_BRAND = get_cpu_brand()
OS_NAME = get_os_pretty_name()


class MetricsCollector:
    """Stateful collector that computes delta rates for network and disk I/O."""

    def __init__(self) -> None:
        self.last_time = time.time()
        self.last_net = psutil.net_io_counters()
        self.last_disk = psutil.disk_io_counters()
        psutil.cpu_percent(interval=None)
        psutil.cpu_percent(interval=None, percpu=True)

    def collect(self) -> Dict[str, Any]:
        now = time.time()
        dt = max(now - self.last_time, 1e-3)
        self.last_time = now

        # 1. CPU Metrics
        cpu_total = psutil.cpu_percent(interval=None)
        cpu_per_core = psutil.cpu_percent(interval=None, percpu=True)
        load_1, load_5, load_15 = (
            psutil.getloadavg() if hasattr(psutil, "getloadavg") else (0.0, 0.0, 0.0)
        )
        cpu_times = psutil.cpu_times_percent(interval=None)
        cpu_freq = psutil.cpu_freq()
        cpu_temp = get_cpu_temperature()

        # 2. Memory Metrics (Cross-platform macOS & Linux)
        vm = psutil.virtual_memory()
        swap = psutil.swap_memory()
        mem_used = vm.total - vm.available

        # On Linux, buffers + cached represent reclaimable cache; wired isn't present so we map buffers+slab
        wired_or_buffers = getattr(vm, "wired", 0) or (
            getattr(vm, "buffers", 0) + getattr(vm, "slab", 0)
        )
        inactive_or_cached = getattr(vm, "cached", 0) or getattr(vm, "inactive", 0)
        active_mem = getattr(vm, "active", 0) or max(
            0, mem_used - wired_or_buffers
        )

        # 3. Network Metrics (Rates & Totals)
        net_now = psutil.net_io_counters()
        net_up_bps = max(0.0, (net_now.bytes_sent - self.last_net.bytes_sent) / dt)
        net_down_bps = max(0.0, (net_now.bytes_recv - self.last_net.bytes_recv) / dt)
        self.last_net = net_now

        interfaces = []
        net_if_addrs = psutil.net_if_addrs()
        net_if_stats = psutil.net_if_stats()
        ignored_prefixes = (
            "utun",
            "awdl",
            "llw",
            "gif",
            "stf",
            "anpi",
            "veth",
            "br-",
            "docker0",
            "virbr",
        )
        for iface, addrs in net_if_addrs.items():
            if iface.startswith(ignored_prefixes):
                continue
            ipv4 = next(
                (a.address for a in addrs if a.family == socket.AF_INET), None
            )
            if not ipv4:
                continue
            st = net_if_stats.get(iface)
            interfaces.append(
                {
                    "name": iface,
                    "ip": ipv4,
                    "isup": st.isup if st else True,
                    "speed": st.speed if st else 0,
                }
            )

        # 4. Disk I/O & Partitions (Cleanly filtering Linux snap/loop/overlay & macOS synthetic volumes)
        disk_now = psutil.disk_io_counters()
        if disk_now and self.last_disk:
            disk_read_bps = max(
                0.0, (disk_now.read_bytes - self.last_disk.read_bytes) / dt
            )
            disk_write_bps = max(
                0.0, (disk_now.write_bytes - self.last_disk.write_bytes) / dt
            )
            disk_read_iops = max(
                0.0, (disk_now.read_count - self.last_disk.read_count) / dt
            )
            disk_write_iops = max(
                0.0, (disk_now.write_count - self.last_disk.write_count) / dt
            )
            self.last_disk = disk_now
        else:
            disk_read_bps = disk_write_bps = disk_read_iops = disk_write_iops = 0.0

        partitions = []
        seen_devices = set()
        ignored_fstypes = {
            "squashfs",
            "tmpfs",
            "devtmpfs",
            "overlay",
            "autofs",
            "proc",
            "sysfs",
            "cgroup2",
            "nsfs",
        }
        for part in psutil.disk_partitions(all=False):
            if part.fstype in ignored_fstypes or part.device.startswith("/dev/loop"):
                continue
            if platform.system() == "Darwin":
                if part.mountpoint.startswith("/System/Volumes/") and not part.mountpoint.startswith(
                    "/System/Volumes/Data"
                ):
                    continue
                if part.mountpoint == "/System/Volumes/Data":
                    continue
            if part.device in seen_devices:
                continue
            try:
                usage = psutil.disk_usage(part.mountpoint)
                if usage.total <= 0:
                    continue
                seen_devices.add(part.device)
                partitions.append(
                    {
                        "device": part.device,
                        "mountpoint": part.mountpoint,
                        "fstype": part.fstype,
                        "total": usage.total,
                        "used": usage.used,
                        "free": usage.free,
                        "percent": usage.percent,
                    }
                )
            except PermissionError:
                continue

        # 5. Battery Status
        battery_info = None
        if hasattr(psutil, "sensors_battery"):
            try:
                bat = psutil.sensors_battery()
                if bat is not None:
                    battery_info = {
                        "percent": round(bat.percent, 1),
                        "power_plugged": bool(bat.power_plugged),
                        "secsleft": (
                            bat.secsleft
                            if bat.secsleft
                            not in (psutil.POWER_TIME_UNLIMITED, psutil.POWER_TIME_UNKNOWN)
                            else None
                        ),
                    }
            except Exception:
                pass

        # 6. Top Processes by CPU & Memory
        processes: List[Dict[str, Any]] = []
        for proc in psutil.process_iter(
            ["pid", "name", "username", "cpu_percent", "memory_percent", "status"]
        ):
            try:
                pinfo = proc.info
                processes.append(
                    {
                        "pid": pinfo["pid"],
                        "name": pinfo["name"] or "Unknown",
                        "user": pinfo["username"] or "-",
                        "cpu": round(pinfo["cpu_percent"] or 0.0, 1),
                        "mem": round(pinfo["memory_percent"] or 0.0, 2),
                        "status": pinfo["status"] or "running",
                    }
                )
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        top_cpu_procs = sorted(processes, key=lambda x: x["cpu"], reverse=True)[:8]

        boot_time = psutil.boot_time()
        uptime_seconds = int(now - boot_time)

        snapshot = {
            "timestamp": datetime.fromtimestamp(now).strftime("%H:%M:%S"),
            "epoch": round(now, 2),
            "system": {
                "version": APP_VERSION,
                "hostname": socket.gethostname(),
                "os": OS_NAME,
                "platform": platform.system(),
                "cpu_brand": CPU_BRAND,
                "uptime_seconds": uptime_seconds,
                "boot_time": datetime.fromtimestamp(boot_time).strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
                "process_count": len(processes),
            },
            "cpu": {
                "total": round(cpu_total, 1),
                "per_core": [round(c, 1) for c in cpu_per_core],
                "cores_physical": psutil.cpu_count(logical=False) or 1,
                "cores_logical": psutil.cpu_count(logical=True) or 1,
                "load_avg": [round(load_1, 2), round(load_5, 2), round(load_15, 2)],
                "user": round(getattr(cpu_times, "user", 0.0), 1),
                "system": round(getattr(cpu_times, "system", 0.0), 1),
                "idle": round(getattr(cpu_times, "idle", 0.0), 1),
                "freq_mhz": round(cpu_freq.current, 0) if cpu_freq else None,
                "temp_c": cpu_temp,
            },
            "memory": {
                "total": vm.total,
                "used": mem_used,
                "available": vm.available,
                "percent": round(vm.percent, 1),
                "active": active_mem,
                "inactive": inactive_or_cached,
                "wired": wired_or_buffers,
                "swap_total": swap.total,
                "swap_used": swap.used,
                "swap_percent": round(swap.percent, 1),
            },
            "disk": {
                "read_bps": round(disk_read_bps, 1),
                "write_bps": round(disk_write_bps, 1),
                "read_iops": round(disk_read_iops, 1),
                "write_iops": round(disk_write_iops, 1),
                "total_read": disk_now.read_bytes if disk_now else 0,
                "total_write": disk_now.write_bytes if disk_now else 0,
                "partitions": partitions,
            },
            "network": {
                "up_bps": round(net_up_bps, 1),
                "down_bps": round(net_down_bps, 1),
                "total_sent": net_now.bytes_sent,
                "total_recv": net_now.bytes_recv,
                "packets_sent": net_now.packets_sent,
                "packets_recv": net_now.packets_recv,
                "interfaces": interfaces,
            },
            "battery": battery_info,
            "top_processes": top_cpu_procs,
        }
        return snapshot


collector = MetricsCollector()


@app.on_event("startup")
async def startup_collector() -> None:
    """Background loop collecting metrics every 1 second so history is always warm."""

    async def _loop() -> None:
        while True:
            try:
                snap = collector.collect()
                metrics_history.append(snap)
            except Exception as exc:
                print(f"[MetricsCollector Error] {exc}")
            await asyncio.sleep(1.0)

    asyncio.create_task(_loop())


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.get("/api/history")
async def get_history() -> Dict[str, Any]:
    if not metrics_history:
        metrics_history.append(collector.collect())
    return {
        "history": list(metrics_history),
        "latest": metrics_history[-1],
    }


@app.get("/api/metrics")
async def get_latest_metrics() -> Dict[str, Any]:
    if metrics_history:
        return metrics_history[-1]
    snap = collector.collect()
    metrics_history.append(snap)
    return snap


@app.websocket("/ws/metrics")
async def websocket_metrics(websocket: WebSocket) -> None:
    await websocket.accept()
    interval = 1.0
    try:
        while True:
            try:
                msg = await asyncio.wait_for(websocket.receive_json(), timeout=0.05)
                if isinstance(msg, dict) and "interval" in msg:
                    req_interval = float(msg["interval"])
                    interval = max(0.5, min(req_interval, 10.0))
            except asyncio.TimeoutError:
                pass

            latest = metrics_history[-1] if metrics_history else collector.collect()
            await websocket.send_json(latest)
            await asyncio.sleep(interval)
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
