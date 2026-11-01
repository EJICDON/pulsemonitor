#!/usr/bin/env bash
# PulseMonitor - Ubuntu / Debian Home Lab Server One-Step Installer
set -e

if [ "$(id -u)" -ne 0 ]; then
  echo "⚠️ Please run this installer as root: sudo bash install_ubuntu.sh"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -f "${SCRIPT_DIR}/../app.py" ]; then
  SRC_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
elif [ -f "${SCRIPT_DIR}/app.py" ]; then
  SRC_DIR="${SCRIPT_DIR}"
else
  echo "❌ Error: app.py not found. Please run from the extracted package directory."
  exit 1
fi

INSTALL_DIR="/opt/pulsemonitor"
PORT="${PORT:-8788}"
VERSION="$(cat "${SRC_DIR}/VERSION" 2>/dev/null || echo '1.1.0')"

echo "========================================================"
echo " 🚀 Installing PulseMonitor v${VERSION} (Ubuntu / Linux)"
echo "========================================================"

# 1. Check and install system dependencies (python3, python3-venv)
if command -v apt-get >/dev/null 2>&1; then
  echo "📦 [1/5] Checking Ubuntu / Debian Python3 dependencies..."
  apt-get update -qq
  apt-get install -y -qq python3 python3-venv python3-pip curl lsof
fi

# 2. Deploy application files to /opt/pulsemonitor
echo "📂 [2/5] Deploying application files to ${INSTALL_DIR}..."
mkdir -p "${INSTALL_DIR}/static"
cp "${SRC_DIR}/app.py" "${INSTALL_DIR}/app.py"
cp "${SRC_DIR}/VERSION" "${INSTALL_DIR}/VERSION"
cp "${SRC_DIR}/requirements.txt" "${INSTALL_DIR}/requirements.txt"
cp "${SRC_DIR}/run.sh" "${INSTALL_DIR}/run.sh"
cp -R "${SRC_DIR}/static/"* "${INSTALL_DIR}/static/"
chmod +x "${INSTALL_DIR}/run.sh"

# 3. Create Python virtual environment and install dependencies
echo "🐍 [3/5] Setting up Python virtualenv & dependencies (fastapi, uvicorn, psutil)..."
if [ ! -d "${INSTALL_DIR}/.venv" ]; then
  python3 -m venv "${INSTALL_DIR}/.venv"
fi
"${INSTALL_DIR}/.venv/bin/pip" install --upgrade pip -q
"${INSTALL_DIR}/.venv/bin/pip" install -r "${INSTALL_DIR}/requirements.txt" -q

# 4. Install CLI utility (/usr/local/bin/pulsemonitor)
echo "🛠️ [4/5] Installing 'pulsemonitor' CLI command..."
cat << 'EOF' > /usr/local/bin/pulsemonitor
#!/usr/bin/env bash
set -e
CMD="${1:-status}"
PORT=$(grep -oP '(?<=--port )\d+' /etc/systemd/system/pulsemonitor.service 2>/dev/null || echo "8788")
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
EOF
chmod +x /usr/local/bin/pulsemonitor

# 5. Configure systemd service
echo "⚙️ [5/5] Configuring systemd service (pulsemonitor.service)..."
cat << EOF > /etc/systemd/system/pulsemonitor.service
[Unit]
Description=PulseMonitor Real-Time Local & Home Lab System Monitor Dashboard
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=${INSTALL_DIR}
Environment="HOST=0.0.0.0"
Environment="PORT=${PORT}"
ExecStart=${INSTALL_DIR}/.venv/bin/uvicorn app:app --host 0.0.0.0 --port ${PORT}
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

# Desktop launcher if GUI is installed
if [ -d /usr/share/applications ]; then
  cat << EOF > /usr/share/applications/pulsemonitor.desktop
[Desktop Entry]
Name=PulseMonitor Dashboard
Comment=Open PulseMonitor Home Lab System Monitor
Exec=xdg-open http://127.0.0.1:${PORT}
Icon=utilities-system-monitor
Terminal=false
Type=Application
Categories=System;Monitor;
EOF
fi

systemctl daemon-reload
systemctl enable pulsemonitor >/dev/null
systemctl restart pulsemonitor

LAN_IP=$(hostname -I 2>/dev/null | awk '{print $1}')
[ -z "$LAN_IP" ] && LAN_IP="127.0.0.1"

echo ""
echo "========================================================"
echo " ✅ PulseMonitor v${VERSION} installed and enabled on boot!"
echo " 🌐 LAN Dashboard URL:   http://${LAN_IP}:${PORT}"
echo " 💻 Local Dashboard URL: http://127.0.0.1:${PORT}"
echo "--------------------------------------------------------"
echo " Useful CLI commands:"
echo "   pulsemonitor status   # Show service status & URL"
echo "   pulsemonitor logs     # Tail live service logs"
echo "   pulsemonitor restart  # Restart service"
echo "   pulsemonitor stop     # Stop service"
echo "   pulsemonitor version  # Print installed version"
echo "========================================================"
