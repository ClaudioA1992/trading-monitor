const API_URL = "/api/quotes/";
const POLL_MS = 5000;
const MAX_BACKOFF_MS = 30000;

const statusEl = document.getElementById("status");
const switcherEl = document.getElementById("asset-switcher");
const symbolEl = document.getElementById("asset-symbol");
const priceEl = document.getElementById("asset-price");
const change1hEl = document.getElementById("asset-1h");
const change24hEl = document.getElementById("asset-24h");
const indicesEl = document.getElementById("asset-indices");
const tickerTrackEl = document.getElementById("ticker-track");

let activeAsset = "BTC/USD";
let lastPayload = null;

function setStatus(message, isError = false) {
  statusEl.textContent = message;
  statusEl.classList.toggle("error", isError);
}

function formatPct(value) {
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(2)}%`;
}

function setChangePill(el, label, value) {
  el.textContent = `${label}: ${formatPct(value)}`;
  el.classList.remove("positive", "negative");
  if (value > 0) el.classList.add("positive");
  if (value < 0) el.classList.add("negative");
}

function renderIndices(indices) {
  indicesEl.innerHTML = "";
  indices.forEach((idx) => {
    const item = document.createElement("article");
    item.className = "index-item";

    const label = document.createElement("span");
    label.className = "index-label";
    label.textContent = idx.label;

    const value = document.createElement("span");
    value.className = "index-value";
    value.textContent = idx.currency ? `$${idx.value}` : idx.value;

    item.appendChild(label);
    item.appendChild(value);
    indicesEl.appendChild(item);
  });
}

function renderAssetView(payload) {
  if (!payload || !payload.assets || !payload.assets[activeAsset]) return;
  const asset = payload.assets[activeAsset];

  symbolEl.textContent = asset.symbol;
  priceEl.textContent = asset.display;
  setChangePill(change1hEl, "1h", asset.change_1h_pct);
  setChangePill(change24hEl, "24h", asset.change_24h_pct);
  renderIndices(asset.indices || []);
}

function renderTicker(ticker) {
  const fragments = [];
  ticker.forEach((item) => {
    const cls = item.change_24h_pct > 0 ? "positive" : item.change_24h_pct < 0 ? "negative" : "";
    const sign = item.change_24h_pct > 0 ? "+" : "";
    fragments.push(
      `<span class="ticker-item ${cls}"><b>${item.label}</b> ${item.value} ${sign}${Number(item.change_24h_pct).toFixed(2)}%</span>`
    );
  });

  const trackHtml = fragments.join("") + fragments.join("");
  tickerTrackEl.innerHTML = trackHtml;
}

function renderPayload(payload) {
  lastPayload = payload;
  renderAssetView(payload);
  renderTicker(payload.ticker || []);
}

function onSwitcherClick(event) {
  const button = event.target.closest(".asset-btn");
  if (!button) return;

  activeAsset = button.dataset.asset;
  [...switcherEl.querySelectorAll(".asset-btn")].forEach((btn) => {
    btn.classList.toggle("active", btn === button);
  });

  renderAssetView(lastPayload);
}

function formatDateFromUnix(ts) {
  const dt = new Date(ts * 1000);
  return dt.toLocaleTimeString("es-ES");
}

async function refreshQuotes() {
  setStatus("Actualizando...");

  try {
    const response = await fetch(API_URL, { cache: "no-store" });
    const data = await response.json();

    if (!response.ok || !data.ok) {
      throw new Error(data.error || "Error al consultar API");
    }

    renderPayload(data);
    if (data.stale) {
      const waitText = Number.isFinite(data.retry_after_seconds) && data.retry_after_seconds > 0
        ? ` Reintento en ${data.retry_after_seconds}s.`
        : "";
      setStatus(`Dato en cache: ${formatDateFromUnix(data.updated_at)} (esperando CoinGecko...)${waitText}`);
    } else {
      setStatus(`Actualizado: ${formatDateFromUnix(data.updated_at)}`);
    }
    return { ok: true, status: response.status };
  } catch (err) {
    setStatus(`Sin datos: ${err.message}`, true);
    return { ok: false, status: 0, error: err };
  }
}

let currentPollMs = POLL_MS;

async function pollLoop() {
  const result = await refreshQuotes();

  if (result.ok) {
    currentPollMs = POLL_MS;
  } else {
    // If CoinGecko throttles (429) or gateway fails (5xx), back off progressively.
    currentPollMs = Math.min(currentPollMs * 2, MAX_BACKOFF_MS);
  }

  setTimeout(pollLoop, currentPollMs);
}

switcherEl.addEventListener("click", onSwitcherClick);
pollLoop();
