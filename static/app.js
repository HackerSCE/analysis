const analyzeBtn = document.getElementById("analyzeBtn");
const downloadBtn = document.getElementById("downloadBtn");
const symbolInput = document.getElementById("symbolInput");
const symbolSuggestions = document.getElementById("symbolSuggestions");
const symbolClearBtn = document.getElementById("symbolClearBtn");
const dateFromInput = document.getElementById("dateFromInput");
const dateToInput = document.getElementById("dateToInput");
const sessionStartInput = document.getElementById("sessionStartInput");
const signalStartInput = document.getElementById("signalStartInput");
const sessionExitInput = document.getElementById("sessionExitInput");
const emptyState = document.getElementById("emptyState");
const tradesBody = document.getElementById("tradesBody");
const logoutBtn = document.getElementById("logoutBtn");
let latestAnalysis = null;
let suggestionTimer = null;
let activeSuggestionIndex = -1;
let latestSuggestions = [];
let latestQuery = "";
let activeFetchController = null;
const recentSearches = [];
const MAX_RECENT_SEARCHES = 5;

updateClearButton();

analyzeBtn.addEventListener("click", analyze);
downloadBtn.addEventListener("click", downloadExcel);
symbolInput.addEventListener("keydown", (event) => {
  if (handleSuggestionKeydown(event)) {
    return;
  }
  if (event.key === "Enter") analyze();
});
symbolInput.addEventListener("input", onSymbolInput);
symbolInput.addEventListener("focus", onSymbolFocus);

if (symbolClearBtn) {
  symbolClearBtn.addEventListener("click", () => {
    symbolInput.value = "";
    latestQuery = "";
    renderSuggestions(recentSearchesAsItems(), "");
    updateClearButton();
    symbolInput.focus();
  });
}

document.addEventListener("click", (event) => {
  if (!symbolSuggestions || !symbolInput) return;
  if (symbolSuggestions.contains(event.target) || symbolInput.contains(event.target)) return;
  closeSuggestions();
});

if (logoutBtn) {
  logoutBtn.addEventListener("click", async () => {
    await fetch("/logout", { method: "POST" });
    window.location.reload();
  });
}

async function analyze() {
  const payload = getBacktestPayload();
  setBusy(true);
  try {
    const response = await fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Analysis failed.");
    latestAnalysis = data;
    downloadBtn.disabled = false;
    renderChart(data.chart, data.symbol);
    renderMetrics(data.metrics);
    renderTrades(data.trades);
  } catch (error) {
    emptyState.textContent = error.message;
    emptyState.style.display = "grid";
  } finally {
    setBusy(false);
  }
}

function getBacktestPayload() {
  return {
    symbol: symbolInput.value.trim(),
    date_from: dateFromInput.value,
    date_to: dateToInput.value,
    session_start: sessionStartInput.value,
    signal_start: signalStartInput.value,
    session_exit: sessionExitInput.value,
  };
}

function onSymbolInput(event) {
  const query = (event?.target?.value || "").trim();
  latestQuery = query;
  updateClearButton();

  window.clearTimeout(suggestionTimer);
  if (!query) {
    renderSuggestions(recentSearchesAsItems(), "");
    return;
  }

  if (query.length < 2) {
    renderSuggestions([], query, { hint: "Type at least 2 characters" });
    return;
  }

  renderSuggestions([], query, { loading: true });
  suggestionTimer = window.setTimeout(() => {
    fetchSymbolSuggestions(query);
  }, 300);
}

function onSymbolFocus() {
  if (!symbolInput.value.trim() && recentSearches.length) {
    renderSuggestions(recentSearchesAsItems(), "");
  }
}

async function fetchSymbolSuggestions(query) {
  if (!query || query.length < 2) return;
  if (activeFetchController) {
    activeFetchController.abort();
  }

  activeFetchController = new AbortController();
  try {
    const response = await fetch(`/api/symbol-search?q=${encodeURIComponent(query)}`, {
      signal: activeFetchController.signal,
      cache: "no-store",
    });
    const data = await response.json().catch(() => []);
    if (!response.ok) {
      throw new Error(data?.error || "Unable to load symbol suggestions.");
    }

    if (latestQuery !== query) return;
    renderSuggestions(Array.isArray(data) ? data : [], query);
  } catch (error) {
    if (error.name === "AbortError") return;
    renderSuggestions([], query, { error: error.message || "Unable to load suggestions." });
  }
}

function renderSuggestions(items, query, options = {}) {
  if (!symbolSuggestions) return;

  activeSuggestionIndex = -1;
  latestSuggestions = Array.isArray(items) ? items : [];
  symbolSuggestions.innerHTML = "";

  if (options.loading) {
    symbolSuggestions.appendChild(buildInfoRow("Loading suggestions..."));
    openSuggestions();
    return;
  }

  if (options.error) {
    symbolSuggestions.appendChild(buildInfoRow(options.error));
    openSuggestions();
    return;
  }

  if (options.hint) {
    symbolSuggestions.appendChild(buildInfoRow(options.hint));
    openSuggestions();
    return;
  }

  if (!latestSuggestions.length) {
    const message = query ? "No results found" : "Start typing a symbol";
    symbolSuggestions.appendChild(buildInfoRow(message));
    openSuggestions();
    return;
  }

  const showRecentLabel = !query && recentSearches.length > 0;
  if (showRecentLabel) {
    const recentRow = document.createElement("div");
    recentRow.className = "symbol-suggestion-item";
    recentRow.innerHTML = '<div class="symbol-suggestion-info">Recent searches</div>';
    symbolSuggestions.appendChild(recentRow);
  }

  latestSuggestions.forEach((item, index) => {
    const suggestionEl = document.createElement("button");
    suggestionEl.type = "button";
    suggestionEl.className = "symbol-suggestion-item";
    suggestionEl.setAttribute("role", "option");
    suggestionEl.dataset.index = String(index);

    const title = document.createElement("div");
    title.className = "symbol-suggestion-title";
    title.innerHTML = highlightMatch(item.name || "", query);

    const meta = document.createElement("div");
    meta.className = "symbol-suggestion-meta";
    meta.innerHTML = `${highlightMatch(item.symbol || "", query)}`;

    const info = document.createElement("div");
    info.className = "symbol-suggestion-info";
    info.textContent = `${item.type || "Instrument"} • ${item.exchange || ""}`;

    suggestionEl.appendChild(title);
    suggestionEl.appendChild(meta);
    suggestionEl.appendChild(info);
    suggestionEl.addEventListener("click", () => selectSuggestion(index));
    symbolSuggestions.appendChild(suggestionEl);
  });

  openSuggestions();
}

function buildInfoRow(text) {
  const row = document.createElement("div");
  row.className = "symbol-suggestion-item";
  row.innerHTML = `<div class="symbol-suggestion-meta">${escapeHtml(text)}</div>`;
  return row;
}

function openSuggestions() {
  if (!symbolSuggestions) return;
  symbolSuggestions.hidden = false;
  symbolInput.setAttribute("aria-expanded", "true");
}

function closeSuggestions() {
  if (!symbolSuggestions) return;
  symbolSuggestions.hidden = true;
  symbolSuggestions.innerHTML = "";
  symbolInput.setAttribute("aria-expanded", "false");
  activeSuggestionIndex = -1;
  latestSuggestions = [];
}

function handleSuggestionKeydown(event) {
  if (!symbolSuggestions || symbolSuggestions.hidden || !latestSuggestions.length) {
    return false;
  }

  if (event.key === "ArrowDown") {
    event.preventDefault();
    setActiveSuggestion(activeSuggestionIndex + 1);
    return true;
  }

  if (event.key === "ArrowUp") {
    event.preventDefault();
    setActiveSuggestion(activeSuggestionIndex - 1);
    return true;
  }

  if (event.key === "Enter") {
    if (activeSuggestionIndex >= 0) {
      event.preventDefault();
      selectSuggestion(activeSuggestionIndex);
      return true;
    }
  }

  if (event.key === "Escape") {
    event.preventDefault();
    closeSuggestions();
    return true;
  }

  return false;
}

function setActiveSuggestion(nextIndex) {
  if (!symbolSuggestions) return;

  const max = latestSuggestions.length - 1;
  if (max < 0) return;

  if (nextIndex < 0) nextIndex = max;
  if (nextIndex > max) nextIndex = 0;

  activeSuggestionIndex = nextIndex;
  symbolSuggestions.querySelectorAll(".symbol-suggestion-item").forEach((el, index) => {
    el.classList.toggle("active", index === activeSuggestionIndex);
  });

  const activeEl = symbolSuggestions.querySelector(`.symbol-suggestion-item[data-index="${activeSuggestionIndex}"]`);
  if (activeEl) {
    activeEl.scrollIntoView({ block: "nearest" });
  }
}

function selectSuggestion(index) {
  const item = latestSuggestions[index];
  if (!item) return;

  symbolInput.value = item.symbol || "";
  latestQuery = symbolInput.value;
  pushRecentSearch(item);
  closeSuggestions();
  updateClearButton();
  symbolInput.focus();
}

function updateClearButton() {
  if (!symbolClearBtn) return;
  const hasText = Boolean(symbolInput.value.trim());
  symbolClearBtn.classList.toggle("visible", hasText);
}

function pushRecentSearch(item) {
  if (!item?.symbol) return;
  const normalized = item.symbol.toUpperCase();
  const deduped = recentSearches.filter((entry) => (entry.symbol || "").toUpperCase() !== normalized);
  deduped.unshift(item);
  recentSearches.splice(0, recentSearches.length, ...deduped.slice(0, MAX_RECENT_SEARCHES));
}

function recentSearchesAsItems() {
  return recentSearches.map((item) => ({ ...item, type: item.type || "Recent" }));
}

function highlightMatch(text, query) {
  const safeText = escapeHtml(String(text || ""));
  const cleanQuery = String(query || "").trim();
  if (!cleanQuery) return safeText;

  const escapedQuery = cleanQuery.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const regex = new RegExp(`(${escapedQuery})`, "ig");
  return safeText.replace(regex, "<mark>$1</mark>");
}

async function downloadExcel() {
  if (!latestAnalysis) return;
  downloadBtn.disabled = true;
  try {
    const response = await fetch("/api/export", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(latestAnalysis),
    });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(data.error || "Could not export Excel file.");
    }
    const blob = await response.blob();
    const safeSymbol = latestAnalysis.symbol.replace(/[^a-z0-9]+/gi, "_");
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `${safeSymbol}_por_trades.xlsx`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(link.href);
  } catch (error) {
    emptyState.textContent = error.message;
    emptyState.style.display = "grid";
  } finally {
    downloadBtn.disabled = false;
  }
}

function setBusy(isBusy) {
  analyzeBtn.disabled = isBusy;
  analyzeBtn.textContent = isBusy ? "Loading..." : "Analyze";
  if (!isBusy) downloadBtn.disabled = !latestAnalysis;
}

function renderChart(chart, symbol) {
  const candles = chart.candles;
  const x = candles.map((c) => c.datetime);
  const close = candles.map((c) => c.close);

  const buyMarkers = chart.markers.filter((m) => m.side === "BUY");
  const sellMarkers = chart.markers.filter((m) => m.side === "SELL");
  const exitMarkers = chart.markers.filter((m) => m.side === "EXIT");

  const traces = [
    {
      x,
      open: candles.map((c) => c.open),
      high: candles.map((c) => c.high),
      low: candles.map((c) => c.low),
      close,
      type: "candlestick",
      name: symbol,
      increasing: { line: { color: "#0f9f6e" } },
      decreasing: { line: { color: "#d64545" } },
      xaxis: "x",
      yaxis: "y",
    },
    markerTrace(buyMarkers, "Buy", "#0f9f6e", "triangle-up"),
    markerTrace(sellMarkers, "Sell", "#d64545", "triangle-down"),
    markerTrace(exitMarkers, "Exit", "#111827", "x"),
  ];

  const layout = {
    title: { text: `${symbol} - 5 minute candles`, x: 0, font: { size: 18 } },
    paper_bgcolor: "#ffffff",
    plot_bgcolor: "#ffffff",
    margin: { l: 52, r: 24, t: 48, b: 44 },
    dragmode: "pan",
    xaxis: { domain: [0, 1], rangeslider: { visible: false }, showgrid: false },
    yaxis: { title: "Price", gridcolor: "#e5e7eb" },
    legend: { orientation: "h", y: 1.06, x: 0.45 },
  };

  Plotly.newPlot("chart", traces, layout, { responsive: true, displaylogo: false });
  emptyState.style.display = "none";
}



function markerTrace(markers, name, color, symbol) {
  return {
    x: markers.map((m) => m.time),
    y: markers.map((m) => m.price),
    type: "scatter",
    mode: "markers",
    name,
    marker: { color, symbol, size: 11, line: { color: "#ffffff", width: 1 } },
    xaxis: "x",
    yaxis: "y",
  };
}

function renderMetrics(metrics) {
  document.getElementById("totalPnl").textContent = Number(metrics.total_pnl).toFixed(2);
  document.getElementById("winRate").textContent = `${Number(metrics.win_rate).toFixed(2)}%`;
  document.getElementById("drawdown").textContent = Number(metrics.drawdown).toFixed(2);
  document.getElementById("tradeCount").textContent = metrics.trade_count;
}

function renderTrades(trades) {
  if (!trades.length) {
    tradesBody.innerHTML = '<tr><td colspan="7">No trades matched the setup.</td></tr>';
    return;
  }
  tradesBody.innerHTML = trades.map((trade) => `
    <tr>
      <td><span class="pill ${trade.side.toLowerCase()}">${trade.side}</span></td>
      <td>${formatDateTime(trade.entry_time)}</td>
      <td>${trade.entry_price.toFixed(2)}</td>
      <td>${formatDateTime(trade.exit_time)}</td>
      <td>${trade.exit_price.toFixed(2)}</td>
      <td>${trade.exit_reason.replace("_", " ")}</td>
      <td class="${trade.pnl >= 0 ? "profit" : "loss"}">${trade.pnl.toFixed(2)}</td>
    </tr>
  `).join("");
}

function formatDateTime(value) {
  return new Date(value).toLocaleString("en-IN", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
