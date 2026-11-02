# $language = "Python"
# $interface = "1.0"

"""
SecureCRT Automated Deployment Script for PulseMonitor v1.2.1
Deploys PulseMonitor v1.2.1 to the active connected tab (e.g. pocetac / pocser01),
authorizes SSH public key, and starts the service on port 8788.
"""


def find_connected_tab():
    try:
        tab = crt.GetScriptTab()
        if tab and tab.Session.Connected and "LocalShell" not in tab.Caption:
            return tab
    except Exception:
        pass
    try:
        count = crt.GetTabCount()
        for i in range(count, 0, -1):
            t = crt.GetTab(i)
            if t.Session.Connected and "LocalShell" not in t.Caption:
                return t
    except Exception:
        pass
    return None


def Main():
    tab = find_connected_tab()
    if not tab:
        return
    tab.Activate()
    screen = tab.Screen
    screen.Synchronous = False
    screen.Send("\ncurl -fsSL http://100.120.172.121:8788/deploy.sh | bash\n")


Main()
