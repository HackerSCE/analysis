import {
  REFRESH_INTERVAL_SECONDS,
  formatCurrency,
  formatDateTime,
  formatInteger,
  formatNumber,
  formatPercent,
  percentClass,
  sortValue,
} from "./analytics/calculations.js";
import { downloadAnalyticsWorkbook } from "./analytics/excelExport.js";

const elements = {
  tableBody: document.getElementById("analyticsTableBody"),
  tableStatus: document.getElementById("tableStatus"),
  rowCount: document.getElementById("rowCount"),
  lastUpdated: document.getElementById("lastUpdated"),
  nextRefresh: document.getElementById("nextRefresh"),
  refreshBtn: document.getElementById("refreshBtn"),
  downloadBtn: document.getElementById("downloadAnalyticsBtn"),
  searchInput: document.getElementById("stockSearchInput"),
  premiumFilter: document.getElementById("premiumFilterSelect"),
  sortColumn: document.getElementById("sortColumnSelect"),
  sortDirection: document.getElementById("sortDirectionSelect"),
  pageSize: document.getElementById("pageSizeSelect"),
  prevPage: document.getElementById("prevPageBtn"),
  nextPage: document.getElementById("nextPageBtn"),
  pageInfo: document.getElementById("pageInfo"),
  error: document.getElementById("analyticsError"),
  logoutBtn: document.getElementById("logoutBtn"),
  totalStocks: document.getElementById("totalStocks"),
  averageNearPremium: document.getElementById("averageNearPremium"),
  highestPremiumStock: document.getElementById("highestPremiumStock"),
  highestDiscountStock: document.getElementById("highestDiscountStock"),
  totalMarketContractValue: document.getElementById("totalMarketContractValue"),
};

const state = {
  rows: [],
  summary: null,
  generatedAt: null,
  source: null,
  search: "",
  dropdownFilter: "all",
  sortColumn: "nearDiffPct",
  sortDirection: "desc",
  quickFilter: "all",
  pageSize: 50,
  page: 1,
  isLoading: false,
  refreshInterval: REFRESH_INTERVAL_SECONDS,
  nextRefreshAt: null,
  refreshTimer: null,
  countdownTimer: null,
};

wireEvents();
loadAnalytics();
state.countdownTimer = window.setInterval(renderCountdown, 1000);

function wireEvents() {
  elements.refreshBtn.addEventListener("click", () => loadAnalytics({ manual: true }));
  elements.downloadBtn.addEventListener("click", downloadExcel);
  elements.searchInput.addEventListener("input", () => {
    state.search = elements.searchInput.value.trim().toUpperCase();
    state.page = 1;
    render();
  });
  elements.premiumFilter.addEventListener("change", () => {
    state.dropdownFilter = elements.premiumFilter.value;
    state.page = 1;
    render();
  });
  elements.sortColumn.addEventListener("change", () => {
    state.sortColumn = elements.sortColumn.value;
    state.quickFilter = "all";
    state.page = 1;
    setQuickFilterActive();
    render();
  });
  elements.sortDirection.addEventListener("change", () => {
    state.sortDirection = elements.sortDirection.value;
    state.quickFilter = "all";
    state.page = 1;
    setQuickFilterActive();
    render();
  });
  elements.pageSize.addEventListener("change", () => {
    state.pageSize = elements.pageSize.value === "all" ? "all" : Number(elements.pageSize.value);
    state.page = 1;
    render();
  });
  elements.prevPage.addEventListener("click", () => {
    state.page = Math.max(1, state.page - 1);
    render();
  });
  elements.nextPage.addEventListener("click", () => {
    state.page += 1;
    render();
  });
  document.querySelectorAll(".quick-filter").forEach((button) => {
    button.addEventListener("click", () => {
      applyQuickFilter(button.dataset.filter);
    });
  });

  if (elements.logoutBtn) {
    elements.logoutBtn.addEventListener("click", async () => {
      await fetch("/logout", { method: "POST" });
      window.location.href = "/";
    });
  }
}

async function loadAnalytics({ manual = false } = {}) {
  setLoading(true, manual);
  try {
    const response = await fetch("/api/nse-fno-analytics", { cache: "no-store" });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || "Unable to load NSE F&O analytics.");

    state.rows = Array.isArray(data.rows) ? data.rows : [];
    state.summary = data.summary || null;
    state.generatedAt = data.generated_at;
    state.source = data.source || null;
    state.refreshInterval = data.refresh_interval_seconds || REFRESH_INTERVAL_SECONDS;
    state.nextRefreshAt = Date.now() + state.refreshInterval * 1000;
    hideMessage();
    if (data.warnings?.length) {
      showMessage(data.warnings.join(" | "));
    }
    render();
  } catch (error) {
    showMessage(error.message || "Unable to load NSE F&O analytics.");
  } finally {
    setLoading(false);
    scheduleNextRefresh();
  }
}

function setLoading(isLoading, manual = false) {
  state.isLoading = isLoading;
  elements.refreshBtn.disabled = isLoading;
  elements.refreshBtn.textContent = isLoading ? "Refreshing..." : "Refresh Now";
  elements.downloadBtn.disabled = isLoading || state.rows.length === 0;
  if (isLoading) {
    elements.tableStatus.textContent = manual ? "Refreshing live FYERS quotes..." : "Loading live FYERS quotes...";
    if (!state.rows.length) {
      elements.tableBody.innerHTML = '<tr><td colspan="10">Loading live FYERS quotes...</td></tr>';
    }
  }
}

function scheduleNextRefresh() {
  window.clearTimeout(state.refreshTimer);
  state.nextRefreshAt = Date.now() + state.refreshInterval * 1000;
  state.refreshTimer = window.setTimeout(() => loadAnalytics(), state.refreshInterval * 1000);
  renderCountdown();
}

function render() {
  renderSummary();
  renderMetadata();
  renderTable();
  renderCountdown();
  elements.downloadBtn.disabled = state.isLoading || state.rows.length === 0;
}

function renderSummary() {
  const summary = state.summary || {};
  elements.totalStocks.textContent = formatInteger(summary.totalStocks ?? state.rows.length);
  elements.averageNearPremium.textContent = formatPercent(summary.averageNearPremiumPct ?? 0);
  elements.highestPremiumStock.textContent = formatSummaryStock(summary.highestPremiumStock);
  elements.highestDiscountStock.textContent = formatSummaryStock(summary.highestDiscountStock);
  elements.totalMarketContractValue.textContent = formatCurrency(summary.totalMarketContractValue ?? 0, true);
}

function renderMetadata() {
  elements.lastUpdated.textContent = formatDateTime(state.generatedAt);
}

function renderTable() {
  const preparedRows = prepareRows();
  const totalRows = preparedRows.length;
  const pageSize = state.pageSize === "all" ? Math.max(totalRows, 1) : state.pageSize;
  const totalPages = Math.max(1, Math.ceil(totalRows / pageSize));
  state.page = Math.min(state.page, totalPages);

  const start = (state.page - 1) * pageSize;
  const pageRows = preparedRows.slice(start, start + pageSize);
  elements.tableBody.innerHTML = pageRows.length
    ? pageRows.map(renderRow).join("")
    : '<tr><td colspan="10">No stocks match the selected filters.</td></tr>';

  elements.rowCount.textContent = `${formatInteger(totalRows)} rows`;
  if (!state.rows.length) {
    elements.tableStatus.textContent = "No live rows loaded.";
  } else if (!totalRows) {
    elements.tableStatus.textContent = "No stocks match the selected filters.";
  } else {
    elements.tableStatus.textContent = `Showing ${formatInteger(start + 1)}-${formatInteger(Math.min(start + pageRows.length, totalRows))} of ${formatInteger(totalRows)} stocks`;
  }
  elements.pageInfo.textContent = `Page ${state.page} of ${totalPages}`;
  elements.prevPage.disabled = state.page <= 1;
  elements.nextPage.disabled = state.page >= totalPages;
}

function prepareRows() {
  let rows = state.rows.filter(matchesSearch).filter(matchesDropdownFilter);

  if (state.quickFilter !== "all") {
    rows = applyQuickFilterResult(rows);
  } else {
    rows = sortRows(rows, state.sortColumn, state.sortDirection);
  }

  return rows;
}

function matchesSearch(row) {
  if (!state.search) return true;
  return `${row.symbol} ${row.stockName}`.toUpperCase().includes(state.search);
}

function matchesDropdownFilter(row) {
  switch (state.dropdownFilter) {
    case "nearPremium":
      return Number(row.nearDiffPct) > 0;
    case "nearDiscount":
      return Number(row.nearDiffPct) < 0;
    case "allPremium":
      return [row.nearDiffPct, row.nextDiffPct, row.farDiffPct].every((value) => Number(value) > 0);
    case "allDiscount":
      return [row.nearDiffPct, row.nextDiffPct, row.farDiffPct].every((value) => Number(value) < 0);
    default:
      return true;
  }
}

function sortRows(rows, key, direction) {
  const multiplier = direction === "asc" ? 1 : -1;
  return [...rows].sort((a, b) => {
    const aValue = sortValue(a, key);
    const bValue = sortValue(b, key);
    if (aValue === null && bValue === null) return a.symbol.localeCompare(b.symbol);
    if (aValue === null) return 1;
    if (bValue === null) return -1;
    return (aValue - bValue) * multiplier || a.symbol.localeCompare(b.symbol);
  });
}

function applyQuickFilter(filter) {
  state.quickFilter = filter;
  state.page = 1;

  const quickSorts = {
    topPremium: ["nearDiffPct", "desc"],
    highestDiscount: ["nearDiffPct", "asc"],
    highestContractValue: ["contractValue", "desc"],
    lowestContractValue: ["contractValue", "asc"],
  };
  if (quickSorts[filter]) {
    const [column, direction] = quickSorts[filter];
    state.sortColumn = column;
    state.sortDirection = direction;
    elements.sortColumn.value = column;
    elements.sortDirection.value = direction;
  }

  setQuickFilterActive();
  render();
}

function applyQuickFilterResult(rows) {
  switch (state.quickFilter) {
    case "topPremium":
      return sortRows(rows, "nearDiffPct", "desc").slice(0, 25);
    case "highestDiscount":
      return sortRows(rows, "nearDiffPct", "asc").slice(0, 25);
    case "highestContractValue":
      return sortRows(rows, "contractValue", "desc").slice(0, 25);
    case "lowestContractValue":
      return sortRows(rows, "contractValue", "asc").slice(0, 25);
    default:
      return sortRows(rows, state.sortColumn, state.sortDirection);
  }
}

function setQuickFilterActive() {
  document.querySelectorAll(".quick-filter").forEach((button) => {
    button.classList.toggle("active", button.dataset.filter === state.quickFilter);
  });
}

function renderRow(row) {
  return `
    <tr title="${escapeHtml(row.quoteStatus || "")}">
      <td>
        <div class="stock-cell">
          <strong>${escapeHtml(row.symbol)}</strong>
          <span>${escapeHtml(row.stockName)}</span>
          <small>${escapeHtml(row.spotSymbol)}</small>
        </div>
      </td>
      <td>${formatNumber(row.spotPrice)}</td>
      ${renderFutureCell(row.nearFuturePrice, row.nearFutureSymbol, row.nearFutureExpiry)}
      ${renderFutureCell(row.nextFuturePrice, row.nextFutureSymbol, row.nextFutureExpiry)}
      ${renderFutureCell(row.farFuturePrice, row.farFutureSymbol, row.farFutureExpiry)}
      ${renderPercentCell(row.nearDiffPct)}
      ${renderPercentCell(row.nextDiffPct)}
      ${renderPercentCell(row.farDiffPct)}
      <td>${formatInteger(row.lotSize)}</td>
      <td>${formatCurrency(row.contractValue)}</td>
    </tr>
  `;
}

function renderFutureCell(price, symbol, expiry) {
  return `
    <td>
      <div class="future-cell">
        <strong>${formatNumber(price)}</strong>
        <span>${escapeHtml(expiry || "--")}</span>
        <small>${escapeHtml(symbol || "")}</small>
      </div>
    </td>
  `;
}

function renderPercentCell(value) {
  return `<td class="${percentClass(value)}">${formatPercent(value)}</td>`;
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

function downloadExcel() {
  try {
    downloadAnalyticsWorkbook(state.rows, state.summary, state.generatedAt);
  } catch (error) {
    showMessage(error.message);
  }
}

function showMessage(message) {
  elements.error.hidden = false;
  elements.error.textContent = message;
}

function hideMessage() {
  elements.error.hidden = true;
  elements.error.textContent = "";
}

function formatSummaryStock(stock) {
  if (!stock) return "--";
  return `${stock.symbol} ${formatPercent(stock.value)}`;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
