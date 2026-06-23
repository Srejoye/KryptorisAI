const API = "http://localhost:5000";

// Reusable Chart.js config generator for real-time line charts
const CHART_OPTS = (label, color) => ({
  type: "line",
  data: {
    labels: [],
    datasets: [{label, data: [], borderColor: color, backgroundColor: color + "18", borderWidth: 1.5, pointRadius: 0, fill: true, tension: 0.4}],
  },
  options: {
    animation: false, responsive: true, maintainAspectRatio: true,
    plugins: { legend: { display: false } },
    scales: {
      x: { display: false },
      y: {
        min: 0,
        ticks: { color: "#4a5568", font: { size: 10, family: "'DM Mono', monospace" } },
        grid:  { color: "rgba(255,255,255,0.20)" },
        border: { color: "rgba(255,255,255,0.16)" },
      },
    },
  },
});

// Chart instances and helper utilities for formatting, classification and chart updates
const rpsChart  = new Chart(document.getElementById("rpsChart"), CHART_OPTS("RPS", "#4f8ef7"));
const riskChart = new Chart(document.getElementById("riskChart"), CHART_OPTS("Risk", "#ff5f57"));
const fmt = (v, d = 3) => (typeof v === "number" ? v.toFixed(d) : v);
const colorForClass = (cls) => ({Normal: "#9BE15D", Suspicious: "#f5a623", Attack: "#ff5f57"}[cls] || "#6b7a8d");

const riskClass = (r) => {
  if (r >= 0.7) return "Attack";
  if (r >= 0.4) return "Suspicious";
  return "Normal";
};

const shortTs = (ts) => {
  if (!ts) return "";
  const date = new Date(ts);
  return isNaN(date) ? ts : date.toLocaleTimeString("en-IN", {timeZone: "Asia/Kolkata", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false});
};

const updateChart = (chart, labels, values, yMax) => {
  chart.data.labels = labels.map(shortTs);
  chart.data.datasets[0].data = values;
  if (yMax !== undefined) {chart.options.scales.y.max = yMax;}
  chart.update("none");
};

// Updates status badge
const setBadge = (cls) => {
  const b = document.getElementById("statusBadge");
  const map = {Normal: ["badge-green", "✅ Normal"], Suspicious: ["badge-yellow", "⚠️ Suspicious"], Attack: ["badge-red", "🚨 Attack Detected"]}
  const [cssClass, text] = map[cls] || ["badge-gray", "⏳ Initializing"];
  b.className = "badge " + cssClass;
  b.textContent = text;
};

// Polls backend state to refresh UI
const pollState = async () => {
  try {
    const res = await fetch(API + "/api/state");
    if (!res.ok) return; // avoid breaking on bad response
    const d = await res.json();
    if (!d?.ready) return;
    const cls = d.class || "Normal";
    const r = d.risk ?? 0;
    const color = colorForClass(cls);
    const riskEl = document.getElementById("riskScore"); riskEl.textContent = fmt(r); riskEl.style.color = color;
    const classEl = document.getElementById("classLabel"); classEl.textContent = cls; classEl.style.color = color;
    document.getElementById("rpsValue").textContent = fmt(d.features?.rps ?? 0, 1);
    document.getElementById("xgbProb").textContent = fmt(d.xgb_prob ?? 0, 4);
    document.getElementById("lstmProb").textContent = fmt(d.lstm_prob ?? 0, 4);
    document.getElementById("anomalyScore").textContent = fmt(d.anomaly_score ?? 0, 4);
    document.getElementById("scenarioLabel").textContent = d.scenario || "Idle";
    setBadge(cls);
    renderFeatures(d.features || {});
    renderShap(d.shap || {});
    appendLog(d);
  } catch (e) {}
};

// Polls time-series data and updates charts
const pollData = async () => {
  try {
    const res = await fetch(API + "/api/data");
    if (!res.ok) return;
    const d = await res.json();
    const labels = d.ts || [];
    const rps = d.rps || [];
    const risk = d.risk || [];
    updateChart(rpsChart, labels, rps);
    updateChart(riskChart, labels, risk, 1);
  } catch (e) {}
};

// Polls alert feed and renders alert items
const pollAlerts = async () => {
  try {
    const res = await fetch(API + "/api/alerts");
    if (!res.ok) return;
    const arr = await res.json();
    const box = document.getElementById("alertLog");
    box.innerHTML = arr.map(a => {const severity = (a.severity || "LOW").toUpperCase();
      return `<div class="alert-item alert-${severity}"> <span class="alert-time">${shortTs(a.timestamp || a.ts || "")}</span>
          <strong>[${severity}]</strong> ${(a.reasons || []).slice(0, 2).join(" · ")} </div>`;}).join("");
  } catch (e) {}
};

// Polls blocked and rate-limited IPs and renders table rows
const pollBlocked = async () => {
  try {
    const res = await fetch(API + "/api/blocked-ips");
    if (!res.ok) return;
    const d = await res.json();
    const tbody = document.querySelector("#ipTable tbody");
    const rows = [];
    for (const [ip, info] of Object.entries(d.blocked || {})) {
      rows.push(`
        <tr>
          <td><code>${ip}</code></td>
          <td><span class="tag-blocked">BLOCKED</span></td>
          <td>${fmt(info.risk ?? 0, 3)}</td>
          <td><button class="btn-unblock" data-ip="${ip}">Unblock</button></td>
        </tr>`);
    }
    for (const [ip, info] of Object.entries(d.rate_limited || {})) {
      rows.push(`
        <tr>
          <td><code>${ip}</code></td>
          <td><span class="tag-limited">RATE-LIMITED</span></td>
          <td>${fmt(info.risk ?? 0, 3)}</td>
          <td><button class="btn-unblock" data-ip="${ip}">Unblock</button></td>
        </tr>`);
    }
    tbody.innerHTML = rows.length ? rows.join("") : `<tr><td colspan="4" class="empty-row">No blocked IPs</td></tr>`;
  } catch (e) {}
};

// Polls pending approvals and renders action table
const pollPending = async () => {
  try {
    const res = await fetch(API + "/api/pending-approvals");
    if (!res.ok) return;
    const data = await res.json();
    const tbody = document.querySelector("#pendingTable tbody");
    if (!data.length) {
      tbody.innerHTML = `<tr><td colspan="4" class="empty-row">No pending approvals</td></tr>`;
      return;
    }
    tbody.innerHTML = data.map(p => {
      const ts = p.timestamp ? p.timestamp.slice(11, 19) : "—";
      return `
        <tr>
          <td><code>${p.ip}</code></td>
          <td class="risk-attack">${fmt(p.risk ?? 0, 3)}</td>
          <td class="log-ts">${ts}</td>
          <td>
            <button class="btn-unblock btn-approve" data-ip="${p.ip}">✔ Block</button>
            <button class="btn-unblock btn-reject" data-ip="${p.ip}">✘ Ignore</button>
          </td>
        </tr>`;
    }).join("");
  } catch (e) {}
};

// Renders feature key-value table
const renderFeatures = (features) => {
  const tbody = document.querySelector("#featureTable tbody");
  tbody.innerHTML = Object.entries(features).map(([k, v]) => `
    <tr>
      <td>${k}</td>
      <td class="feat-val">${typeof v === "number" ? fmt(v, 4) : v}</td>
    </tr>`).join("");
};

// Renders SHAP feature contributions and appends live log entries
const renderShap = (shap) => {
  const sorted = Object.entries(shap).sort((a, b) => Math.abs(b[1]) - Math.abs(a[1])).slice(0, 10);
  const maxAbs = Math.max(...sorted.map(([, v]) => Math.abs(v)), 0.0001);
  const container = document.getElementById("shapBars");
  container.innerHTML = sorted.map(([name, val]) => {
    const pct = Math.round((Math.abs(val) / maxAbs) * 100);
    const cls = val >= 0 ? "shap-pos" : "shap-neg";
    const sign = val >= 0 ? "+" : "";
    return `
      <div class="shap-row">
        <div class="shap-name">${name}</div>
        <div class="shap-track">
          <div class="shap-fill ${cls}" style="width:${pct}%"></div>
        </div>
        <div class="shap-val-label">${sign}${Number(val).toFixed(5)}</div>
      </div>`;}).join("");
};

const logLines = [];
const appendLog = (d) => {
  const cls = d.class || "Normal";
  const line = `
    <div class="log-line">
      <span class="log-ts">${shortTs(d.timestamp)}</span>
      <span class="log-cls-${cls}">[${cls}]</span>
      risk=${fmt(d.risk ?? 0, 4)} rps=${fmt(d.features?.rps ?? 0, 1)} win=#${d.window ?? "-"}
    </div>`;
  logLines.unshift(line);
  if (logLines.length > 50) {logLines.pop();}
  document.getElementById("logFeed").innerHTML = logLines.join("");
};

// Action handlers and main polling loop for syncing dashboard state
const unblock = async (ip) => {
  try {
    const res = await fetch(API + `/api/unblock/${ip}`, { method: "POST" });
    if (!res.ok) return;
    pollBlocked();
  } catch (e) {}
};

const approveBlock = async (ip) => {
  try {
    const res = await fetch(API + `/api/approve-block/${ip}`, { method: "POST" });
    if (!res.ok) return;
    pollBlocked();
    pollPending();
  } catch (e) {}
};

const rejectBlock = async (ip) => {
  try {
    const res = await fetch(API + `/api/reject-block/${ip}`, { method: "POST" });
    if (!res.ok) return;
    pollPending();
  } catch (e) {}
};

document.addEventListener("click", (e) => {
  const ip = e.target.dataset.ip;
  if (!ip) return;
  if (e.target.classList.contains("btn-unblock")) {unblock(ip);}
  if (e.target.classList.contains("btn-approve")) {approveBlock(ip);}
  if (e.target.classList.contains("btn-reject")) {rejectBlock(ip);}
});

// Runs all polling functions in parallel for better performance
const pollAll = async () => {
  await Promise.all([
    pollState(),
    pollData(),
    pollAlerts(),
    pollBlocked(),
    pollPending()
  ]);
};

// Initial load + polling loop
pollAll();
setInterval(pollAll, 1000);