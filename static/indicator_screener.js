const elements = {
  instrumentTypeChips: document.getElementById("instrumentTypeChips"),
  sectorChips: document.getElementById("sectorChips"),
  timeframe: document.getElementById("timeframeSelect"),
  presetButtons: document.getElementById("presetButtons"),
  conditionsList: document.getElementById("conditionsList"),
  addCondition: document.getElementById("addConditionBtn"),
  runScan: document.getElementById("runScanBtn"),
  refreshScan: document.getElementById("refreshScreenerBtn"),
  autoRefresh: document.getElementById("autoRefreshToggle"),
  andLogic: document.getElementById("andLogicBtn"),
  orLogic: document.getElementById("orLogicBtn"),
  message: document.getElementById("screenerMessage"),
  tableBody: document.getElementById("screenerTableBody"),
  tableStatus: document.getElementById("screenerTableStatus"),
  rowCount: document.getElementById("screenerRowCount"),
  pageInfo: document.getElementById("screenerPageInfo"),
  prevPage: document.getElementById("screenerPrevPageBtn"),
  nextPage: document.getElementById("screenerNextPageBtn"),
  pageSize: document.getElementById("screenerPageSizeSelect"),
  search: document.getElementById("screenerSearchInput"),
  signalFilter: document.getElementById("signalFilterSelect"),
  sort: document.getElementById("screenerSortSelect"),
  exportExcel: document.getElementById("exportExcelBtn"),
  exportCsv: document.getElementById("exportCsvBtn"),
  lastUpdated: document.getElementById("screenerLastUpdated"),
  nextRefresh: document.getElementById("screenerNextRefresh"),
  scanLatency: document.getElementById("scanLatency"),
  catalogStatus: document.getElementById("catalogStatus"),
  saveScanName: document.getElementById("saveScanName"),
  saveScan: document.getElementById("saveScanBtn"),
  savedScanSelect: document.getElementById("savedScanSelect"),
  loadScan: document.getElementById("loadScanBtn"),
  deleteScan: document.getElementById("deleteScanBtn"),
  logoutBtn: document.getElementById("logoutBtn"),
  totalStocksScanned: document.getElementById("totalStocksScanned"),
  matchingResults: document.getElementById("matchingResults"),
  bullishSignals: document.getElementById("bullishSignals"),
  bearishSignals: document.getElementById("bearishSignals"),
  strongestMomentumStock: document.getElementById("strongestMomentumStock"),
  highestAdxStock: document.getElementById("highestAdxStock"),
  highestVolumeBreakout: document.getElementById("highestVolumeBreakout"),
};

const STORAGE_KEY = "advancedFoIndicatorScreener.savedScans";
const TIMEFRAME_ALIASES = {
  D: "1D",
  DAY: "1D",
  W: "1W",
  WEEK: "1W",
};

const state = {
  metadata: null,
  instrumentTypes: ["spot", "near"],
  sectors: ["All Sectors"],
  timeframe: "5",
  logic: "AND",
  conditions: [],
  rows: [],
  summary: null,
  scan: null,
  generatedAt: null,
  search: "",
  signalFilter: "all",
  sort: "signalScore",
  pageSize: 25,
  page: 1,
  isLoading: false,
  refreshInterval: 60,
  refreshTimer: null,
  nextRefreshAt: null,
};

wireEvents();
loadMetadata();
window.setInterval(renderCountdown, 1000);

function wireEvents() {
  elements.instrumentTypeChips.addEventListener("click", onInstrumentChipClick);
  elements.sectorChips.addEventListener("click", onSectorChipClick);
  elements.timeframe.addEventListener("change", () => {
    state.timeframe = elements.timeframe.value;
  });
  elements.addCondition.addEventListener("click", () => {
    state.conditions.push(defaultCondition());
    renderConditions();
  });
  elements.conditionsList.addEventListener("change", onConditionChange);
  elements.conditionsList.addEventListener("input", onConditionInput);
  elements.conditionsList.addEventListener("click", onConditionClick);
  elements.andLogic.addEventListener("click", () => setLogic("AND"));
  elements.orLogic.addEventListener("click", () => setLogic("OR"));
  elements.runScan.addEventListener("click", () => runScan({ manual: true }));
  elements.refreshScan.addEventListener("click", () => runScan({ manual: true }));
  elements.autoRefresh.addEventListener("change", scheduleNextRefresh);
  elements.search.addEventListener("input", () => {
    state.search = elements.search.value.trim().toUpperCase();
    state.page = 1;
    renderResults();
  });
  elements.signalFilter.addEventListener("change", () => {
    state.signalFilter = elements.signalFilter.value;
    state.page = 1;
    renderResults();
  });
  elements.sort.addEventListener("change", () => {
    state.sort = elements.sort.value;
    state.page = 1;
    renderResults();
  });
  elements.pageSize.addEventListener("change", () => {
    state.pageSize = elements.pageSize.value === "all" ? "all" : Number(elements.pageSize.value);
    state.page = 1;
    renderResults();
  });
  elements.prevPage.addEventListener("click", () => {
    state.page = Math.max(1, state.page - 1);
    renderResults();
  });
  elements.nextPage.addEventListener("click", () => {
    state.page += 1;
    renderResults();
  });
  elements.exportExcel.addEventListener("click", () => exportResults("xlsx"));
  elements.exportCsv.addEventListener("click", () => exportResults("csv"));
  elements.saveScan.addEventListener("click", saveCurrentScan);
  elements.loadScan.addEventListener("click", loadSelectedScan);
  elements.deleteScan.addEventListener("click", deleteSelectedScan);

  if (elements.logoutBtn) {
    elements.logoutBtn.addEventListener("click", async () => {
      await fetch("/logout", { method: "POST" });
      window.location.reload();
    });
  }
}

async function loadMetadata() {
  setMessage("");
  try {
    const response = await fetch("/api/indicator-screener/metadata", { cache: "no-store" });
    const metadata = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(metadata.error || "Unable to load screener metadata.");
    state.metadata = metadata;
    state.refreshInterval = metadata.refreshIntervalSeconds || 60;
    elements.catalogStatus.textContent = `${formatInteger(metadata.symbols?.length || 0)} F&O stocks mapped`;
    renderUniverseControls();
    renderPresets();
    if (!state.conditions.length) {
      const preset = presetById("momentum_buying");
      if (preset) {
        applyPreset(preset.id);
      } else {
        state.conditions = [defaultCondition()];
      }
    }
    renderConditions();
    renderSavedScans();
    if (metadata.warnings?.length) setMessage(metadata.warnings.join(" | "));
  } catch (error) {
    elements.catalogStatus.textContent = "Catalog unavailable";
    setMessage(error.message);
  }
}

function renderUniverseControls() {
  state.timeframe = normalizeTimeframeId(state.timeframe);
  elements.instrumentTypeChips.innerHTML = state.metadata.instrumentTypes.map((item) => chipButton(
    item.label,
    item.id,
    state.instrumentTypes.includes(item.id),
    "instrument",
  )).join("");

  elements.sectorChips.innerHTML = state.metadata.sectors.map((sector) => chipButton(
    sector,
    sector,
    state.sectors.includes(sector),
    "sector",
  )).join("");

  elements.timeframe.innerHTML = state.metadata.timeframes.map((timeframe) => `
    <option value="${escapeHtml(timeframe.id)}">${escapeHtml(timeframe.label)}</option>
  `).join("");
  elements.timeframe.value = state.timeframe;
}

function renderPresets() {
  elements.presetButtons.innerHTML = state.metadata.presets.map((preset) => `
    <button class="ghost preset-button" type="button" data-preset="${escapeHtml(preset.id)}">${escapeHtml(preset.label)}</button>
  `).join("");
  elements.presetButtons.querySelectorAll("[data-preset]").forEach((button) => {
    button.addEventListener("click", () => applyPreset(button.dataset.preset));
  });
}

function chipButton(label, value, active, type) {
  return `
    <button class="filter-chip ${active ? "active" : ""}" type="button" data-chip-type="${type}" data-value="${escapeHtml(value)}">
      ${escapeHtml(label)}
    </button>
  `;
}

function onInstrumentChipClick(event) {
  const button = event.target.closest("[data-chip-type='instrument']");
  if (!button) return;
  const value = button.dataset.value;
  if (state.instrumentTypes.includes(value)) {
    state.instrumentTypes = state.instrumentTypes.filter((item) => item !== value);
  } else {
    state.instrumentTypes = [...state.instrumentTypes, value];
  }
  if (!state.instrumentTypes.length) state.instrumentTypes = ["spot"];
  renderUniverseControls();
}

function onSectorChipClick(event) {
  const button = event.target.closest("[data-chip-type='sector']");
  if (!button) return;
  const value = button.dataset.value;
  if (value === "All Sectors") {
    state.sectors = ["All Sectors"];
  } else if (state.sectors.includes(value)) {
    state.sectors = state.sectors.filter((sector) => sector !== value);
    if (!state.sectors.length) state.sectors = ["All Sectors"];
  } else {
    state.sectors = state.sectors.filter((sector) => sector !== "All Sectors").concat(value);
  }
  renderUniverseControls();
}

function renderConditions() {
  const indicatorGroups = state.metadata?.indicatorGroups || [];
  elements.conditionsList.innerHTML = state.conditions.map((condition, index) => {
    const indicator = indicatorById(condition.indicator) || firstIndicator();
    const operator = operatorById(indicator, condition.operator) || indicator.operators[0];
    const needsValue = operator?.needsValue;
    const selectedTimeframe = normalizeTimeframeId(condition.timeframe || state.timeframe);
    return `
      <div class="condition-row" data-condition-index="${index}">
        <select class="condition-indicator" data-role="indicator">
          ${indicatorGroups.map((group) => `
            <optgroup label="${escapeHtml(group.group)}">
              ${group.indicators.map((item) => `
                <option value="${escapeHtml(item.id)}" ${item.id === indicator.id ? "selected" : ""}>${escapeHtml(item.label)}</option>
              `).join("")}
            </optgroup>
          `).join("")}
        </select>
        <select class="condition-operator" data-role="operator">
          ${indicator.operators.map((item) => `
            <option value="${escapeHtml(item.id)}" ${item.id === operator.id ? "selected" : ""}>${escapeHtml(item.label)}</option>
          `).join("")}
        </select>
        <select class="condition-timeframe" data-role="timeframe">
          ${state.metadata.timeframes.map((timeframe) => `
            <option value="${escapeHtml(timeframe.id)}" ${timeframe.id === selectedTimeframe ? "selected" : ""}>${escapeHtml(timeframe.label)}</option>
          `).join("")}
        </select>
        <input class="condition-value" data-role="value" type="number" step="0.01" ${needsValue ? "" : "disabled"} value="${needsValue ? escapeHtml(condition.value ?? indicator.defaultValue ?? "") : ""}" placeholder="Value">
        <button class="ghost condition-remove" type="button" data-role="remove">Remove</button>
      </div>
    `;
  }).join("");
}

function onConditionChange(event) {
  const row = event.target.closest("[data-condition-index]");
  if (!row) return;
  const index = Number(row.dataset.conditionIndex);
  const role = event.target.dataset.role;

  if (role === "indicator") {
    const indicator = indicatorById(event.target.value);
    const existing = state.conditions[index];
    state.conditions[index] = {
      indicator: indicator.id,
      operator: indicator.operators[0].id,
      value: indicator.operators[0].needsValue ? indicator.defaultValue : null,
      timeframe: existing?.timeframe || state.timeframe,
    };
    renderConditions();
  }

  if (role === "operator") {
    const indicator = indicatorById(state.conditions[index].indicator);
    const operator = operatorById(indicator, event.target.value);
    state.conditions[index].operator = operator.id;
    state.conditions[index].value = operator.needsValue ? (state.conditions[index].value ?? indicator.defaultValue ?? "") : null;
    renderConditions();
  }

  if (role === "timeframe") {
    state.conditions[index].timeframe = event.target.value;
  }
}

function onConditionInput(event) {
  const row = event.target.closest("[data-condition-index]");
  if (!row || event.target.dataset.role !== "value") return;
  state.conditions[Number(row.dataset.conditionIndex)].value = event.target.value;
}

function onConditionClick(event) {
  const row = event.target.closest("[data-condition-index]");
  if (!row || event.target.dataset.role !== "remove") return;
  state.conditions.splice(Number(row.dataset.conditionIndex), 1);
  if (!state.conditions.length) state.conditions.push(defaultCondition());
  renderConditions();
}

function indicatorById(id) {
  return (state.metadata?.indicatorGroups || [])
    .flatMap((group) => group.indicators)
    .find((indicator) => indicator.id === id);
}

function firstIndicator() {
  return state.metadata.indicatorGroups[0].indicators[0];
}

function operatorById(indicator, id) {
  return indicator?.operators.find((operator) => operator.id === id);
}

function defaultCondition() {
  const indicator = firstIndicator();
  const operator = indicator.operators[0];
  return {
    indicator: indicator.id,
    operator: operator.id,
    value: operator.needsValue ? indicator.defaultValue : null,
    timeframe: normalizeTimeframeId(state.timeframe),
  };
}

function setLogic(logic) {
  state.logic = logic;
  elements.andLogic.classList.toggle("active", logic === "AND");
  elements.orLogic.classList.toggle("active", logic === "OR");
}

function applyPreset(presetId) {
  const preset = presetById(presetId);
  if (!preset) return;
  state.instrumentTypes = [...preset.instrumentTypes];
  state.sectors = [...preset.sectors];
  state.timeframe = normalizeTimeframeId(preset.timeframe || state.timeframe);
  state.conditions = preset.conditions.map((condition) => cloneConditionWithFallback(condition, state.timeframe));
  setLogic(preset.logic);
  renderUniverseControls();
  renderConditions();
}

function presetById(presetId) {
  return state.metadata?.presets.find((preset) => preset.id === presetId);
}

function cloneCondition(condition) {
  return cloneConditionWithFallback(condition, state.timeframe);
}

function cloneConditionWithFallback(condition, fallbackTimeframe) {
  return {
    indicator: condition.indicator,
    operator: condition.operator,
    value: condition.value,
    timeframe: normalizeTimeframeId(condition.timeframe || fallbackTimeframe),
  };
}

async function runScan({ manual = false } = {}) {
  if (!state.metadata || state.isLoading) return;
  setLoading(true, manual);
  try {
    const response = await fetch("/api/indicator-screener/scan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(currentScanConfig()),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || "Unable to run indicator screener.");

    state.rows = Array.isArray(data.rows) ? data.rows : [];
    state.summary = data.summary || null;
    state.scan = data.scan || currentScanConfig();
    state.generatedAt = data.generated_at;
    state.refreshInterval = data.refresh_interval_seconds || 60;
    elements.scanLatency.textContent = data.elapsed_ms ? `${data.elapsed_ms} ms` : "--";
    elements.lastUpdated.textContent = formatDateTime(data.generated_at);
    state.page = 1;
    setMessage(data.warnings?.length ? data.warnings.join(" | ") : "");
    renderSummary();
    renderResults();
  } catch (error) {
    setMessage(error.message);
  } finally {
    setLoading(false);
    scheduleNextRefresh();
  }
}

function currentScanConfig() {
  return {
    instrumentTypes: state.instrumentTypes,
    sectors: state.sectors,
    timeframe: normalizeTimeframeId(state.timeframe),
    logic: state.logic,
    conditions: state.conditions.map((condition) => cloneConditionWithFallback(condition, state.timeframe)),
  };
}

function setLoading(isLoading, manual = false) {
  state.isLoading = isLoading;
  elements.runScan.disabled = isLoading;
  elements.refreshScan.disabled = isLoading;
  elements.runScan.textContent = isLoading ? "Scanning..." : "Run Scan";
  elements.refreshScan.textContent = isLoading ? "Scanning..." : "Refresh Now";
  if (isLoading) {
    elements.tableStatus.textContent = manual ? "Scanning selected F&O universe..." : "Refreshing scanner...";
    if (!state.rows.length) {
      elements.tableBody.innerHTML = '<tr><td colspan="13">Loading live candle data and indicator signals...</td></tr>';
    }
  }
  updateExportState();
}

function scheduleNextRefresh() {
  window.clearTimeout(state.refreshTimer);
  if (!elements.autoRefresh.checked || !state.scan) {
    state.nextRefreshAt = null;
    renderCountdown();
    return;
  }
  state.nextRefreshAt = Date.now() + state.refreshInterval * 1000;
  state.refreshTimer = window.setTimeout(() => runScan(), state.refreshInterval * 1000);
  renderCountdown();
}

function renderCountdown() {
  if (!state.nextRefreshAt) {
    elements.nextRefresh.textContent = "--";
    return;
  }
  if (state.isLoading) {
    elements.nextRefresh.textContent = "Refreshing...";
    return;
  }
  const seconds = Math.max(0, Math.ceil((state.nextRefreshAt - Date.now()) / 1000));
  elements.nextRefresh.textContent = `${seconds}s`;
}

function renderSummary() {
  const summary = state.summary || {};
  elements.totalStocksScanned.textContent = formatInteger(summary.totalStocksScanned || 0);
  elements.matchingResults.textContent = formatInteger(summary.matchingResults || 0);
  elements.bullishSignals.textContent = formatInteger(summary.bullishSignals || 0);
  elements.bearishSignals.textContent = formatInteger(summary.bearishSignals || 0);
  elements.strongestMomentumStock.textContent = formatSummaryStock(summary.strongestMomentumStock);
  elements.highestAdxStock.textContent = formatSummaryStock(summary.highestAdxStock);
  elements.highestVolumeBreakout.textContent = formatSummaryStock(summary.highestVolumeBreakout);
}

function renderResults() {
  const preparedRows = prepareRows();
  const totalRows = preparedRows.length;
  const pageSize = state.pageSize === "all" ? Math.max(totalRows, 1) : state.pageSize;
  const totalPages = Math.max(1, Math.ceil(totalRows / pageSize));
  state.page = Math.min(state.page, totalPages);

  const start = (state.page - 1) * pageSize;
  const pageRows = preparedRows.slice(start, start + pageSize);
  elements.tableBody.innerHTML = pageRows.length
    ? pageRows.map(renderRow).join("")
    : '<tr><td colspan="13">No stocks match the selected screener filters.</td></tr>';

  elements.rowCount.textContent = `${formatInteger(totalRows)} rows`;
  if (!state.rows.length) {
    elements.tableStatus.textContent = "No matching stocks loaded.";
  } else {
    elements.tableStatus.textContent = `Showing ${formatInteger(start + 1)}-${formatInteger(Math.min(start + pageRows.length, totalRows))} of ${formatInteger(totalRows)} matches`;
  }
  elements.pageInfo.textContent = `Page ${state.page} of ${totalPages}`;
  elements.prevPage.disabled = state.page <= 1;
  elements.nextPage.disabled = state.page >= totalPages;
  updateExportState();
}

function prepareRows() {
  return state.rows
    .filter(matchesSearch)
    .filter(matchesSignal)
    .sort((left, right) => sortValue(right, state.sort) - sortValue(left, state.sort) || left.symbol.localeCompare(right.symbol));
}

function matchesSearch(row) {
  if (!state.search) return true;
  return [
    row.symbol,
    row.stockName,
    row.sector,
    row.instrumentType,
    row.signalBias,
    row.signalStrength,
    row.fyersSymbol,
  ].join(" ").toUpperCase().includes(state.search);
}

function matchesSignal(row) {
  return state.signalFilter === "all" || row.signalBias === state.signalFilter;
}

function sortValue(row, key) {
  const value = row[key];
  if (key === "signalScore") return Math.abs(Number(value) || 0);
  return Number.isFinite(Number(value)) ? Number(value) : -Infinity;
}

function renderRow(row) {
  const signalClass = signalToneClass(row.signalBias);
  return `
    <tr>
      <td>
        <div class="stock-cell">
          <strong>${escapeHtml(row.symbol)}</strong>
          <span>${escapeHtml(row.stockName)}</span>
          <small>${escapeHtml(row.fyersSymbol)}</small>
        </div>
      </td>
      <td>${escapeHtml(row.sector)}</td>
      <td>${escapeHtml(row.instrumentType)}${row.expiry ? `<small class="expiry-note">${escapeHtml(row.expiry)}</small>` : ""}</td>
      <td>${formatNumber(row.currentPrice)}</td>
      <td>${formatNumber(row.rsi)}</td>
      <td>${formatNumber(row.adx)}</td>
      <td>${statusPill(row.supertrendStatus)}</td>
      <td>${statusPill(row.vwapStatus)}</td>
      <td>${statusPill(row.bollingerStatus)}</td>
      <td><span class="signal-badge ${signalClass}">${escapeHtml(row.signalStrength)}</span></td>
      <td>${escapeHtml(row.timeframe)}</td>
      <td>${formatInteger(row.volume)}</td>
      <td>${formatDateTime(row.lastUpdated)}</td>
    </tr>
  `;
}

function statusPill(value) {
  return `<span class="status-pill ${signalToneClass(value)}">${escapeHtml(value || "Neutral")}</span>`;
}

function signalToneClass(value) {
  const text = String(value || "").toLowerCase();
  if (text.includes("bull") || text.includes("above") || text.includes("upper breakout")) return "bullish";
  if (text.includes("bear") || text.includes("below") || text.includes("lower")) return "bearish";
  return "neutral";
}

async function exportResults(format) {
  const rows = prepareRows();
  if (!rows.length) return;
  try {
    const response = await fetch("/api/indicator-screener/export", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        rows,
        scan: state.scan || currentScanConfig(),
        generated_at: state.generatedAt,
        format,
      }),
    });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(data.error || "Unable to export screener results.");
    }
    const blob = await response.blob();
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = filenameFromDisposition(response.headers.get("Content-Disposition")) || `Advanced_FO_Indicator_Screener.${format === "csv" ? "csv" : "xlsx"}`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(link.href);
  } catch (error) {
    setMessage(error.message);
  }
}

function filenameFromDisposition(disposition) {
  if (!disposition) return "";
  const match = disposition.match(/filename="?([^"]+)"?/i);
  return match?.[1] || "";
}

function updateExportState() {
  const disabled = state.isLoading || !state.rows.length;
  elements.exportExcel.disabled = disabled;
  elements.exportCsv.disabled = disabled;
}

function saveCurrentScan() {
  const name = elements.saveScanName.value.trim();
  if (!name) {
    setMessage("Enter a scanner name before saving.");
    return;
  }
  const saved = readSavedScans();
  saved[name] = currentScanConfig();
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(saved));
  elements.saveScanName.value = "";
  renderSavedScans(name);
  setMessage(`Saved scanner: ${name}`);
}

function loadSelectedScan() {
  const name = elements.savedScanSelect.value;
  const scan = readSavedScans()[name];
  if (!scan) return;
  state.instrumentTypes = scan.instrumentTypes || ["spot"];
  state.sectors = scan.sectors || ["All Sectors"];
  state.timeframe = normalizeTimeframeId(scan.timeframe || "5");
  state.conditions = (scan.conditions || []).map((condition) => cloneConditionWithFallback(condition, state.timeframe));
  setLogic(scan.logic || "AND");
  renderUniverseControls();
  renderConditions();
  setMessage(`Loaded scanner: ${name}`);
}

function deleteSelectedScan() {
  const name = elements.savedScanSelect.value;
  if (!name) return;
  const saved = readSavedScans();
  delete saved[name];
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(saved));
  renderSavedScans();
  setMessage(`Deleted scanner: ${name}`);
}

function readSavedScans() {
  try {
    return JSON.parse(window.localStorage.getItem(STORAGE_KEY) || "{}");
  } catch {
    return {};
  }
}

function renderSavedScans(selectedName = "") {
  const saved = readSavedScans();
  const names = Object.keys(saved).sort();
  elements.savedScanSelect.innerHTML = names.length
    ? names.map((name) => `<option value="${escapeHtml(name)}">${escapeHtml(name)}</option>`).join("")
    : '<option value="">No saved scans</option>';
  if (selectedName && saved[selectedName]) elements.savedScanSelect.value = selectedName;
  elements.loadScan.disabled = !names.length;
  elements.deleteScan.disabled = !names.length;
}

function setMessage(message) {
  elements.message.hidden = !message;
  elements.message.textContent = message || "";
}

function formatSummaryStock(stock) {
  if (!stock) return "--";
  const value = Number.isFinite(Number(stock.value)) ? ` ${Number(stock.value).toFixed(2)}` : "";
  return `${stock.symbol}${value}`;
}

function formatNumber(value, digits = 2) {
  if (!Number.isFinite(Number(value))) return "--";
  return Number(value).toLocaleString("en-IN", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function formatInteger(value) {
  if (!Number.isFinite(Number(value))) return "--";
  return Number(value).toLocaleString("en-IN", { maximumFractionDigits: 0 });
}

function formatDateTime(value) {
  if (!value) return "--";
  return new Date(value).toLocaleString("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
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

function normalizeTimeframeId(value) {
  const raw = String(value ?? "").trim().toUpperCase();
  if (!raw) return "5";
  return TIMEFRAME_ALIASES[raw] || raw;
}
