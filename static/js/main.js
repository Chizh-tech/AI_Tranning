"use strict";

// ── State ──────────────────────────────────────────────────────────────────
let dimCount = 0;
let taChart = null;

// ── Default seed dimensions ────────────────────────────────────────────────
const DEFAULTS = [
  { name: "Shaft OD",    nominal: 20.00, tolerance: 0.05, distribution: "normal",  sigma: 3 },
  { name: "Housing ID",  nominal: 20.10, tolerance: 0.08, distribution: "normal",  sigma: 3 },
  { name: "Spacer",      nominal:  5.00, tolerance: 0.03, distribution: "uniform" },
];

// ── Boot ───────────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("btn-add-dim").addEventListener("click", () => addDimCard());
  document.getElementById("btn-calculate").addEventListener("click", onCalculate);
  document.getElementById("btn-reset").addEventListener("click", onReset);

  DEFAULTS.forEach(addDimCard);
});

// ── Add dimension card ─────────────────────────────────────────────────────
function addDimCard(data = {}) {
  dimCount++;
  const id = dimCount;
  const dist = data.distribution || "normal";
  const showSigma = dist === "normal";

  const card = document.createElement("div");
  card.className = "dim-card";
  card.dataset.id = id;
  card.innerHTML = `
    <div class="dim-card-header">
      <span class="dim-card-title">Dimension ${id}</span>
      <button class="btn-remove" title="Remove">✕</button>
    </div>
    <div class="dim-grid">
      <div class="field full-width">
        <label>Name</label>
        <input type="text" class="d-name" placeholder="e.g. Shaft OD"
               value="${escapeHtml(data.name || "")}" />
      </div>
      <div class="field">
        <label>Nominal value</label>
        <input type="number" class="d-nominal" step="any"
               value="${data.nominal !== undefined ? data.nominal : ""}" />
      </div>
      <div class="field">
        <label>Tolerance (±)</label>
        <input type="number" class="d-tolerance" step="any" min="0.000001"
               value="${data.tolerance !== undefined ? data.tolerance : ""}" />
      </div>
      <div class="field full-width">
        <label>Distribution</label>
        <select class="d-distribution">
          <option value="normal"  ${dist === "normal"  ? "selected" : ""}>Normal</option>
          <option value="uniform" ${dist === "uniform" ? "selected" : ""}>Uniform</option>
        </select>
      </div>
      <div class="field full-width sigma-row ${showSigma ? "" : "hidden"}">
        <label>Process sigma (n&sigma;)</label>
        <input type="number" class="d-sigma" step="0.5" min="1" max="6"
               value="${data.sigma !== undefined ? data.sigma : 3}" />
      </div>
    </div>
  `;

  card.querySelector(".btn-remove").addEventListener("click", () => {
    card.remove();
  });

  card.querySelector(".d-distribution").addEventListener("change", (e) => {
    const sigmaRow = card.querySelector(".sigma-row");
    sigmaRow.classList.toggle("hidden", e.target.value !== "normal");
  });

  document.getElementById("dimensions-list").appendChild(card);
}

// ── Collect form data ──────────────────────────────────────────────────────
function collectDimensions() {
  const cards = document.querySelectorAll(".dim-card");
  const dims = [];
  for (const card of cards) {
    const name = card.querySelector(".d-name").value.trim();
    const nominal = parseFloat(card.querySelector(".d-nominal").value);
    const tolerance = parseFloat(card.querySelector(".d-tolerance").value);
    const distribution = card.querySelector(".d-distribution").value;
    const sigma = parseFloat(card.querySelector(".d-sigma").value);

    if (!name) return { error: "All dimensions must have a name." };
    if (isNaN(tolerance) || tolerance <= 0)
      return { error: `"${name}": tolerance must be a positive number.` };
    if (distribution === "normal" && (isNaN(sigma) || sigma <= 0))
      return { error: `"${name}": sigma must be a positive number.` };

    const dim = { name, tolerance, distribution };
    if (!isNaN(nominal)) dim.nominal = nominal;
    if (distribution === "normal") dim.sigma = sigma;
    dims.push(dim);
  }
  return { dims };
}

// ── Calculate ──────────────────────────────────────────────────────────────
async function onCalculate() {
  hideError();
  const { error, dims } = collectDimensions();
  if (error) { showError(error); return; }
  if (!dims || dims.length === 0) { showError("Add at least one dimension."); return; }

  const resultSigma = parseFloat(document.getElementById("result-sigma").value);

  let resp, json;
  try {
    resp = await fetch("/api/calculate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ dimensions: dims, result_sigma: resultSigma }),
    });
    json = await resp.json();
  } catch (err) {
    showError("Network error: " + err.message);
    return;
  }

  if (!resp.ok || json.error) {
    showError(json.error || "Calculation error.");
    return;
  }

  renderResults(json);
}

// ── Render results ─────────────────────────────────────────────────────────
function renderResults(data) {
  const { worst_case, rss, dimensions, distribution_points } = data;

  // Cards
  document.getElementById("wc-value").textContent = `± ${formatNumber(worst_case.plus)}`;
  document.getElementById("wc-range").textContent =
    `[${formatNumber(worst_case.minus)},  +${formatNumber(worst_case.plus)}]`;

  document.getElementById("rss-value").textContent = `± ${formatNumber(rss.plus)}`;
  document.getElementById("rss-range").textContent =
    `[${formatNumber(rss.minus)},  +${formatNumber(rss.plus)}]`;

  // Contribution table
  const tbody = document.getElementById("contrib-tbody");
  tbody.innerHTML = "";
  dimensions.forEach((d) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${escapeHtml(d.name)}</td>
      <td>± ${formatNumber(d.tolerance)}</td>
      <td>${d.distribution === "normal" ? "Normal" : "Uniform"}</td>
      <td>${formatScientific(d.variance)}</td>
      <td class="pct-bar-cell">
        <div class="pct-bar-wrap">
          <div class="pct-bar">
            <div class="pct-bar-fill" style="width:${d.contribution_pct}%"></div>
          </div>
          <span class="pct-label">${d.contribution_pct.toFixed(1)}%</span>
        </div>
      </td>
    `;
    tbody.appendChild(tr);
  });

  // Chart
  renderChart(distribution_points, worst_case, rss);

  // Show results
  document.getElementById("results-placeholder").classList.add("hidden");
  document.getElementById("results-content").classList.remove("hidden");
}

// ── Chart ──────────────────────────────────────────────────────────────────
function renderChart(pts, wc, rss) {
  const ctx = document.getElementById("ta-chart").getContext("2d");

  if (taChart) { taChart.destroy(); }

  taChart = new Chart(ctx, {
    type: "line",
    data: {
      labels: pts.x,
      datasets: [
        {
          label: "RSS (Normal combined)",
          data: pts.rss,
          borderColor: "#4f6ef7",
          backgroundColor: "rgba(79,110,247,.12)",
          borderWidth: 2,
          pointRadius: 0,
          fill: true,
          tension: 0.4,
        },
        {
          label: "Worst Case (Uniform)",
          data: pts.worst_case,
          borderColor: "#f7924f",
          backgroundColor: "rgba(247,146,79,.12)",
          borderWidth: 2,
          pointRadius: 0,
          fill: true,
          tension: 0,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { position: "top" },
        tooltip: {
          callbacks: {
            label: (ctx) =>
              `${ctx.dataset.label}: ${ctx.parsed.y.toExponential(3)}`,
          },
        },
        annotation: buildAnnotations(wc, rss),
      },
      scales: {
        x: {
          type: "linear",
          title: { display: true, text: "Deviation from nominal" },
          ticks: {
            maxTicksLimit: 10,
            callback: (v) => formatNumber(v),
          },
        },
        y: {
          title: { display: true, text: "Probability Density" },
          ticks: {
            callback: (v) => v.toExponential(1),
          },
        },
      },
    },
  });
}

function buildAnnotations(wc, rss) {
  // Chart.js annotations plugin not loaded by default — draw vertical lines
  // via a custom plugin approach (inline dataset instead).
  // We skip the chartjs-plugin-annotation dependency and rely on the curves.
  return {};
}

// ── Reset ──────────────────────────────────────────────────────────────────
function onReset() {
  document.getElementById("dimensions-list").innerHTML = "";
  dimCount = 0;
  hideError();
  document.getElementById("results-placeholder").classList.remove("hidden");
  document.getElementById("results-content").classList.add("hidden");
  if (taChart) { taChart.destroy(); taChart = null; }
  DEFAULTS.forEach(addDimCard);
}

// ── Helpers ────────────────────────────────────────────────────────────────
function formatNumber(v)    { return parseFloat(v).toPrecision(6).replace(/\.?0+$/, ""); }
function formatScientific(v) { return parseFloat(v).toExponential(3); }

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function showError(msg) {
  const el = document.getElementById("error-msg");
  el.textContent = msg;
  el.classList.remove("hidden");
}

function hideError() {
  document.getElementById("error-msg").classList.add("hidden");
}
