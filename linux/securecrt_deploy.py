# $language = "Python3"
# $interface = "1.0"

"""
SecureCRT Automated Deployment Script for PulseMonitor v1.2.0
Finds the connected remote tab in SecureCRT, deploys PulseMonitor v1.2.0,
starts the service on port 8788, and logs status to /tmp/securecrt_deploy_status.txt.
"""

import base64
import os

TAR_PATH = "/Users/jichundong/.gemini/antigravity/scratch/sys-monitor-dashboard/dist/pulsemonitor-ubuntu-1.2.0.tar.gz"
DEB_PATH = "/Users/jichundong/.gemini/antigravity/scratch/sys-monitor-dashboard/dist/pulsemonitor_1.2.0_all.deb"
PUBKEY_PATH = os.path.expanduser("~/.ssh/home_ai_lab_ed25519.pub")
STATUS_LOG = "/tmp/securecrt_deploy_status.txt"


def log_status(msg):
    with open(STATUS_LOG, "a", encoding="utf-8") as f:
        f.write(msg + "\n")


def find_connected_tab():
    try:
        count = crt.GetTabCount()
        for i in range(1, count + 1):
            t = crt.GetTab(i)
            if t.Session.Connected and "LocalShell" not in t.Caption:
                return t
    except Exception as e:
        log_status(f"Tab scan error: {e}")
    tab = crt.GetScriptTab()
    if tab and tab.Session.Connected:
        return tab
    return None


def Main():
    with open(STATUS_LOG, "w", encoding="utf-8") as f:
        f.write("STARTING_DEPLOY\n")

    tab = find_connected_tab()
    if not tab:
        log_status("ERROR: No connected remote SSH tab found in SecureCRT.")
        return

    tab.Activate()
    log_status(f"CONNECTED_TAB: {tab.Caption}")

    screen = tab.Screen
    screen.Synchronous = True

    # Wake up prompt
    screen.Send("\n")
    crt.Sleep(300)

    # 1. Authorize ~/.ssh/home_ai_lab_ed25519.pub for seamless SSH/SCP access
    if os.path.exists(PUBKEY_PATH):
        with open(PUBKEY_PATH, "r", encoding="utf-8") as pf:
            pubkey = pf.read().strip()
        if pubkey:
            cmd_key = (
                f"mkdir -p ~/.ssh && chmod 700 ~/.ssh && "
                f"(grep -qF '{pubkey}' ~/.ssh/authorized_keys 2>/dev/null || echo '{pubkey}' >> ~/.ssh/authorized_keys) && "
                f"chmod 600 ~/.ssh/authorized_keys\n"
            )
            screen.Send(cmd_key)
            crt.Sleep(500)
            log_status("SSH_PUBKEY_SENT")

    # 2. Upload pulsemonitor-ubuntu-1.2.0.tar.gz via Base64 stream
    if os.path.exists(TAR_PATH):
        with open(TAR_PATH, "rb") as tf:
            b64_tar = base64.b64encode(tf.read()).decode("ascii")

        screen.Send("mkdir -p ~/pulsemonitor-deploy && rm -f ~/pulsemonitor-deploy/pkg.b64\n")
        crt.Sleep(300)

        screen.Send("cat << 'EOF_PM_TAR' > ~/pulsemonitor-deploy/pkg.b64\n")
        chunk_size = 768
        for i in range(0, len(b64_tar), chunk_size):
            screen.Send(b64_tar[i : i + chunk_size] + "\n")
            crt.Sleep(15)
        screen.Send("EOF_PM_TAR\n")
        crt.Sleep(600)

        # Decode, extract, and launch PulseMonitor (tries sudo install_ubuntu.sh if passwordless sudo, plus user-level service on 8788)
        deploy_cmd = (
            "cd ~/pulsemonitor-deploy && "
            "base64 -d pkg.b64 > pulsemonitor-ubuntu-1.2.0.tar.gz && "
            "tar -xzf pulsemonitor-ubuntu-1.2.0.tar.gz && "
            "cd pulsemonitor && "
            "(sudo -n bash linux/install_ubuntu.sh || "
            "(nohup bash run.sh > ~/pulsemonitor-deploy/pulsemonitor.log 2>&1 &)) && "
            "echo 'PULSE_DEPLOY_DONE'\n"
        )
        screen.Send(deploy_cmd)
        log_status("DEPLOY_COMMANDS_SENT")

    screen.Synchronous = False
    log_status("FINISHED_SCRIPT")


Main()
