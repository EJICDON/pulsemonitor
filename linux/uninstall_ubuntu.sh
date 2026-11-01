#!/usr/bin/env bash
# PulseMonitor - Ubuntu / Debian Uninstaller
set -e

if [ "$(id -u)" -ne 0 ]; then
  echo "⚠️ Please run this uninstaller as root: sudo bash uninstall_ubuntu.sh"
  exit 1
fi

echo "🛑 Stopping and removing PulseMonitor service..."
systemctl stop pulsemonitor 2>/dev/null || true
systemctl disable pulsemonitor 2>/dev/null || true
rm -f /etc/systemd/system/pulsemonitor.service
systemctl daemon-reload

rm -f /usr/local/bin/pulsemonitor
rm -f /usr/share/applications/pulsemonitor.desktop
rm -rf /opt/pulsemonitor

echo "✅ PulseMonitor has been completely uninstalled."
