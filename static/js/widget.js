const API_URL = "/api/quotes/";
const UI_TEXT_API_URL = "/api/ui-text/";
const POLL_MS = 60000;
const FULL_REFRESH_MS = 60000;
const MAX_BACKOFF_MS = 30000;

const statusEl = document.getElementById("status");
const switcherEl = document.getElementById("asset-switcher");
const switcherHintEl = document.getElementById("switcher-hint");
const symbolEl = document.getElementById("asset-symbol");
const priceEl = document.getElementById("asset-price");
const change1hEl = document.getElementById("asset-1h");
const change24hEl = document.getElementById("asset-24h");
const indicesEl = document.getElementById("asset-indices");
const tickerTrackEl = document.getElementById("ticker-track");
const appTitleEl = document.getElementById("app-title");
const indicesTitleEl = document.getElementById("indices-title");
const widgetEl = document.querySelector(".widget");
const compactToggleEl = document.getElementById("compact-toggle");

let activeAsset = "BTC/USD";
let lastPayload = null;
let lastStatusPayload = null;
let currentLang = "es";
let uiText = {
  status_loading: "Actualizando...",
  status_updated: "Actualizado",
  status_cache: "Dato en cache",
  status_waiting: "esperando CoinGecko...",
  status_retry_in: "Reintento en {seconds}s.",
  status_no_data: "Sin datos",
  lbl_1h: "1h",
  lbl_24h: "24h",
  app_title: "Monitor de Mercado",
  app_subtitle: "Monitoreo en tiempo real",
  indices_title: "Indices Relevantes",
  compact_on: "Compactar",
  compact_off: "Expandir",
};

function setStatus(message, isError = false) {
  if (!statusEl) return;
  statusEl.textContent = message;
  statusEl.classList.toggle("error", isError);
}

function formatPct(value) {
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(2)}%`;
}

function setChangePill(el, label, value) {
  if (!el) return;
  el.textContent = `${label}: ${formatPct(value)}`;
  el.classList.remove("positive", "negative");
  if (value > 0) el.classList.add("positive");
  if (value < 0) el.classList.add("negative");
}

function formatAssetDisplay(asset) {
  if (!asset || typeof asset.price !== "number" || !Number.isFinite(asset.price)) {
    return asset?.display || "--";
  }

  const decimalsBySymbol = {
    "BTC/USD": 2,
    "ETH/USD": 2,
    "EUR/USD": 5,
    "XAU/USD": 2,
    "XAG/USD": 3,
  };

  const decimals = decimalsBySymbol[asset.symbol] ?? 2;
  const value = Number(asset.price).toLocaleString("en-US", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });

  return asset.symbol === "EUR/USD" ? value : `$${value}`;
}

function localeFromLanguage(code) {
  const map = {
    es: "es-ES",
    en: "en-US",
    pt: "pt-PT",
    fr: "fr-FR",
    de: "de-DE",
    ja: "ja-JP",
    zh: "zh-CN",
  };
  return map[code] || "es-ES";
}

function applyUiText(payloadUiText, payloadLanguage) {
  uiText = { ...uiText, ...(payloadUiText || {}) };
  currentLang = payloadLanguage || currentLang;

  if (appTitleEl) appTitleEl.textContent = uiText.app_title;
  if (indicesTitleEl) indicesTitleEl.textContent = uiText.indices_title;
  if (widgetEl) {
    applyCompactUiState(widgetEl.classList.contains("compact"));
  }
}

function renderStatusFromPayload(payload) {
  if (!payload || typeof payload.updated_at !== "number") return;

  if (payload.stale) {
    const waitText = Number.isFinite(payload.retry_after_seconds) && payload.retry_after_seconds > 0
      ? ` ${(uiText.status_retry_in || "Reintento en {seconds}s.").replace("{seconds}", String(payload.retry_after_seconds))}`
      : "";
    setStatus(`${uiText.status_cache || "Dato en cache"}: ${formatDateFromUnix(payload.updated_at)} (${uiText.status_waiting || "esperando CoinGecko..."})${waitText}`);
  } else {
    setStatus(`${uiText.status_updated || "Actualizado"}: ${formatDateFromUnix(payload.updated_at)}`);
  }
}

function applyCompactUiState(isCompact) {
  if (!widgetEl || !compactToggleEl) return;
  widgetEl.classList.toggle("compact", isCompact);
  compactToggleEl.classList.toggle("active", isCompact);
  compactToggleEl.setAttribute("aria-pressed", isCompact ? "true" : "false");
  compactToggleEl.textContent = isCompact
    ? (uiText.compact_off || "Expandir")
    : (uiText.compact_on || "Compactar");
}

async function syncCompactWindowSize(isCompact) {
  try {
    if (window.pywebview && window.pywebview.api && window.pywebview.api.set_compact_mode) {
      await window.pywebview.api.set_compact_mode(Boolean(isCompact));
    }
  } catch (_err) {
    // Ignore bridge errors in plain browser/dev mode.
  }
}

function toggleCompactMode() {
  if (!widgetEl) return;
  const isCompact = !widgetEl.classList.contains("compact");
  applyCompactUiState(isCompact);
  syncCompactWindowSize(isCompact);
  try {
    localStorage.setItem("widgetCompactMode", isCompact ? "1" : "0");
  } catch (_err) {
    // Ignore localStorage failures in embedded webview contexts.
  }
}

function initCompactMode() {
  let isCompact = false;
  try {
    isCompact = localStorage.getItem("widgetCompactMode") === "1";
  } catch (_err) {
    isCompact = false;
  }
  applyCompactUiState(isCompact);
  syncCompactWindowSize(isCompact);
}

function renderIndices(indices) {
  if (!indicesEl) return;
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
  if (!symbolEl || !priceEl || !change1hEl || !change24hEl) return;
  if (!payload || !payload.assets || !payload.assets[activeAsset]) return;
  const asset = payload.assets[activeAsset];

  symbolEl.textContent = asset.symbol;
  priceEl.textContent = formatAssetDisplay(asset);
  setChangePill(change1hEl, uiText.lbl_1h || "1h", asset.change_1h_pct);
  setChangePill(change24hEl, uiText.lbl_24h || "24h", asset.change_24h_pct);
  renderIndices(asset.indices || []);
}

function renderTicker(ticker) {
  if (!tickerTrackEl) return;
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
  applyUiText(payload.ui_text, payload.language);
  lastPayload = payload;
  renderAssetView(payload);
  renderTicker(payload.ticker || []);
}

function renderActiveOnly(payload) {
  applyUiText(payload.ui_text, payload.language);
  if (!payload || !payload.assets || !payload.assets[activeAsset]) return;

  if (!lastPayload) {
    lastPayload = payload;
  } else {
    lastPayload = {
      ...lastPayload,
      updated_at: payload.updated_at,
      stale: payload.stale,
      retry_after_seconds: payload.retry_after_seconds,
      language: payload.language,
      ui_text: payload.ui_text,
      assets: {
        ...lastPayload.assets,
        [activeAsset]: payload.assets[activeAsset],
      },
    };
  }

  renderAssetView(lastPayload);
}

async function syncUiTextOnly() {
  try {
    const response = await fetch(UI_TEXT_API_URL, { cache: "no-store" });
    if (!response.ok) return;
    const data = await response.json();
    if (!data || !data.ok) return;
    applyUiText(data.ui_text, data.language);
  } catch (_err) {
    // Ignore language-sync failures; polling loop will try again.
  }
}

async function syncLanguageNow() {
  await syncUiTextOnly();
  if (lastPayload) {
    renderAssetView(lastPayload);
  }
  if (lastStatusPayload) {
    renderStatusFromPayload(lastStatusPayload);
  }
}

window.__widgetSyncLanguage = syncLanguageNow;

function onSwitcherClick(event) {
  if (!switcherEl) return;
  const button = event.target.closest(".asset-btn");
  if (!button) return;

  activeAsset = button.dataset.asset;
  [...switcherEl.querySelectorAll(".asset-btn")].forEach((btn) => {
    btn.classList.toggle("active", btn === button);
  });

  renderAssetView(lastPayload);
}

function updateSwitcherHint() {
  if (!switcherEl || !switcherHintEl) return;
  const hidden = switcherEl.scrollWidth <= switcherEl.clientWidth + 2
    || (switcherEl.scrollLeft + switcherEl.clientWidth >= switcherEl.scrollWidth - 2);
  switcherHintEl.classList.toggle("hidden", hidden);
}

function onSwitcherWheel(event) {
  if (!switcherEl) return;
  if (Math.abs(event.deltaY) > Math.abs(event.deltaX)) {
    switcherEl.scrollLeft += event.deltaY;
    event.preventDefault();
    updateSwitcherHint();
  }
}

function initSwitcherScrollHint() {
  if (!switcherEl) return;
  switcherEl.addEventListener("scroll", updateSwitcherHint, { passive: true });
  switcherEl.addEventListener("wheel", onSwitcherWheel, { passive: false });
  window.addEventListener("resize", updateSwitcherHint);
  updateSwitcherHint();
}

function formatDateFromUnix(ts) {
  const dt = new Date(ts * 1000);
  return dt.toLocaleTimeString(localeFromLanguage(currentLang));
}

async function refreshQuotes() {
  setStatus(uiText.status_loading || "Actualizando...");

  try {
    const response = await fetch(API_URL, { cache: "no-store" });
    const data = await response.json();

    if (data && (data.ui_text || data.language)) {
      applyUiText(data.ui_text, data.language);
    }

    if (!response.ok || !data.ok) {
      throw new Error(data.error || "Error al consultar API");
    }

    lastStatusPayload = {
      updated_at: data.updated_at,
      stale: data.stale,
      retry_after_seconds: data.retry_after_seconds,
    };

    const nowMs = Date.now();
    const shouldFullRefresh = !lastPayload || (nowMs - lastFullRefreshAt >= FULL_REFRESH_MS);
    if (shouldFullRefresh) {
      renderPayload(data);
      lastFullRefreshAt = nowMs;
    } else {
      renderActiveOnly(data);
    }

    renderStatusFromPayload(lastStatusPayload);
    return { ok: true, status: response.status };
  } catch (err) {
    await syncUiTextOnly();
    setStatus(`${uiText.status_no_data || "Sin datos"}: ${err.message}`, true);
    return { ok: false, status: 0, error: err };
  }
}

let currentPollMs = POLL_MS;
let lastFullRefreshAt = 0;

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

if (switcherEl) {
  switcherEl.addEventListener("click", onSwitcherClick);
}

if (compactToggleEl) {
  compactToggleEl.addEventListener("click", toggleCompactMode);
}

if (statusEl) {
  initCompactMode();
  initSwitcherScrollHint();
  syncUiTextOnly();
  pollLoop();
}
