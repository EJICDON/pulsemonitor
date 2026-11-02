import asyncio
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import time
from collections import deque
from datetime import datetime
from typing import Any, Dict, List, Optional

import psutil
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
DIST_DIR = os.path.join(BASE_DIR, "dist")
VERSION_FILE = os.path.join(BASE_DIR, "VERSION")


def get_app_version() -> str:
    try:
        with open(VERSION_FILE, "r", encoding="utf-8") as f:
            return f.read().strip() or "1.2.0"
    except Exception:
        return "1.2.0"


APP_VERSION = get_app_version()
app = FastAPI(title="PulseMonitor · Home Lab & System Dashboard", version=APP_VERSION)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
if os.path.isdir(DIST_DIR):
    app.mount("/dist", StaticFiles(directory=DIST_DIR), name="dist")

# Store up to 120 data points of historical metrics (~2 minutes at 1s interval)
HISTORY_MAX_LEN = 120
metrics_history: deque = deque(maxlen=HISTORY_MAX_LEN)


def get_cpu_brand() -> str:
    """Retrieve human-readable CPU brand string across Linux (Ubuntu) and macOS."""
    sys_name = platform.system()
    if sys_name == "Linux":
        try:
            with open("/proc/cpuinfo", "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
            for line in lines:
                key = line.split(":", 1)[0].strip().lower()
                if key == "model name":
                    val = line.split(":", 1)[1].strip()
                    if val:
                        return val
            for line in lines:
                key = line.split(":", 1)[0].strip().lower()
                if key in ("hardware", "processor", "cpu model"):
                    val = line.split(":", 1)[1].strip()
                    if val and not val.isdigit():
                        return val
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
        preferred = ["coretemp", "k10temp", "zenpower", "cpu_thermal", "acpitz", "Package id 0"]
        for key in preferred:
            if key in temps and temps[key]:
                for entry in temps[key]:
                    if entry.current and entry.current > 0:
                        return round(float(entry.current), 1)
        for entries in temps.values():
            for entry in entries:
                if entry.current and entry.current > 0:
                    return round(float(entry.current), 1)
    except Exception:
        pass
    return None


CPU_BRAND = get_cpu_brand()
OS_NAME = get_os_pretty_name()


def parse_qemu_cmdline(cmdline: List[str], default_cores: int, default_mem: int) -> Dict[str, Any]:
    """
    Parse QEMU/KVM command line arguments (-name, -smp, -m, -id) to extract:
    - VM Name
    - Allocated vCPUs
    - Allocated Memory in bytes
    """
    vm_name = None
    vcpus = 1
    alloc_mem_bytes = 0
    vm_id = None

    i = 0
    n = len(cmdline)
    while i < n:
        arg = cmdline[i]
        if arg == "-name" and i + 1 < n:
            raw_name = cmdline[i + 1]
            # Handle libvirt/Proxmox format: guest=ubuntu-vm,debug-threads=on
            for part in raw_name.split(","):
                if part.startswith("guest="):
                    vm_name = part.split("=", 1)[1]
                    break
            if not vm_name:
                vm_name = raw_name.split(",")[0]
            i += 2
            continue
        elif arg == "-id" and i + 1 < n:
            vm_id = cmdline[i + 1]
            i += 2
            continue
        elif arg == "-smp" and i + 1 < n:
            smp_str = cmdline[i + 1]
            # e.g. "4,sockets=1,cores=4,threads=1" or "cpus=8,maxcpus=8" or "4"
            m_cpus = re.search(r"(?:^|,)(?:cpus=)?(\d+)", smp_str)
            if m_cpus:
                vcpus = max(1, int(m_cpus.group(1)))
            else:
                m_cores = re.search(r"cores=(\d+)", smp_str)
                if m_cores:
                    vcpus = max(1, int(m_cores.group(1)))
            i += 2
            continue
        elif arg == "-m" and i + 1 < n:
            mem_str = cmdline[i + 1]
            # e.g. "4096" or "size=8192M" or "8G"
            m_mem = re.search(r"(?:size=)?(\d+(?:\.\d+)?)([KMGTP]?)", mem_str, re.IGNORECASE)
            if m_mem:
                val = float(m_mem.group(1))
                unit = m_mem.group(2).upper()
                if unit == "G":
                    alloc_mem_bytes = int(val * 1024 * 1024 * 1024)
                elif unit == "K":
                    alloc_mem_bytes = int(val * 1024)
                elif unit == "T":
                    alloc_mem_bytes = int(val * 1024 * 1024 * 1024 * 1024)
                else:
                    # Default unit in QEMU -m is MiB
                    alloc_mem_bytes = int(val * 1024 * 1024)
            i += 2
            continue
        i += 1

    if not vm_name:
        vm_name = f"vm-{vm_id}" if vm_id else "qemu-vm"
    if alloc_mem_bytes <= 0:
        alloc_mem_bytes = default_mem
    return {
        "name": vm_name,
        "vm_id": vm_id,
        "vcpus": min(vcpus, default_cores * 4),
        "allocated_memory": alloc_mem_bytes,
    }


class VMCollector:
    """
    Discovers Virtual Machines and collects both Resource Allocation (vCPUs, Allocated RAM)
    and Current Usage (CPU %, Resident RAM RSS, Status, Uptime) across:
    - QEMU / KVM (Linux Home Lab, Proxmox VE, libvirt, UTM)
    - libvirt (`virsh` CLI for stopped/paused VMs & domain metadata)
    - Proxmox VE (`qm list` CLI if available)
    - Multipass (`multipass list --format json` if available)
    - VirtualBox (`VBoxHeadless`), VMware (`vmware-vmx`), Parallels (`prl_vm_app`), Apple Virtualization
    """

    def __init__(self) -> None:
        self.last_cli_sync = 0.0
        self.cached_cli_vms: Dict[str, Dict[str, Any]] = {}
        self.has_virsh = shutil.which("virsh") is not None
        self.has_qm = shutil.which("qm") is not None
        self.has_multipass = shutil.which("multipass") is not None

    def _sync_cli_metadata(self) -> None:
        """Periodically poll virsh / qm / multipass (every 5s) for configured & stopped VMs."""
        now = time.time()
        if now - self.last_cli_sync < 5.0:
            return
        self.last_cli_sync = now
        discovered: Dict[str, Dict[str, Any]] = {}

        # 1. Proxmox VE `qm list`
        if self.has_qm:
            try:
                out = subprocess.check_output(
                    ["qm", "list"], stderr=subprocess.DEVNULL, text=True, timeout=2.0
                )
                for line in out.splitlines()[1:]:
                    parts = line.split()
                    if len(parts) >= 6:
                        vmid, name, status, mem_mb, _disk_gb, pid = (
                            parts[0],
                            parts[1],
                            parts[2].lower(),
                            float(parts[3]),
                            parts[4],
                            int(parts[5]),
                        )
                        discovered[name] = {
                            "id": vmid,
                            "name": name,
                            "hypervisor": "Proxmox KVM",
                            "status": "running" if status == "running" else "stopped",
                            "vcpus": 0,  # Enriched from QEMU cmdline if running
                            "allocated_memory": int(mem_mb * 1024 * 1024),
                            "pid": pid if pid > 0 else None,
                        }
            except Exception:
                pass

        # 2. libvirt `virsh list --all`
        if self.has_virsh and not discovered:
            try:
                out = subprocess.check_output(
                    ["virsh", "list", "--all"],
                    stderr=subprocess.DEVNULL,
                    text=True,
                    timeout=2.0,
                )
                for line in out.splitlines()[2:]:
                    line_s = line.strip()
                    if not line_s:
                        continue
                    parts = line_s.split(None, 2)
                    if len(parts) >= 3:
                        dom_id, dom_name, dom_state = parts[0], parts[1], parts[2].lower()
                        vcpus = 1
                        max_mem_bytes = 0
                        try:
                            info_out = subprocess.check_output(
                                ["virsh", "dominfo", dom_name],
                                stderr=subprocess.DEVNULL,
                                text=True,
                                timeout=1.5,
                            )
                            for iline in info_out.splitlines():
                                if iline.startswith("CPU(s):"):
                                    vcpus = int(iline.split(":", 1)[1].strip())
                                elif iline.startswith("Max memory:"):
                                    # e.g. "4194304 KiB"
                                    val_kb = int(iline.split(":", 1)[1].strip().split()[0])
                                    max_mem_bytes = val_kb * 1024
                        except Exception:
                            pass
                        discovered[dom_name] = {
                            "id": dom_id if dom_id != "-" else None,
                            "name": dom_name,
                            "hypervisor": "KVM / libvirt",
                            "status": "running" if "running" in dom_state else ("paused" if "paused" in dom_state else "stopped"),
                            "vcpus": vcpus,
                            "allocated_memory": max_mem_bytes,
                            "pid": None,
                        }
            except Exception:
                pass

        # 3. Canonical Multipass
        if self.has_multipass:
            try:
                out = subprocess.check_output(
                    ["multipass", "list", "--format", "json"],
                    stderr=subprocess.DEVNULL,
                    text=True,
                    timeout=2.0,
                )
                data = json.loads(out)
                for item in data.get("list", []):
                    name = item.get("name", "multipass-vm")
                    state = item.get("state", "Stopped").lower()
                    discovered[name] = {
                        "id": None,
                        "name": name,
                        "hypervisor": "Multipass",
                        "status": "running" if state == "running" else "stopped",
                        "vcpus": 1,
                        "allocated_memory": 0,
                        "pid": None,
                    }
            except Exception:
                pass

        self.cached_cli_vms = discovered

    def collect(self, host_logical_cores: int, host_total_mem: int) -> Dict[str, Any]:
        self._sync_cli_metadata()
        now = time.time()

        vms_by_name: Dict[str, Dict[str, Any]] = {}
        # Start with CLI-discovered VMs (including stopped ones)
        for name, meta in self.cached_cli_vms.items():
            vms_by_name[name] = {
                "id": meta.get("id") or "-",
                "pid": meta.get("pid"),
                "name": name,
                "hypervisor": meta.get("hypervisor", "KVM/QEMU"),
                "status": meta.get("status", "stopped"),
                "vcpus": meta.get("vcpus") or 1,
                "cpu_host_percent": 0.0,
                "cpu_vm_percent": 0.0,
                "allocated_memory": meta.get("allocated_memory") or 0,
                "used_memory": 0,
                "memory_vm_percent": 0.0,
                "uptime_seconds": 0,
            }

        # Scan running hypervisor processes via psutil for live CPU & RSS memory telemetry
        for proc in psutil.process_iter(
            ["pid", "name", "cmdline", "cpu_percent", "memory_info", "create_time"]
        ):
            try:
                pinfo = proc.info
                pname = (pinfo.get("name") or "").lower()
                cmdline = pinfo.get("cmdline") or []

                hypervisor_type = None
                if pname.startswith("qemu-system") or pname == "kvm":
                    hypervisor_type = "KVM / QEMU"
                elif pname in ("vboxheadless", "virtualboxvm"):
                    hypervisor_type = "VirtualBox"
                elif pname in ("vmware-vmx", "vmware-vmx-debug"):
                    hypervisor_type = "VMware"
                elif pname in ("prl_vm_app",):
                    hypervisor_type = "Parallels"
                elif "virtualization.virtualmachine" in pname or (
                    cmdline and "Virtualization.framework" in " ".join(cmdline)
                ):
                    hypervisor_type = "Apple Virtualization"

                if not hypervisor_type:
                    continue

                rss_bytes = pinfo["memory_info"].rss if pinfo.get("memory_info") else 0
                raw_cpu = float(pinfo.get("cpu_percent") or 0.0)
                uptime_sec = max(0, int(now - (pinfo.get("create_time") or now)))

                if hypervisor_type == "KVM / QEMU":
                    parsed = parse_qemu_cmdline(cmdline, host_logical_cores, rss_bytes)
                    vm_name = parsed["name"]
                    vcpus = parsed["vcpus"]
                    alloc_mem = parsed["allocated_memory"]
                    vm_id = parsed["vm_id"] or str(pinfo["pid"])
                else:
                    # Extract name from cmdline or process name
                    vm_name = f"{hypervisor_type}-{pinfo['pid']}"
                    for idx, arg in enumerate(cmdline):
                        if arg in ("--comment", "-s", "--startvm") and idx + 1 < len(cmdline):
                            vm_name = cmdline[idx + 1]
                            break
                        elif arg.endswith(".vmx") or arg.endswith(".pvm"):
                            vm_name = os.path.splitext(os.path.basename(arg))[0]
                            break
                    vcpus = max(1, host_logical_cores // 2)
                    alloc_mem = max(rss_bytes, int(rss_bytes * 1.25))
                    vm_id = str(pinfo["pid"])

                # Merge if already in vms_by_name from virsh/qm
                existing = vms_by_name.get(vm_name)
                if existing:
                    if existing["vcpus"] <= 1 and vcpus > 1:
                        existing["vcpus"] = vcpus
                    if existing["allocated_memory"] <= 0 and alloc_mem > 0:
                        existing["allocated_memory"] = alloc_mem
                    vcpus = existing["vcpus"]
                    alloc_mem = existing["allocated_memory"]
                    hypervisor_type = existing["hypervisor"]
                    vm_id = existing["id"] if existing["id"] != "-" else vm_id

                # Normalize CPU %:
                # psutil process cpu_percent can reach (vcpus * 100)% on multi-core workloads
                cpu_vm_pct = min(100.0, round(raw_cpu / max(1, vcpus), 1))
                cpu_host_pct = min(100.0, round(raw_cpu / max(1, host_logical_cores), 1))
                mem_vm_pct = (
                    min(100.0, round((rss_bytes / alloc_mem) * 100.0, 1))
                    if alloc_mem > 0
                    else 0.0
                )

                vms_by_name[vm_name] = {
                    "id": vm_id,
                    "pid": pinfo["pid"],
                    "name": vm_name,
                    "hypervisor": hypervisor_type,
                    "status": "running",
                    "vcpus": vcpus,
                    "cpu_host_percent": cpu_host_pct,
                    "cpu_vm_percent": cpu_vm_pct,
                    "allocated_memory": alloc_mem,
                    "used_memory": rss_bytes,
                    "memory_vm_percent": mem_vm_pct,
                    "uptime_seconds": uptime_sec,
                }
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        vm_list = sorted(
            vms_by_name.values(),
            key=lambda x: (0 if x["status"] == "running" else 1, -x["cpu_vm_percent"], x["name"]),
        )

        running_vms = [v for v in vm_list if v["status"] == "running"]
        total_alloc_vcpus = sum(v["vcpus"] for v in vm_list)
        active_alloc_vcpus = sum(v["vcpus"] for v in running_vms)
        total_alloc_mem = sum(v["allocated_memory"] for v in vm_list)
        total_used_mem = sum(v["used_memory"] for v in running_vms)
        total_vm_host_cpu = round(sum(v["cpu_host_percent"] for v in running_vms), 1)

        return {
            "summary": {
                "total_count": len(vm_list),
                "running_count": len(running_vms),
                "stopped_count": len(vm_list) - len(running_vms),
                "allocated_vcpus": total_alloc_vcpus,
                "active_vcpus": active_alloc_vcpus,
                "host_cores": host_logical_cores,
                "vcpu_allocation_percent": round(
                    (total_alloc_vcpus / max(1, host_logical_cores)) * 100.0, 1
                ),
                "host_cpu_used_percent": min(100.0, total_vm_host_cpu),
                "allocated_memory": total_alloc_mem,
                "used_memory": total_used_mem,
                "host_total_memory": host_total_mem,
                "memory_allocation_percent": round(
                    (total_alloc_mem / max(1, host_total_mem)) * 100.0, 1
                ),
                "memory_used_of_host_percent": round(
                    (total_used_mem / max(1, host_total_mem)) * 100.0, 1
                ),
                "memory_used_of_allocated_percent": (
                    round((total_used_mem / total_alloc_mem) * 100.0, 1)
                    if total_alloc_mem > 0
                    else 0.0
                ),
            },
            "items": vm_list,
        }


class MetricsCollector:
    """Stateful collector that computes delta rates for network, disk I/O, and VMs."""

    def __init__(self) -> None:
        self.last_time = time.time()
        self.last_net = psutil.net_io_counters()
        self.last_disk = psutil.disk_io_counters()
        self.vm_collector = VMCollector()
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
        logical_cores = psutil.cpu_count(logical=True) or 1

        # 2. Memory Metrics (Cross-platform macOS & Linux)
        vm = psutil.virtual_memory()
        swap = psutil.swap_memory()
        mem_used = vm.total - vm.available

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

        # 4. Disk I/O & Partitions
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

        # 7. Virtual Machines (VM) Allocation & Usage
        vms_data = self.vm_collector.collect(
            host_logical_cores=logical_cores, host_total_mem=vm.total
        )

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
                "cores_logical": logical_cores,
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
            "vms": vms_data,
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
    return FileResponse(
        os.path.join(STATIC_DIR, "index.html"),
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@app.get("/install_chrome.sh", response_class=PlainTextResponse)
async def get_install_chrome_script() -> str:
    """One-line script to install & optimize Google Chrome for XRDP/XFCE4 on Ubuntu Server."""
    return """#!/usr/bin/env bash
set -e
echo "========================================================"
echo " 🌐 Installing Google Chrome (Stable) on $(hostname)..."
echo "========================================================"

# 1. Download official Google Chrome .deb package
echo "📥 [1/4] Downloading official Google Chrome (amd64)..."
cd /tmp
curl -fL --progress-bar https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb -o google-chrome-stable_current_amd64.deb

# 2. Install Chrome + CJK fonts (so Chinese/Asian webpages render cleanly without boxes)
echo "📦 [2/4] Installing Google Chrome & CJK Fonts..."
sudo apt-get update -qq
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y \\
  ./google-chrome-stable_current_amd64.deb \\
  fonts-liberation fonts-noto-cjk xdg-utils
rm -f /tmp/google-chrome-stable_current_amd64.deb

# 3. Optimize Chrome Launcher for XRDP Remote Desktop (avoid keyring popup & set default browser)
echo "⚙️  [3/4] Optimizing Chrome for XRDP Remote Desktop..."
mkdir -p "$HOME/Desktop" "$HOME/.local/share/applications" "$HOME/.config/xfce4"

if [ -f /usr/share/applications/google-chrome.desktop ]; then
  sed 's|/usr/bin/google-chrome-stable|/usr/bin/google-chrome-stable --password-store=basic|g' \\
    /usr/share/applications/google-chrome.desktop > "$HOME/Desktop/google-chrome.desktop"
  cp "$HOME/Desktop/google-chrome.desktop" "$HOME/.local/share/applications/google-chrome.desktop"
  chmod +x "$HOME/Desktop/google-chrome.desktop" "$HOME/.local/share/applications/google-chrome.desktop"
  gio set "$HOME/Desktop/google-chrome.desktop" metadata::trusted true 2>/dev/null || true
fi

# Set Google Chrome as default XFCE4 Web Browser
echo "WebBrowser=google-chrome" > "$HOME/.config/xfce4/helpers.rc"
xdg-settings set default-web-browser google-chrome.desktop 2>/dev/null || true

echo "🚀 [4/4] Verifying installation..."
google-chrome --version

echo ""
echo "========================================================"
echo " ✅ Google Chrome is installed and ready on $(hostname)!"
echo " 🖥️  You can now click 'Google Chrome' directly on your"
echo "    Remote Desktop or Applications -> Internet menu!"
echo "========================================================"
"""


@app.get("/enable_gui.sh", response_class=PlainTextResponse)
async def get_enable_gui_script() -> str:
    """One-line script to install & enable Remote Desktop (XRDP + XFCE4 GUI) on Ubuntu Server."""
    pubkey = ""
    pubkey_path = os.path.expanduser("~/.ssh/home_ai_lab_ed25519.pub")
    if os.path.exists(pubkey_path):
        try:
            with open(pubkey_path, "r", encoding="utf-8") as f:
                pubkey = f.read().strip()
        except Exception:
            pass

    return f"""#!/usr/bin/env bash
set -e
echo "========================================================"
echo " 🖥️  Enabling Remote Desktop GUI (XRDP + XFCE4) on $(hostname)"
echo "========================================================"

# 1. Authorize SSH key for passwordless maintenance
if [ -n "{pubkey}" ]; then
  chmod 755 "$HOME" 2>/dev/null || true
  mkdir -p "$HOME/.ssh" && chmod 700 "$HOME/.ssh"
  grep -qF "{pubkey}" "$HOME/.ssh/authorized_keys" 2>/dev/null || echo "{pubkey}" >> "$HOME/.ssh/authorized_keys"
  chmod 600 "$HOME/.ssh/authorized_keys"
fi

# 2. Install XRDP & XFCE4 Desktop Environment
echo "📦 [1/4] Installing XFCE4 Desktop & XRDP Server (port 3389)..."
sudo apt-get update -qq
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y \\
  xrdp xfce4 xfce4-goodies xfce4-terminal dbus-x11 xorgxrdp

# 3. Configure XFCE4 session & fix Ubuntu 24.04 DBUS/XDG XRDP session variables
echo "⚙️  [2/4] Configuring XRDP session for user $USER..."
echo "xfce4-session" > "$HOME/.xsession"
chmod +x "$HOME/.xsession"

cat << 'EOF_XRC' > "$HOME/.xsessionrc"
export XDG_SESSION_DESKTOP=xfce
export XDG_DATA_DIRS=/usr/share/xfce4:/usr/local/share:/usr/share:/var/lib/snapd/desktop
export XDG_CONFIG_DIRS=/etc/xdg/xdg-xfce:/etc/xdg
EOF_XRC

sudo adduser xrdp ssl-cert >/dev/null 2>&1 || true

# Ensure /etc/xrdp/startwm.sh clears conflicting systemd user session vars
if ! grep -q "unset DBUS_SESSION_BUS_ADDRESS" /etc/xrdp/startwm.sh 2>/dev/null; then
  sudo sed -i '/^test -x \\/etc\\/X11\\/Xsession/i unset DBUS_SESSION_BUS_ADDRESS\\nunset XDG_RUNTIME_DIR' /etc/xrdp/startwm.sh || true
fi

# 4. Enable & Start XRDP Service + Allow Firewall Port 3389
echo "🚀 [3/4] Starting XRDP service on port 3389..."
sudo systemctl enable xrdp >/dev/null 2>&1 || true
sudo systemctl restart xrdp

if command -v ufw >/dev/null 2>&1 && sudo ufw status | grep -q "Status: active"; then
  sudo ufw allow 3389/tcp >/dev/null 2>&1 || true
fi

# 5. Also update PulseMonitor to latest v{APP_VERSION}
echo "🔄 [4/4] Updating PulseMonitor to v{APP_VERSION}..."
curl -fsSL http://100.120.172.121:8788/deploy.sh | bash

TS_IP=$(tailscale ip -4 2>/dev/null || hostname -I | awk '{{print $1}}')
LAN_IP=$(hostname -I | awk '{{print $1}}')
echo ""
echo "========================================================"
echo " ✅ Remote Desktop GUI (XRDP) is READY on $(hostname)!"
echo " 🖥️  RDP Address (Tailscale): ${{TS_IP}}:3389"
echo " 🖥️  RDP Address (LAN):       ${{LAN_IP}}:3389"
echo " 👤 Username:                 $USER"
echo "========================================================"
"""


@app.get("/deploy.sh", response_class=PlainTextResponse)
async def get_deploy_script() -> str:
    """One-line remote deployment script served over LAN / Tailscale."""
    pubkey = ""
    pubkey_path = os.path.expanduser("~/.ssh/home_ai_lab_ed25519.pub")
    if os.path.exists(pubkey_path):
        try:
            with open(pubkey_path, "r", encoding="utf-8") as f:
                pubkey = f.read().strip()
        except Exception:
            pass

    return f"""#!/usr/bin/env bash
set -e
echo "========================================================"
echo " 🚀 Deploying PulseMonitor v{APP_VERSION} to $(hostname)..."
echo "========================================================"

# 1. Authorize SSH key for passwordless management
if [ -n "{pubkey}" ]; then
  chmod go-w "$HOME" 2>/dev/null || true
  mkdir -p "$HOME/.ssh" && chmod 700 "$HOME/.ssh"
  grep -qF "{pubkey}" "$HOME/.ssh/authorized_keys" 2>/dev/null || echo "{pubkey}" >> "$HOME/.ssh/authorized_keys"
  chmod 600 "$HOME/.ssh/authorized_keys"
fi

# 2. Download portable tarball from Mac host over Tailscale / LAN
WORK_DIR="$HOME/pulsemonitor-app"
mkdir -p "$WORK_DIR"
cd "$WORK_DIR"
curl -fsSL http://100.120.172.121:8788/dist/pulsemonitor-ubuntu-{APP_VERSION}.tar.gz -o pulsemonitor.tar.gz
tar -xzf pulsemonitor.tar.gz --strip-components=1

# 3. Install system-wide if passwordless sudo is available, or start immediately in user space
if sudo -n true 2>/dev/null; then
  sudo bash linux/install_ubuntu.sh
else
  echo "📦 Setting up PulseMonitor v{APP_VERSION} in $WORK_DIR..."
  if ! python3 -m venv .venv 2>/dev/null; then
    if command -v apt-get >/dev/null 2>&1; then
      sudo apt-get update && sudo apt-get install -y python3-venv python3-pip
    elif command -v dnf >/dev/null 2>&1; then
      sudo dnf install -y python3-pip
    elif command -v yum >/dev/null 2>&1; then
      sudo yum install -y python3-pip
    fi
    python3 -m venv .venv
  fi
  .venv/bin/pip install --upgrade pip -q
  .venv/bin/pip install -r requirements.txt -q
  pkill -f "uvicorn app:app" 2>/dev/null || true
  nohup .venv/bin/uvicorn app:app --host 0.0.0.0 --port 8788 > "$WORK_DIR/pulsemonitor.log" 2>&1 &
  sleep 1
  TS_IP=$(tailscale ip -4 2>/dev/null || hostname -I | awk '{{print $1}}')
  echo "========================================================"
  echo " ✅ PulseMonitor v{APP_VERSION} is LIVE on $(hostname)!"
  echo " 🌐 Tailscale / LAN URL: http://${{TS_IP}}:8788"
  echo "========================================================"
fi
"""


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
