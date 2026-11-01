#!/usr/bin/env bash
set -e

PROJECT_DIR="/Users/jichundong/.gemini/antigravity/scratch/sys-monitor-dashboard"
APP_NAME="PulseMonitor"
APP_BUNDLE="${PROJECT_DIR}/${APP_NAME}.app"
CONTENTS_DIR="${APP_BUNDLE}/Contents"
MACOS_DIR="${CONTENTS_DIR}/MacOS"
RESOURCES_DIR="${CONTENTS_DIR}/Resources"

rm -rf "${APP_BUNDLE}"
mkdir -p "${MACOS_DIR}" "${RESOURCES_DIR}"

echo "🔨 正在编译原生 macOS 状态栏 & 任务栏程序..."
swiftc -swift-version 5 -O \
  "${PROJECT_DIR}/macos_app/PulseMonitorApp.swift" \
  -framework Cocoa -framework WebKit \
  -o "${MACOS_DIR}/${APP_NAME}"

# 生成高清脉冲监控图标 (AppIcon.icns)
ICONSET_DIR="${PROJECT_DIR}/macos_app/AppIcon.iconset"
rm -rf "${ICONSET_DIR}"
mkdir -p "${ICONSET_DIR}"

cat << 'EOF' > "${PROJECT_DIR}/macos_app/make_icon.swift"
import Cocoa

let size = NSSize(width: 1024, height: 1024)
let img = NSImage(size: size)
img.lockFocus()

let rect = NSRect(origin: .zero, size: size)
let path = NSBezierPath(roundedRect: rect.insetBy(dx: 60, dy: 60), xRadius: 210, yRadius: 210)

// Background gradient
let grad = NSGradient(colors: [
    NSColor(calibratedRed: 0.05, green: 0.09, blue: 0.18, alpha: 1.0),
    NSColor(calibratedRed: 0.09, green: 0.15, blue: 0.28, alpha: 1.0)
])!
grad.draw(in: path, angle: -45)

// Glowing border
NSColor(calibratedRed: 0.22, green: 0.74, blue: 0.97, alpha: 0.55).setStroke()
path.lineWidth = 16
path.stroke()

// Pulse waveform line
let wave = NSBezierPath()
wave.move(to: NSPoint(x: 170, y: 512))
wave.line(to: NSPoint(x: 340, y: 512))
wave.line(to: NSPoint(x: 430, y: 760))
wave.line(to: NSPoint(x: 560, y: 260))
wave.line(to: NSPoint(x: 660, y: 610))
wave.line(to: NSPoint(x: 730, y: 512))
wave.line(to: NSPoint(x: 854, y: 512))
wave.lineCapStyle = .round
wave.lineJoinStyle = .round

// Outer glow
NSColor(calibratedRed: 0.22, green: 0.74, blue: 0.97, alpha: 0.35).setStroke()
wave.lineWidth = 58
wave.stroke()

// Main line
NSColor(calibratedRed: 0.22, green: 0.74, blue: 0.97, alpha: 1.0).setStroke()
wave.lineWidth = 28
wave.stroke()

img.unlockFocus()

if let tiff = img.tiffRepresentation,
   let rep = NSBitmapImageRep(data: tiff),
   let png = rep.representation(using: .png, properties: [:]) {
    let outURL = URL(fileURLWithPath: CommandLine.arguments[1])
    try! png.write(to: outURL)
}
EOF

BASE_PNG="${PROJECT_DIR}/macos_app/icon_1024.png"
swift "${PROJECT_DIR}/macos_app/make_icon.swift" "${BASE_PNG}"

for s in 16 32 128 256 512; do
  sips -z $s $s "${BASE_PNG}" --out "${ICONSET_DIR}/icon_${s}x${s}.png" >/dev/null
  s2=$((s * 2))
  sips -z $s2 $s2 "${BASE_PNG}" --out "${ICONSET_DIR}/icon_${s}x${s}@2x.png" >/dev/null
done

iconutil -c icns "${ICONSET_DIR}" -o "${RESOURCES_DIR}/AppIcon.icns"
rm -rf "${ICONSET_DIR}" "${BASE_PNG}" "${PROJECT_DIR}/macos_app/make_icon.swift"

cat << 'EOF' > "${CONTENTS_DIR}/Info.plist"
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>PulseMonitor</string>
    <key>CFBundleIdentifier</key>
    <string>local.sysmonitor.pulsemonitor</string>
    <key>CFBundleName</key>
    <string>PulseMonitor</string>
    <key>CFBundleDisplayName</key>
    <string>PulseMonitor</string>
    <key>CFBundleVersion</key>
    <string>1.0.0</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0.0</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleIconFile</key>
    <string>AppIcon</string>
    <key>LSMinimumSystemVersion</key>
    <string>12.0</string>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>NSAppTransportSecurity</key>
    <dict>
        <key>NSAllowsArbitraryLoads</key>
        <true/>
    </dict>
</dict>
</plist>
EOF

codesign --force --deep --sign - "${APP_BUNDLE}"
echo "✅ 编译完成: ${APP_BUNDLE}"
