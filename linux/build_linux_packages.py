#!/usr/bin/env python3
"""
Builds two ready-to-deploy Linux / Ubuntu Home Lab artifacts in dist/:
1. dist/pulsemonitor_<version>_all.deb       (Native Ubuntu/Debian apt/dpkg installer)
2. dist/pulsemonitor-ubuntu-<version>.tar.gz (Portable tarball with install_ubuntu.sh)
"""

import io
import os
import tarfile
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST_DIR = os.path.join(BASE_DIR, "dist")


def get_version() -> str:
    ver_file = os.path.join(BASE_DIR, "VERSION")
    if os.path.exists(ver_file):
        with open(ver_file, "r", encoding="utf-8") as f:
            v = f.read().strip()
            if v:
                return v
    return "1.1.0"


VERSION = get_version()


def make_tar_gz_bytes(files_dict):
    """
    Create a deterministic gzipped tar archive in memory with root:root ownership.
    files_dict maps arcname -> (bytes_content, mode_int)
    """
    buf = io.BytesIO()
    now = int(time.time())
    with tarfile.open(fileobj=buf, mode="w:gz", format=tarfile.GNU_FORMAT) as tf:
        dirs = set()
        for path in files_dict:
            parts = path.strip("./").split("/")
            for i in range(1, len(parts)):
                dirs.add("./" + "/".join(parts[:i]))

        for d in sorted(dirs):
            ti = tarfile.TarInfo(name=d)
            ti.type = tarfile.DIRTYPE
            ti.mode = 0o755
            ti.uid = 0
            ti.gid = 0
            ti.uname = "root"
            ti.gname = "root"
            ti.mtime = now
            tf.addfile(ti)

        for arcname, (data, mode) in sorted(files_dict.items()):
            ti = tarfile.TarInfo(name=arcname)
            ti.size = len(data)
            ti.mode = mode
            ti.uid = 0
            ti.gid = 0
            ti.uname = "root"
            ti.gname = "root"
            ti.mtime = now
            tf.addfile(ti, io.BytesIO(data))
    return buf.getvalue()


def make_ar_archive(entries):
    """
    Build a standard Unix `ar` archive (used by Debian .deb format).
    entries: list of (filename, bytes_data)
    """
    out = bytearray(b"!<arch>\n")
    now = int(time.time())
    for name, data in entries:
        header = (
            f"{name:<16}"
            f"{now:<12}"
            f"{0:<6}"
            f"{0:<6}"
            f"{100644:<8}"
            f"{len(data):<10}"
            f"`\n"
        ).encode("ascii")
        out.extend(header)
        out.extend(data)
        if len(data) % 2 == 1:
            out.extend(b"\n")
    return bytes(out)


def build_deb_package():
    os.makedirs(DIST_DIR, exist_ok=True)
    deb_path = os.path.join(DIST_DIR, f"pulsemonitor_{VERSION}_all.deb")

    # 1. Collect application files into /opt/pulsemonitor
    data_files = {}
    core_files = [
        ("VERSION", 0o644),
        ("app.py", 0o644),
        ("requirements.txt", 0o644),
        ("run.sh", 0o755),
        ("static/index.html", 0o644),
        ("static/style.css", 0o644),
        ("static/app.js", 0o644),
    ]
    for rel_path, mode in core_files:
        full_p = os.path.join(BASE_DIR, rel_path)
        with open(full_p, "rb") as f:
            data_files[f"./opt/pulsemonitor/{rel_path}"] = (f.read(), mode)

    # systemd unit file
    systemd_unit = """[Unit]
Description=PulseMonitor Real-Time Local & Home Lab System Monitor Dashboard
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/pulsemonitor
Environment="HOST=0.0.0.0"
Environment="PORT=8788"
ExecStart=/opt/pulsemonitor/.venv/bin/uvicorn app:app --host 0.0.0.0 --port 8788
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
""".encode("utf-8")
    data_files["./lib/systemd/system/pulsemonitor.service"] = (systemd_unit, 0o644)

    # CLI utility /usr/local/bin/pulsemonitor
    cli_script = """#!/usr/bin/env bash
set -e
CMD="${1:-status}"
PORT=8788
VER=$(cat /opt/pulsemonitor/VERSION 2>/dev/null || echo "1.1.0")
LAN_IP=$(hostname -I 2>/dev/null | awk '{print $1}')
[ -z "$LAN_IP" ] && LAN_IP="127.0.0.1"

case "$CMD" in
  start)
    sudo systemctl start pulsemonitor
    echo "✅ PulseMonitor v${VER} started: http://${LAN_IP}:${PORT}"
    ;;
  stop)
    sudo systemctl stop pulsemonitor
    echo "⏹️ PulseMonitor stopped."
    ;;
  restart)
    sudo systemctl restart pulsemonitor
    echo "🔄 PulseMonitor v${VER} restarted: http://${LAN_IP}:${PORT}"
    ;;
  status)
    echo "📊 PulseMonitor v${VER} | Dashboard URL: http://${LAN_IP}:${PORT}"
    systemctl status pulsemonitor --no-pager
    ;;
  logs)
    journalctl -u pulsemonitor -f -n 50
    ;;
  version|-v|--version)
    echo "PulseMonitor v${VER}"
    ;;
  open|url)
    echo "🌐 LAN URL: http://${LAN_IP}:${PORT}"
    if command -v xdg-open >/dev/null 2>&1 && [ -n "$DISPLAY" ]; then
      xdg-open "http://127.0.0.1:${PORT}" >/dev/null 2>&1 &
    fi
    ;;
  *)
    echo "Usage: pulsemonitor {status|start|stop|restart|logs|url|version}"
    exit 1
    ;;
esac
""".encode("utf-8")
    data_files["./usr/local/bin/pulsemonitor"] = (cli_script, 0o755)

    # Desktop shortcut
    desktop_entry = """[Desktop Entry]
Name=PulseMonitor Dashboard
Comment=Open PulseMonitor Home Lab System Monitor
Exec=xdg-open http://127.0.0.1:8788
Icon=utilities-system-monitor
Terminal=false
Type=Application
Categories=System;Monitor;
""".encode("utf-8")
    data_files["./usr/share/applications/pulsemonitor.desktop"] = (desktop_entry, 0o644)

    data_tar_gz = make_tar_gz_bytes(data_files)

    # 2. Control files (control, postinst, prerm)
    control_text = f"""Package: pulsemonitor
Version: {VERSION}
Section: utils
Priority: optional
Architecture: all
Depends: python3, python3-venv, python3-pip
Maintainer: HomeLab Admin <admin@homelab.local>
Description: PulseMonitor Real-Time Local & Home Lab System Monitor Dashboard
 Lightweight real-time WebSocket hardware and process monitoring dashboard
 built with FastAPI, psutil, and Chart.js for Ubuntu/Linux Home Lab servers.
""".encode("utf-8")

    postinst_text = f"""#!/bin/sh
set -e
if [ "$1" = "configure" ]; then
    echo "🐍 [PulseMonitor v{VERSION}] Configuring Python virtualenv (/opt/pulsemonitor/.venv)..."
    if [ ! -d /opt/pulsemonitor/.venv ]; then
        python3 -m venv /opt/pulsemonitor/.venv
    fi
    /opt/pulsemonitor/.venv/bin/pip install --upgrade pip -q
    /opt/pulsemonitor/.venv/bin/pip install -r /opt/pulsemonitor/requirements.txt -q
    systemctl daemon-reload || true
    systemctl enable pulsemonitor >/dev/null 2>&1 || true
    systemctl restart pulsemonitor || true
    LAN_IP=$(hostname -I 2>/dev/null | awk '{{print $1}}')
    [ -z "$LAN_IP" ] && LAN_IP="127.0.0.1"
    echo "✅ PulseMonitor v{VERSION} is active! Dashboard URL: http://${{LAN_IP}}:8788"
fi
exit 0
""".encode("utf-8")

    prerm_text = """#!/bin/sh
set -e
if [ "$1" = "remove" ]; then
    systemctl stop pulsemonitor >/dev/null 2>&1 || true
    systemctl disable pulsemonitor >/dev/null 2>&1 || true
    rm -rf /opt/pulsemonitor/.venv
fi
exit 0
""".encode("utf-8")

    control_tar_gz = make_tar_gz_bytes(
        {
            "./control": (control_text, 0o644),
            "./postinst": (postinst_text, 0o755),
            "./prerm": (prerm_text, 0o755),
        }
    )

    deb_bytes = make_ar_archive(
        [
            ("debian-binary", b"2.0\n"),
            ("control.tar.gz", control_tar_gz),
            ("data.tar.gz", data_tar_gz),
        ]
    )

    with open(deb_path, "wb") as f:
        f.write(deb_bytes)
    print(f"✅ Built Debian/Ubuntu package: {deb_path} ({len(deb_bytes)} bytes)")


def build_portable_tarball():
    os.makedirs(DIST_DIR, exist_ok=True)
    tar_path = os.path.join(DIST_DIR, f"pulsemonitor-ubuntu-{VERSION}.tar.gz")
    include_items = [
        "VERSION",
        "app.py",
        "requirements.txt",
        "run.sh",
        "Dockerfile",
        "docker-compose.yml",
        "static/index.html",
        "static/style.css",
        "static/app.js",
        "linux/install_ubuntu.sh",
        "linux/uninstall_ubuntu.sh",
    ]
    with tarfile.open(tar_path, "w:gz") as tf:
        for item in include_items:
            full_p = os.path.join(BASE_DIR, item)
            tf.add(full_p, arcname=f"pulsemonitor/{item}")
    print(f"✅ Built Ubuntu portable tarball: {tar_path}")


if __name__ == "__main__":
    build_deb_package()
    build_portable_tarball()
