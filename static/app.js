// PulseMonitor Frontend Controller (English Edition)

const MAX_POINTS = 60;
let isPaused = false;
let ws = null;
let currentInterval = 1.0;

// Helpers for human-readable byte and rate formatting
function formatBytes(bytes, decimals = 1) {
  if (!bytes || bytes <= 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(decimals))} ${sizes[i]}`;
}

function formatRate(bps) {
  return `${formatBytes(bps, 1)}/s`;
}

function formatUptime(seconds) {
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (d > 0) return `${d}d ${h}h ${m}m`;
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

function coreColor(pct) {
  if (pct >= 85) return "#ef4444";
  if (pct >= 60) return "#f59e0b";
  return "#38bdf8";
}

// Chart.js Shared Defaults
Chart.defaults.color = "#64748b";
Chart.defaults.font.family = "-apple-system, BlinkMacSystemFont, 'Inter', sans-serif";
Chart.defaults.font.size = 11;

function createTimeSeriesChart(ctx, datasets, yOptions = {}) {
  return new Chart(ctx, {
    type: "line",
    data: {
      labels: [],
      datasets: datasets,
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 250 },
      interaction: {
        mode: "index",
        intersect: false,
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: "rgba(15, 23, 42, 0.92)",
          titleColor: "#f1f5f9",
          bodyColor: "#cbd5e1",
          borderColor: "rgba(148, 163, 184, 0.2)",
          borderWidth: 1,
          padding: 9,
        },
      },
      scales: {
        x: {
          grid: { color: "rgba(148, 163, 184, 0.06)" },
          ticks: { maxTicksLimit: 8 },
        },
        y: {
          beginAtZero: true,
          grid: { color: "rgba(148, 163, 184, 0.08)" },
          ...yOptions,
        },
      },
    },
  });
}

// Initialize 3 Charts
const cpuMemCtx = document.getElementById("cpuMemChart").getContext("2d");
const cpuMemChart = createTimeSeriesChart(
  cpuMemCtx,
  [
    {
      label: "CPU Usage (%)",
      data: [],
      borderColor: "#38bdf8",
      backgroundColor: "rgba(56, 189, 248, 0.14)",
      borderWidth: 2,
      pointRadius: 0,
      fill: true,
      tension: 0.35,
    },
    {
      label: "Memory Usage (%)",
      data: [],
      borderColor: "#a855f7",
      backgroundColor: "rgba(168, 85, 247, 0.10)",
      borderWidth: 2,
      pointRadius: 0,
      fill: true,
      tension: 0.35,
    },
  ],
  {
    max: 100,
    ticks: { callback: (v) => `${v}%` },
  }
);

const netCtx = document.getElementById("netChart").getContext("2d");
const netChart = createTimeSeriesChart(
  netCtx,
  [
    {
      label: "Download (KB/s)",
      data: [],
      borderColor: "#10b981",
      backgroundColor: "rgba(16, 185, 129, 0.14)",
      borderWidth: 2,
      pointRadius: 0,
      fill: true,
      tension: 0.35,
    },
    {
      label: "Upload (KB/s)",
      data: [],
      borderColor: "#6366f1",
      backgroundColor: "rgba(99, 102, 241, 0.12)",
      borderWidth: 2,
      pointRadius: 0,
      fill: true,
      tension: 0.35,
    },
  ],
  {
    suggestedMax: 64,
    ticks: {
      callback: (v) => (v >= 1024 ? `${(v / 1024).toFixed(1)} MB/s` : `${v} KB/s`),
    },
  }
);

const diskCtx = document.getElementById("diskChart").getContext("2d");
const diskChart = createTimeSeriesChart(
  diskCtx,
  [
    {
      label: "Read (KB/s)",
      data: [],
      borderColor: "#38bdf8",
      backgroundColor: "rgba(56, 189, 248, 0.12)",
      borderWidth: 1.8,
      pointRadius: 0,
      fill: true,
      tension: 0.35,
    },
    {
      label: "Write (KB/s)",
      data: [],
      borderColor: "#f59e0b",
      backgroundColor: "rgba(245, 158, 11, 0.12)",
      borderWidth: 1.8,
      pointRadius: 0,
      fill: true,
      tension: 0.35,
    },
  ],
  {
    suggestedMax: 128,
    ticks: {
      maxTicksLimit: 5,
      callback: (v) => (v >= 1024 ? `${(v / 1024).toFixed(1)} MB/s` : `${v} KB/s`),
    },
  }
);

function pushChartPoint(snap) {
  const ts = snap.timestamp;

  // CPU & Mem
  cpuMemChart.data.labels.push(ts);
  cpuMemChart.data.datasets[0].data.push(snap.cpu.total);
  cpuMemChart.data.datasets[1].data.push(snap.memory.percent);
  if (cpuMemChart.data.labels.length > MAX_POINTS) {
    cpuMemChart.data.labels.shift();
    cpuMemChart.data.datasets[0].data.shift();
    cpuMemChart.data.datasets[1].data.shift();
  }
  cpuMemChart.update("none");

  // Network (KB/s)
  const downKB = +(snap.network.down_bps / 1024).toFixed(1);
  const upKB = +(snap.network.up_bps / 1024).toFixed(1);
  netChart.data.labels.push(ts);
  netChart.data.datasets[0].data.push(downKB);
  netChart.data.datasets[1].data.push(upKB);
  if (netChart.data.labels.length > MAX_POINTS) {
    netChart.data.labels.shift();
    netChart.data.datasets[0].data.shift();
    netChart.data.datasets[1].data.shift();
  }
  netChart.update("none");

  // Disk I/O (KB/s)
  const readKB = +(snap.disk.read_bps / 1024).toFixed(1);
  const writeKB = +(snap.disk.write_bps / 1024).toFixed(1);
  diskChart.data.labels.push(ts);
  diskChart.data.datasets[0].data.push(readKB);
  diskChart.data.datasets[1].data.push(writeKB);
  if (diskChart.data.labels.length > MAX_POINTS) {
    diskChart.data.labels.shift();
    diskChart.data.datasets[0].data.shift();
    diskChart.data.datasets[1].data.shift();
  }
  diskChart.update("none");
}

function renderSnapshot(snap, updateCharts = true) {
  if (!snap) return;

  // 1. Header & System Summary
  const sys = snap.system;
  if (sys.version) {
    document.getElementById("app-version-badge").textContent = `v${sys.version}`;
  }
  document.getElementById("sys-summary-text").textContent =
    `${sys.hostname} · ${sys.os} · ${sys.cpu_brand}`;
  document.getElementById("uptime-val").textContent = formatUptime(sys.uptime_seconds);
  document.getElementById("load-val").textContent = snap.cpu.load_avg.join(" / ");

  const batChip = document.getElementById("battery-chip");
  const batVal = document.getElementById("battery-val");
  const tempPrefix = snap.cpu.temp_c ? `🌡️ ${snap.cpu.temp_c}°C · ` : "";
  if (snap.battery) {
    batChip.style.display = "flex";
    const plugStr = snap.battery.power_plugged ? "⚡ AC / Charging" : "🔋 On Battery";
    batVal.textContent = `${tempPrefix}${snap.battery.percent}% (${plugStr})`;
  } else {
    batVal.textContent = `${tempPrefix}AC Power (Server)`;
  }

  // 2. CPU KPI & Per-Core Grid
  const cpu = snap.cpu;
  document.getElementById("kpi-cpu").textContent = `${cpu.total.toFixed(1)}%`;
  document.getElementById("kpi-cpu-cores").textContent =
    `${cpu.cores_physical}P / ${cpu.cores_logical}L Cores`;
  document.getElementById("bar-cpu").style.width = `${Math.min(100, cpu.total)}%`;
  document.getElementById("cpu-user-sys").textContent =
    `User ${cpu.user}% · Sys ${cpu.system}%`;
  document.getElementById("cpu-idle").textContent = `Idle ${cpu.idle}%`;
  document.getElementById("proc-count-badge").textContent =
    `${sys.process_count} Processes`;

  const coresGrid = document.getElementById("cores-grid");
  if (coresGrid.children.length !== cpu.per_core.length) {
    coresGrid.innerHTML = cpu.per_core
      .map(
        (pct, idx) => `
      <div class="core-item">
        <div class="core-top">
          <span class="core-name">Core #${idx + 1}</span>
          <span class="core-val" id="core-val-${idx}">${pct.toFixed(0)}%</span>
        </div>
        <div class="core-bar-bg">
          <div class="core-bar-fill" id="core-bar-${idx}" style="width: ${pct}%; background-color: ${coreColor(pct)}"></div>
        </div>
      </div>
    `
      )
      .join("");
  } else {
    cpu.per_core.forEach((pct, idx) => {
      const valEl = document.getElementById(`core-val-${idx}`);
      const barEl = document.getElementById(`core-bar-${idx}`);
      if (valEl) valEl.textContent = `${pct.toFixed(0)}%`;
      if (barEl) {
        barEl.style.width = `${Math.min(100, pct)}%`;
        barEl.style.backgroundColor = coreColor(pct);
      }
    });
  }

  // 3. Memory KPI & Breakdown
  const mem = snap.memory;
  document.getElementById("kpi-mem").textContent = `${mem.percent.toFixed(1)}%`;
  document.getElementById("kpi-mem-detail").textContent =
    `${formatBytes(mem.used, 1)} / ${formatBytes(mem.total, 0)}`;
  document.getElementById("bar-mem").style.width = `${Math.min(100, mem.percent)}%`;
  document.getElementById("mem-avail").textContent =
    `Available: ${formatBytes(mem.available, 1)}`;
  document.getElementById("swap-info").textContent =
    `Swap: ${mem.swap_percent}% (${formatBytes(mem.swap_used, 1)})`;

  const totalMem = mem.total || 1;
  const wiredPct = ((mem.wired || 0) / totalMem) * 100;
  const activePct = ((mem.active || 0) / totalMem) * 100;
  const inactivePct = ((mem.inactive || 0) / totalMem) * 100;

  document.getElementById("seg-wired").style.width = `${wiredPct.toFixed(1)}%`;
  document.getElementById("seg-active").style.width = `${activePct.toFixed(1)}%`;
  document.getElementById("seg-inactive").style.width = `${inactivePct.toFixed(1)}%`;

  document.getElementById("val-wired").textContent = formatBytes(mem.wired, 1);
  document.getElementById("val-active").textContent = formatBytes(mem.active, 1);
  document.getElementById("val-inactive").textContent = formatBytes(mem.inactive, 1);
  document.getElementById("val-avail").textContent = formatBytes(mem.available, 1);

  // 4. Disk KPI & Partitions
  const disk = snap.disk;
  const totalDiskRate = disk.read_bps + disk.write_bps;
  document.getElementById("kpi-disk-io").textContent = formatRate(totalDiskRate);
  document.getElementById("disk-rw-rate").textContent =
    `Read ${formatRate(disk.read_bps)} · Write ${formatRate(disk.write_bps)}`;
  document.getElementById("disk-iops").textContent =
    `${Math.round(disk.read_iops + disk.write_iops)} IOPS`;

  const rootPart = disk.partitions.find((p) => p.mountpoint === "/") || disk.partitions[0];
  if (rootPart) {
    document.getElementById("kpi-disk-root").textContent =
      `Root ${rootPart.percent}%`;
    document.getElementById("bar-disk").style.width = `${Math.min(100, rootPart.percent)}%`;
  }

  const partList = document.getElementById("partitions-list");
  partList.innerHTML = disk.partitions
    .map(
      (p) => `
    <div class="part-item">
      <div class="part-row">
        <span class="part-mount">${p.mountpoint} <small style="color:#64748b;font-weight:400">(${p.fstype})</small></span>
        <span class="part-meta">${formatBytes(p.used, 1)} / ${formatBytes(p.total, 1)} (${p.percent}%) · Free ${formatBytes(p.free, 1)}</span>
      </div>
      <div class="progress-track">
        <div class="progress-fill fill-disk" style="width: ${Math.min(100, p.percent)}%"></div>
      </div>
    </div>
  `
    )
    .join("");

  // 5. Network KPI & Interfaces
  const net = snap.network;
  document.getElementById("kpi-net-down").textContent = `↓ ${formatRate(net.down_bps)}`;
  document.getElementById("kpi-net-up").textContent = `↑ ${formatRate(net.up_bps)}`;
  document.getElementById("net-total-down").textContent =
    `Total RX: ${formatBytes(net.total_recv, 2)}`;
  document.getElementById("net-total-up").textContent =
    `Total TX: ${formatBytes(net.total_sent, 2)}`;

  const ifaceFoot = document.getElementById("net-ifaces-foot");
  const primaryIface =
    net.interfaces.find((i) => i.name !== "lo" && i.name !== "lo0") || net.interfaces[0];
  if (primaryIface) {
    ifaceFoot.innerHTML = `<span>NIC: ${primaryIface.name} (${primaryIface.ip})</span><span>Packets: ${(net.packets_recv + net.packets_sent).toLocaleString()}</span>`;
  }

  const ifaceList = document.getElementById("iface-list");
  ifaceList.innerHTML = net.interfaces
    .map(
      (iface) => `
    <div class="iface-pill">
      <span class="iface-name">${iface.name}</span>
      <span class="iface-ip">${iface.ip}</span>
    </div>
  `
    )
    .join("");

  // 6. Top Active Processes
  const tbody = document.getElementById("proc-tbody");
  tbody.innerHTML = (snap.top_processes || [])
    .map(
      (p) => `
    <tr>
      <td class="proc-pid">${p.pid}</td>
      <td class="proc-name" title="${p.name}">${p.name}</td>
      <td class="proc-user">${p.user}</td>
      <td class="num-col ${p.cpu >= 25 ? "cpu-hot" : ""}">${p.cpu.toFixed(1)}%</td>
      <td class="num-col">${p.mem.toFixed(2)}%</td>
    </tr>
  `
    )
    .join("");

  if (updateCharts && !isPaused) {
    pushChartPoint(snap);
  }
}

// Initial History Load & WebSocket Streaming
async function initDashboard() {
  try {
    const res = await fetch("/api/history");
    const data = await res.json();
    const history = (data.history || []).slice(-MAX_POINTS);
    history.forEach((snap) => {
      pushChartPoint(snap);
    });
    if (data.latest) {
      renderSnapshot(data.latest, false);
    }
  } catch (err) {
    console.warn("History preload failed:", err);
  }

  connectWebSocket();
}

function connectWebSocket() {
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  const wsUrl = `${proto}://${window.location.host}/ws/metrics`;
  ws = new WebSocket(wsUrl);

  const statusDot = document.getElementById("ws-status-dot");
  const statusText = document.getElementById("ws-status-text");

  ws.onopen = () => {
    statusDot.classList.remove("offline");
    statusText.textContent = isPaused ? "Paused" : "Live";
    ws.send(JSON.stringify({ interval: currentInterval }));
  };

  ws.onmessage = (event) => {
    try {
      const snap = JSON.parse(event.data);
      renderSnapshot(snap, true);
    } catch (e) {
      console.error("Failed to parse metrics frame", e);
    }
  };

  ws.onclose = () => {
    statusDot.classList.add("offline");
    statusText.textContent = "Reconnecting...";
    setTimeout(connectWebSocket, 2000);
  };
}

// Controls: Sampling Interval & Pause
document.getElementById("interval-select").addEventListener("change", (e) => {
  currentInterval = parseFloat(e.target.value);
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ interval: currentInterval }));
  }
});

document.getElementById("pause-btn").addEventListener("click", () => {
  isPaused = !isPaused;
  const btn = document.getElementById("pause-btn");
  const btnText = document.getElementById("pause-btn-text");
  const statusDot = document.getElementById("ws-status-dot");
  const statusText = document.getElementById("ws-status-text");

  if (isPaused) {
    btn.classList.add("active");
    btnText.textContent = "Resume";
    statusDot.classList.add("paused");
    statusText.textContent = "Paused";
  } else {
    btn.classList.remove("active");
    btnText.textContent = "Pause";
    statusDot.classList.remove("paused");
    statusText.textContent = "Live";
  }
});

initDashboard();
