import Cocoa
import WebKit

struct MetricsResponse: Decodable {
    struct CPU: Decodable {
        let total: Double
    }
    struct Memory: Decodable {
        let percent: Double
    }
    struct Network: Decodable {
        let down_bps: Double
        let up_bps: Double
    }
    let cpu: CPU
    let memory: Memory
    let network: Network
}

class AppDelegate: NSObject, NSApplicationDelegate, NSWindowDelegate {
    var statusItem: NSStatusItem!
    var serverProcess: Process?
    var pollTimer: Timer?
    var dashboardWindow: NSWindow?
    var webView: WKWebView?

    let runScriptPath = "/Users/jichundong/.gemini/antigravity/scratch/sys-monitor-dashboard/run.sh"
    let dashboardURL = URL(string: "http://127.0.0.1:8788")!
    let metricsURL = URL(string: "http://127.0.0.1:8788/api/metrics")!

    var isServerOnline = false
    var statusMenuItem: NSMenuItem!
    var statsMenuItem: NSMenuItem!
    var toggleServerMenuItem: NSMenuItem!

    func applicationDidFinishLaunching(_ notification: Notification) {
        setupMainMenu()
        setupStatusBar()
        setupDashboardWindow()

        checkServerAndEnsureRunning(openWindowAfterReady: true)

        pollTimer = Timer.scheduledTimer(
            timeInterval: 2.0,
            target: self,
            selector: #selector(pollMetrics),
            userInfo: nil,
            repeats: true
        )
    }

    func setupMainMenu() {
        let mainMenu = NSMenu()

        let appMenuItem = NSMenuItem()
        mainMenu.addItem(appMenuItem)
        let appMenu = NSMenu()
        appMenu.addItem(
            withTitle: "Show Dashboard Window",
            action: #selector(showDashboardWindow),
            keyEquivalent: "1"
        )
        appMenu.addItem(
            withTitle: "Open in Default Browser",
            action: #selector(openInBrowser),
            keyEquivalent: "o"
        )
        appMenu.addItem(NSMenuItem.separator())
        appMenu.addItem(
            withTitle: "Reload Dashboard",
            action: #selector(reloadWebView),
            keyEquivalent: "r"
        )
        appMenu.addItem(
            withTitle: "Close Window",
            action: #selector(closeCurrentWindow),
            keyEquivalent: "w"
        )
        appMenu.addItem(NSMenuItem.separator())
        appMenu.addItem(
            withTitle: "Quit PulseMonitor",
            action: #selector(quitApp),
            keyEquivalent: "q"
        )
        appMenuItem.submenu = appMenu

        NSApp.mainMenu = mainMenu
    }

    func setupStatusBar() {
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        if let button = statusItem.button {
            button.title = "⚡ Pulse"
            button.font = NSFont.monospacedDigitSystemFont(ofSize: 12, weight: .medium)
        }

        let menu = NSMenu()

        statusMenuItem = NSMenuItem(title: "🟢 Status: Checking...", action: nil, keyEquivalent: "")
        statusMenuItem.isEnabled = false
        menu.addItem(statusMenuItem)

        statsMenuItem = NSMenuItem(title: "CPU: --%  |  RAM: --%", action: nil, keyEquivalent: "")
        statsMenuItem.isEnabled = false
        menu.addItem(statsMenuItem)

        menu.addItem(NSMenuItem.separator())

        let openWinItem = NSMenuItem(
            title: "🪟 Show Dashboard Window",
            action: #selector(showDashboardWindow),
            keyEquivalent: "1"
        )
        openWinItem.target = self
        menu.addItem(openWinItem)

        let openBrowserItem = NSMenuItem(
            title: "🌐 Open in Default Browser",
            action: #selector(openInBrowser),
            keyEquivalent: "o"
        )
        openBrowserItem.target = self
        menu.addItem(openBrowserItem)

        menu.addItem(NSMenuItem.separator())

        toggleServerMenuItem = NSMenuItem(
            title: "🔄 Restart Backend Service (run.sh)",
            action: #selector(restartServer),
            keyEquivalent: "s"
        )
        toggleServerMenuItem.target = self
        menu.addItem(toggleServerMenuItem)

        let stopItem = NSMenuItem(
            title: "⏹️ Stop Backend Service",
            action: #selector(stopServer),
            keyEquivalent: ""
        )
        stopItem.target = self
        menu.addItem(stopItem)

        menu.addItem(NSMenuItem.separator())

        let quitItem = NSMenuItem(
            title: "Quit PulseMonitor",
            action: #selector(quitApp),
            keyEquivalent: "q"
        )
        quitItem.target = self
        menu.addItem(quitItem)

        statusItem.menu = menu
    }

    func setupDashboardWindow() {
        let rect = NSRect(x: 0, y: 0, width: 1280, height: 840)
        let style: NSWindow.StyleMask = [.titled, .closable, .miniaturizable, .resizable]
        let win = NSWindow(contentRect: rect, styleMask: style, backing: .buffered, defer: false)
        win.title = "PulseMonitor · System & Home Lab Dashboard"
        win.center()
        win.isReleasedWhenClosed = false
        win.delegate = self
        win.backgroundColor = NSColor(calibratedRed: 0.035, green: 0.05, blue: 0.086, alpha: 1.0)

        let config = WKWebViewConfiguration()
        let wv = WKWebView(frame: rect, configuration: config)
        wv.autoresizingMask = [.width, .height]
        wv.setValue(false, forKey: "drawsBackground")
        win.contentView = wv

        self.dashboardWindow = win
        self.webView = wv
    }

    func formatRate(_ bps: Double) -> String {
        if bps < 1024 {
            return String(format: "%.0f B/s", bps)
        } else if bps < 1024 * 1024 {
            return String(format: "%.1f KB/s", bps / 1024.0)
        } else {
            return String(format: "%.1f MB/s", bps / (1024.0 * 1024.0))
        }
    }

    func checkServerAndEnsureRunning(openWindowAfterReady: Bool) {
        var req = URLRequest(url: metricsURL)
        req.timeoutInterval = 1.2
        URLSession.shared.dataTask(with: req) { [weak self] data, response, error in
            guard let self = self else { return }
            if let httpResp = response as? HTTPURLResponse, httpResp.statusCode == 200, data != nil {
                DispatchQueue.main.async {
                    self.isServerOnline = true
                    if openWindowAfterReady {
                        self.showDashboardWindow()
                    }
                    self.pollMetrics()
                }
            } else {
                DispatchQueue.main.async {
                    self.startRunShProcess()
                    if openWindowAfterReady {
                        DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) {
                            self.showDashboardWindow()
                        }
                    }
                }
            }
        }.resume()
    }

    func startRunShProcess() {
        if let proc = serverProcess, proc.isRunning {
            return
        }
        let proc = Process()
        proc.executableURL = URL(fileURLWithPath: "/bin/bash")
        proc.arguments = [runScriptPath]
        proc.currentDirectoryURL = URL(fileURLWithPath: "/Users/jichundong/.gemini/antigravity/scratch/sys-monitor-dashboard")
        proc.standardOutput = FileHandle.nullDevice
        proc.standardError = FileHandle.nullDevice
        do {
            try proc.run()
            self.serverProcess = proc
        } catch {
            print("Failed to launch run.sh: \(error)")
        }
    }

    @objc func pollMetrics() {
        var req = URLRequest(url: metricsURL)
        req.timeoutInterval = 1.5
        URLSession.shared.dataTask(with: req) { [weak self] data, response, error in
            guard let self = self else { return }
            guard let data = data,
                  let httpResp = response as? HTTPURLResponse,
                  httpResp.statusCode == 200,
                  let decoded = try? JSONDecoder().decode(MetricsResponse.self, from: data) else {
                DispatchQueue.main.async {
                    self.isServerOnline = false
                    self.statusItem.button?.title = "⚡ Pulse (Offline)"
                    self.statusMenuItem.title = "🔴 Service: Stopped (Click Restart)"
                    self.statsMenuItem.title = "CPU: --%  |  RAM: --%"
                }
                return
            }

            DispatchQueue.main.async {
                self.isServerOnline = true
                let cpuInt = Int(decoded.cpu.total.rounded())
                let memInt = Int(decoded.memory.percent.rounded())
                self.statusItem.button?.title = "⚡ \(cpuInt)% · \(memInt)%"
                self.statusMenuItem.title = "🟢 Service Online (127.0.0.1:8788)"
                let downStr = self.formatRate(decoded.network.down_bps)
                self.statsMenuItem.title = String(
                    format: "CPU: %.1f%%  |  RAM: %.1f%%  |  ↓ %@",
                    decoded.cpu.total,
                    decoded.memory.percent,
                    downStr
                )
            }
        }.resume()
    }

    @objc func showDashboardWindow() {
        if !isServerOnline {
            startRunShProcess()
        }
        guard let win = dashboardWindow, let wv = webView else { return }
        if wv.url == nil {
            wv.load(URLRequest(url: dashboardURL))
        } else {
            wv.reload()
        }
        NSApp.activate(ignoringOtherApps: true)
        win.makeKeyAndOrderFront(nil)
    }

    @objc func reloadWebView() {
        webView?.reload()
    }

    @objc func closeCurrentWindow() {
        dashboardWindow?.orderOut(nil)
    }

    @objc func openInBrowser() {
        if !isServerOnline {
            startRunShProcess()
        }
        NSWorkspace.shared.open(dashboardURL)
    }

    @objc func restartServer() {
        stopServer()
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.6) {
            self.startRunShProcess()
            DispatchQueue.main.asyncAfter(deadline: .now() + 1.2) {
                self.pollMetrics()
                self.webView?.reload()
            }
        }
    }

    @objc func stopServer() {
        if let proc = serverProcess, proc.isRunning {
            proc.terminate()
            serverProcess = nil
        }
        let killProc = Process()
        killProc.executableURL = URL(fileURLWithPath: "/bin/sh")
        killProc.arguments = ["-c", "lsof -ti :8788 | xargs kill -15 2>/dev/null || true"]
        try? killProc.run()
        killProc.waitUntilExit()
        pollMetrics()
    }

    @objc func quitApp() {
        if let proc = serverProcess, proc.isRunning {
            proc.terminate()
        }
        NSApp.terminate(nil)
    }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        showDashboardWindow()
        return true
    }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.regular)
app.run()
