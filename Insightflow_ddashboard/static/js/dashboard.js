/**
 * dashboard.js
 * InsightFlow sales analytics dashboard client logic.
 */

// Global Chart.js defaults: disable animations for instant updates
if (typeof Chart !== "undefined") {
  Chart.defaults.animation = false;
  Chart.defaults.animations = { colors: false, x: false, y: false };
  Chart.defaults.transitions = { active: { animation: { duration: 0 } } };
  Chart.defaults.font.family = "Inter, sans-serif";
  Chart.defaults.color = "#64748b";
}

const state = {
  region: "all",
  category: "all",
  product: "all",
  startDate: "",
  endDate: ""
};

let trendChart = null;
let regionChart = null;
let productChart = null;
let categoryChart = null;

const fmtINR = (n) => "₹" + Number(n).toLocaleString("en-IN", { maximumFractionDigits: 0 });
const fmtNum = (n) => Number(n).toLocaleString("en-IN");

const emptyState = document.getElementById("emptyState");
const dataView = document.getElementById("dataView");
const loadingOvl = document.getElementById("loadingOverlay");

async function fetchJSON(url, opts = {}) {
  const res = await fetch(url, opts);
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "Server error.");
  return data;
}

function buildQuery(overrides = {}) {
  const p = new URLSearchParams();
  const s = { ...state, ...overrides };
  if (s.region !== "all") p.set("region", s.region);
  if (s.category !== "all") p.set("category", s.category);
  if (s.product !== "all") p.set("product", s.product);
  if (s.startDate) p.set("start_date", s.startDate);
  if (s.endDate) p.set("end_date", s.endDate);
  return p.toString();
}

function showView(hasData) {
  emptyState.classList.toggle("hidden", hasData);
  dataView.classList.toggle("hidden", !hasData);
}

async function uploadFile(file, statusEl) {
  if (!file) return;
  if (statusEl) {
    statusEl.textContent = "Uploading...";
    statusEl.className = "upload-inline";
  }
  const fd = new FormData();
  fd.append("file", file);
  try {
    const data = await fetchJSON("/api/upload", { method: "POST", body: fd });
    if (statusEl) {
      statusEl.textContent = data.message;
      statusEl.classList.add("ok");
    }
    await enterDataView();
  } catch (err) {
    if (statusEl) {
      statusEl.textContent = err.message;
      statusEl.classList.add("err");
    } else {
      showEmptyError(err.message);
    }
  }
}

function showEmptyError(msg) {
  const el = document.getElementById("emptyError");
  el.textContent = msg;
  el.classList.remove("hidden");
}

// Drag-and-drop & file upload
const dropzone = document.getElementById("dropzone");
const fileInput = document.getElementById("fileInput");
dropzone.addEventListener("click", () => fileInput.click());
fileInput.addEventListener("change", () => uploadFile(fileInput.files[0], null));

["dragenter", "dragover"].forEach((evt) =>
  dropzone.addEventListener(evt, (e) => { e.preventDefault(); dropzone.classList.add("drag-over"); })
);
["dragleave", "drop"].forEach((evt) =>
  dropzone.addEventListener(evt, (e) => { e.preventDefault(); dropzone.classList.remove("drag-over"); })
);
dropzone.addEventListener("drop", (e) => {
  const f = e.dataTransfer.files[0];
  if (f) uploadFile(f, null);
});

document.getElementById("sampleBtn").addEventListener("click", async () => {
  try {
    await fetchJSON("/api/load-sample", { method: "POST" });
    await enterDataView();
  } catch (err) {
    showEmptyError(err.message);
  }
});

const fileInputToolbar = document.getElementById("fileInputToolbar");
document.getElementById("addMoreBtn").addEventListener("click", () => fileInputToolbar.click());
fileInputToolbar.addEventListener("change", () =>
  uploadFile(fileInputToolbar.files[0], document.getElementById("uploadStatus"))
);

document.getElementById("resetBtn").addEventListener("click", async () => {
  if (!confirm("Clear all uploaded data? This cannot be undone.")) return;
  await fetchJSON("/api/reset", { method: "POST" });
  showView(false);
  document.getElementById("lastUpdated").textContent = "";
  document.getElementById("periodCompare").classList.add("hidden");
  destroyCharts();
});

// Filters
document.getElementById("regionFilter").addEventListener("change", (e) => { state.region = e.target.value; refreshAll(); });
document.getElementById("categoryFilter").addEventListener("change", (e) => { state.category = e.target.value; refreshAll(); });
document.getElementById("productFilter").addEventListener("change", (e) => { state.product = e.target.value; refreshAll(); });
document.getElementById("startDate").addEventListener("change", (e) => { state.startDate = e.target.value; refreshAll(); });
document.getElementById("endDate").addEventListener("change", (e) => { state.endDate = e.target.value; refreshAll(); });

document.getElementById("clearFiltersBtn").addEventListener("click", () => {
  state.region = "all";
  state.category = "all";
  state.product = "all";
  state.startDate = "";
  state.endDate = "";
  document.getElementById("regionFilter").value = "all";
  document.getElementById("categoryFilter").value = "all";
  document.getElementById("productFilter").value = "all";
  document.getElementById("startDate").value = "";
  document.getElementById("endDate").value = "";
  document.getElementById("periodCompare").classList.add("hidden");
  refreshAll();
});

async function loadFilterOptions() {
  const data = await fetchJSON("/api/filters");
  const regionSel = document.getElementById("regionFilter");
  const catSel = document.getElementById("categoryFilter");
  const productSel = document.getElementById("productFilter");

  regionSel.innerHTML = '<option value="all">All regions</option>'
    + data.regions.map((r) => `<option value="${r}">${r}</option>`).join("");
  catSel.innerHTML = '<option value="all">All categories</option>'
    + data.categories.map((c) => `<option value="${c}">${c}</option>`).join("");
  productSel.innerHTML = '<option value="all">All products</option>'
    + data.products.map((p) => `<option value="${p}">${p}</option>`).join("");

  return data.has_data;
}

async function loadKPIs() {
  const data = await fetchJSON("/api/kpis?" + buildQuery());
  document.getElementById("kpiRevenue").textContent = fmtINR(data.total_revenue || 0);
  document.getElementById("kpiOrders").textContent = fmtNum(data.total_orders || 0);
  document.getElementById("kpiUnits").textContent = fmtNum(data.total_units || 0);
  document.getElementById("kpiAOV").textContent = fmtINR(data.avg_order_value || 0);
}

async function loadPeriodComparison() {
  if (!state.startDate || !state.endDate) {
    document.getElementById("periodCompare").classList.add("hidden");
    return;
  }
  try {
    const data = await fetchJSON("/api/period-comparison?" + buildQuery());
    if (!data.changes) {
      document.getElementById("periodCompare").classList.add("hidden");
      return;
    }
    const { changes, current } = data;
    const items = [
      { label: "Revenue", key: "revenue", fmt: fmtINR },
      { label: "Orders", key: "orders", fmt: fmtNum },
    ];

    document.getElementById("compareItems").innerHTML = items.map(({ label, key, fmt }) => {
      const ch = changes[key] || {};
      const dir = ch.pct > 0 ? "up" : ch.pct < 0 ? "down" : "flat";
      const pctStr = ch.pct != null ? `${Math.abs(ch.pct).toFixed(1)}%` : "—";
      const sign = ch.pct > 0 ? "+" : (ch.pct < 0 ? "-" : "");
      return `
        <div class="compare-item">
          <div class="compare-item-label">${label}</div>
          <div class="compare-item-val">
            ${fmt(current[key] || 0)}
            <span class="compare-badge ${dir}">${sign}${pctStr}</span>
          </div>
        </div>`;
    }).join("");

    document.getElementById("periodCompare").classList.remove("hidden");
  } catch (e) {
    document.getElementById("periodCompare").classList.add("hidden");
  }
}

const PALETTE = ["#0d9488", "#1a2744", "#f59e0b", "#3b82f6", "#8b5cf6", "#ef4444", "#10b981", "#f97316"];

function destroyCharts() {
  [trendChart, regionChart, productChart, categoryChart].forEach((c) => c && c.destroy());
  trendChart = regionChart = productChart = categoryChart = null;
}

async function loadTrendChart() {
  const data = await fetchJSON("/api/revenue-trend?" + buildQuery());
  const ctx = document.getElementById("trendChart");
  if (!ctx) return;

  const labels = data.map((d) => d.month || d.order_date);
  const revenues = data.map((d) => d.revenue);

  if (trendChart) {
    trendChart.data.labels = labels;
    trendChart.data.datasets[0].data = revenues;
    trendChart.update("none");
    return;
  }

  trendChart = new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [{
        data: revenues,
        borderColor: "#0d9488",
        backgroundColor: "rgba(13,148,136,0.08)",
        fill: true,
        tension: 0.35,
        pointRadius: 2,
        pointHoverRadius: 4,
        borderWidth: 2,
        pointBackgroundColor: "#0d9488",
      }],
    },
    options: {
      animation: false,
      responsive: true,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: { label: (c) => " " + fmtINR(c.raw) },
        },
      },
      scales: {
        x: {
          ticks: { color: "#94a3b8", maxRotation: 30, autoSkip: true, maxTicksLimit: 10 },
          grid: { display: false },
          border: { color: "#e2e8f0" },
        },
        y: {
          ticks: { color: "#94a3b8", callback: (v) => fmtINR(v) },
          grid: { color: "#f1f5f9" },
          border: { display: false },
        },
      },
    },
  });
}

async function loadRegionChart() {
  const data = await fetchJSON("/api/region-breakdown?" + buildQuery());
  const ctx = document.getElementById("regionChart");
  if (!ctx) return;

  const labels = data.map((d) => d.region);
  const values = data.map((d) => d.revenue);

  if (regionChart) {
    regionChart.data.labels = labels;
    regionChart.data.datasets[0].data = values;
    regionChart.update("none");
    return;
  }

  regionChart = new Chart(ctx, {
    type: "doughnut",
    data: {
      labels,
      datasets: [{
        data: values,
        backgroundColor: PALETTE,
        borderColor: "#ffffff",
        borderWidth: 2,
      }],
    },
    options: {
      animation: false,
      responsive: true,
      cutout: "65%",
      plugins: {
        legend: {
          position: "bottom",
          labels: { color: "#64748b", boxWidth: 12, padding: 16, font: { size: 11 } },
        },
        tooltip: {
          callbacks: { label: (c) => ` ${c.label}: ${fmtINR(c.raw)}` },
        },
      },
    },
  });
}

async function loadProductChart() {
  const data = await fetchJSON("/api/top-products?" + buildQuery());
  const ctx = document.getElementById("productChart");
  if (!ctx) return;

  const labels = data.map((d) => d.product);
  const values = data.map((d) => d.revenue);

  if (productChart) {
    productChart.data.labels = labels;
    productChart.data.datasets[0].data = values;
    productChart.update("none");
    return;
  }

  productChart = new Chart(ctx, {
    type: "bar",
    data: {
      labels,
      datasets: [{
        data: values,
        backgroundColor: "#0d9488",
        borderRadius: 4,
        maxBarThickness: 18,
      }],
    },
    options: {
      animation: false,
      indexAxis: "y",
      responsive: true,
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: (c) => " " + fmtINR(c.raw) } },
      },
      scales: {
        x: {
          ticks: { color: "#94a3b8", callback: (v) => fmtINR(v) },
          grid: { color: "#f1f5f9" },
          border: { display: false },
        },
        y: {
          ticks: { color: "#334155", font: { size: 11 } },
          grid: { display: false },
          border: { display: false },
        },
      },
    },
  });
}

async function loadCategoryChart() {
  const data = await fetchJSON("/api/category-breakdown?" + buildQuery());
  const ctx = document.getElementById("categoryChart");
  if (!ctx) return;

  const labels = data.map((d) => d.category);
  const values = data.map((d) => d.revenue);

  if (categoryChart) {
    categoryChart.data.labels = labels;
    categoryChart.data.datasets[0].data = values;
    categoryChart.update("none");
    return;
  }

  categoryChart = new Chart(ctx, {
    type: "bar",
    data: {
      labels,
      datasets: [{
        label: "Revenue",
        data: values,
        backgroundColor: "#1a2744",
        borderRadius: 4,
        maxBarThickness: 40,
      }],
    },
    options: {
      animation: false,
      responsive: true,
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: (c) => " " + fmtINR(c.raw) } },
      },
      scales: {
        x: {
          ticks: { color: "#334155" },
          grid: { display: false },
          border: { color: "#e2e8f0" },
        },
        y: {
          ticks: { color: "#94a3b8", callback: (v) => fmtINR(v) },
          grid: { color: "#f1f5f9" },
          border: { display: false },
        },
      },
    },
  });
}

async function loadTable() {
  const data = await fetchJSON("/api/table?" + buildQuery());
  const wrap = document.getElementById("tableWrap");
  const cnt = document.getElementById("tableCount");
  if (!wrap) return;

  if (!data.length) {
    wrap.innerHTML = '<div class="table-empty">No orders match these filters.</div>';
    if (cnt) cnt.textContent = "";
    return;
  }
  if (cnt) cnt.textContent = `Showing ${Math.min(data.length, 40)} of ${data.length} rows`;

  const rows = data.slice(0, 40).map((r) => `<tr>
    <td>${r.order_date}</td>
    <td>${r.region}</td>
    <td>${r.category}</td>
    <td>${r.product}</td>
    <td>${fmtNum(r.quantity)}</td>
    <td>${fmtINR(r.unit_price)}</td>
    <td>${fmtINR(r.revenue)}</td>
  </tr>`).join("");

  wrap.innerHTML = `
    <table>
      <thead>
        <tr>
          <th>Date</th><th>Region</th><th>Category</th><th>Product</th>
          <th>Qty</th><th>Unit Price</th><th>Revenue</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>`;
}

document.getElementById("exportCsvBtn").addEventListener("click", () => {
  window.location.href = "/api/export?" + buildQuery();
});

document.getElementById("exportPdfBtn").addEventListener("click", async () => {
  const btn = document.getElementById("exportPdfBtn");
  const orig = btn.innerHTML;
  btn.innerHTML = "Generating...";
  btn.disabled = true;
  try {
    const res = await fetch("/api/export-pdf?" + buildQuery());
    if (!res.ok) {
      const err = await res.json();
      alert("PDF error: " + (err.error || "Unknown error"));
      return;
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "insightflow_report.pdf";
    a.click();
    URL.revokeObjectURL(url);
  } catch (e) {
    alert("Could not generate PDF: " + e.message);
  } finally {
    btn.innerHTML = orig;
    btn.disabled = false;
  }
});

let refreshTimer = null;
function refreshAll() {
  clearTimeout(refreshTimer);
  refreshTimer = setTimeout(_doRefresh, 50);
}

async function _doRefresh() {
  loadingOvl.classList.remove("hidden");
  try {
    await Promise.all([
      loadKPIs(),
      loadTrendChart(),
      loadRegionChart(),
      loadProductChart(),
      loadCategoryChart(),
      loadTable(),
      loadPeriodComparison(),
    ]);
  } finally {
    loadingOvl.classList.add("hidden");
    document.getElementById("lastUpdated").textContent =
      "Updated " + new Date().toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" });
  }
}

async function enterDataView() {
  showView(true);
  await loadFilterOptions();
  await refreshAll();
}

(async function init() {
  const hasData = await loadFilterOptions();
  if (hasData) {
    await enterDataView();
  } else {
    showView(false);
  }
})();
