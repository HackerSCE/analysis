import {
  formatCurrency,
  formatDateTime,
  formatInteger,
  formatPercent,
  percentClass,
} from "./analytics/calculations.js";

const elements = {
  shell: document.querySelector(".arbitrage-shell"),
  metadataStatus: document.getElementById("metadataStatus"),
  calculatedAt: document.getElementById("calculatedAt"),
  nextRefresh: document.getElementById("nextRefresh"),
  marketType: document.getElementById("marketTypeSelect"),
  buyStock: document.getElementById("buyStockInput"),
  sellFuture: document.getElementById("sellFutureInput"),
  buyExpiry: document.getElementById("buyFutureExpirySelect"),
  sellExpiry: document.getElementById("futureExpirySelect"),
  buyExpiryField: document.getElementById("buyExpiryField"),
  lots: document.getElementById("lotsInput"),
  commodityClass: document.getElementById("commodityClassSelect"),
  commodityClassField: document.getElementById("commodityClassField"),
  settlementPrice: document.getElementById("settlementPriceInput"),
  settlementPriceField: document.getElementById("settlementPriceField"),
  buyInstrumentLabel: document.getElementById("buyInstrumentLabel"),
  sellInstrumentLabel: document.getElementById("sellInstrumentLabel"),
  sellExpiryLabel: document.getElementById("sellExpiryLabel"),
  calculate: document.getElementById("calculateArbitrageBtn"),
  instrumentOptions: document.getElementById("arbitrageInstrumentOptions"),
  chargeRulesDescription: document.getElementById("chargeRulesDescription"),
  chargeRulesList: document.getElementById("chargeRulesList"),
  message: document.getElementById("arbitrageMessage"),
  cashRequiredLabel: document.getElementById("cashRequiredLabel"),
  netProfitLabel: document.getElementById("netProfitLabel"),
  netReturnLabel: document.getElementById("netReturnLabel"),
  annualizedReturnLabel: document.getElementById("annualizedReturnLabel"),
  totalChargesLabel: document.getElementById("totalChargesLabel"),
  cashRequired: document.getElementById("cashRequired"),
  netProfit: document.getElementById("netProfit"),
  netReturn: document.getElementById("netReturn"),
  annualizedReturn: document.getElementById("annualizedReturn"),
  totalCharges: document.getElementById("totalCharges"),
  selectedContract: document.getElementById("selectedContract"),
  chargeTotalMeta: document.getElementById("chargeTotalMeta"),
  snapshotBody: document.getElementById("tradeSnapshotBody"),
  chargesBody: document.getElementById("chargesBreakdownBody"),
  logoutBtn: document.getElementById("logoutBtn"),
};

const state = {
  symbols: { equity: [], commodity: [] },
  chargeRules: { equity: [], commodity: [] },
  refreshInterval: 30,
  isLoading: false,
  hasCalculated: false,
  refreshTimer: null,
  countdownTimer: null,
  nextRefreshAt: null,
};

wireEvents();
loadMetadata();

function wireEvents() {
  elements.marketType.addEventListener("change", () => {
    stopAutoRefresh();
    state.hasCalculated = false;
    setModeUI({ selectDefault: true });
    hideMessage();
  });
  elements.buyStock.addEventListener("change", handleBuyInstrumentChange);
  elements.sellFuture.addEventListener("input", renderExpiryOptions);
  elements.sellFuture.addEventListener("change", renderExpiryOptions);
  elements.calculate.addEventListener("click", () => calculateArbitrage());

  if (elements.logoutBtn) {
    elements.logoutBtn.addEventListener("click", async () => {
      await fetch("/logout", { method: "POST" });
      window.location.href = "/";
    });
  }

  document.addEventListener("visibilitychange", () => {
    if (!state.hasCalculated) return;
    if (document.hidden) {
      stopAutoRefresh({ keepStatus: true });
    } else {
      scheduleNextRefresh();
    }
  });
}

async function loadMetadata() {
  setLoading(true);
  elements.metadataStatus.textContent = "Loading...";
  try {
    const response = await fetch("/api/arbitrage/metadata", { cache: "no-store" });
    const metadata = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(metadata.error || "Unable to load calculator metadata.");

    state.symbols.equity = Array.isArray(metadata.equitySymbols) ? metadata.equitySymbols : [];
    state.symbols.commodity = Array.isArray(metadata.commoditySymbols) ? metadata.commoditySymbols : [];
    state.chargeRules = metadata.chargeRules || state.chargeRules;
    state.refreshInterval = Number(metadata.refresh_interval_seconds) || 30;
    setModeUI({ selectDefault: true });
    elements.metadataStatus.textContent = `${formatInteger(state.symbols.equity.length)} stocks · ${formatInteger(state.symbols.commodity.length)} commodities`;
    hideMessage();
  } catch (error) {
    showMessage(error.message || "Unable to load calculator metadata.");
    elements.metadataStatus.textContent = "Unavailable";
  } finally {
    setLoading(false);
    updateRefreshText();
  }
}

function currentMarketType() {
  return elements.marketType.value === "commodity" ? "commodity" : "equity";
}

function currentSymbols() {
  return state.symbols[currentMarketType()] || [];
}

function setModeUI({ selectDefault = false } = {}) {
  const commodity = currentMarketType() === "commodity";
  elements.buyExpiryField.hidden = !commodity;
  elements.commodityClassField.hidden = !commodity;
  elements.settlementPriceField.hidden = commodity;
  elements.buyInstrumentLabel.textContent = commodity ? "BUY Commodity" : "BUY Stock Name";
  elements.sellInstrumentLabel.textContent = commodity ? "SELL Commodity" : "SELL Stock Future";
  elements.sellExpiryLabel.textContent = commodity ? "SELL Future Expiry" : "SELL Future Expiry";
  elements.buyStock.placeholder = commodity ? "MCX:GOLD" : "RELIANCE";
  elements.sellFuture.placeholder = commodity ? "MCX:GOLD" : "RELIANCE";

  populateSymbolOptions();
  if (selectDefault) chooseDefaultSymbols();
  renderExpiryOptions();
  renderChargeRules();
  setMetricLabels(commodity);
  updateRefreshText();
}

function populateSymbolOptions() {
  elements.instrumentOptions.innerHTML = currentSymbols()
    .map((item) => {
      const exchange = item.exchange ? `${item.exchange} · ` : "";
      return `<option value="${escapeHtml(item.symbol)}" label="${escapeHtml(`${exchange}${item.stockName}`)}"></option>`;
    })
    .join("");
}

function chooseDefaultSymbols() {
  const symbols = currentSymbols();
  const preferred = currentMarketType() === "equity"
    ? (symbols.find((item) => item.symbol === "RELIANCE") || symbols[0])
    : (symbols.find((item) => item.symbol === "MCX:GOLD" && item.contracts.length >= 2)
      || symbols.find((item) => item.contracts.length >= 2)
      || symbols[0]);
  if (!preferred) {
    elements.buyStock.value = "";
    elements.sellFuture.value = "";
    return;
  }
  elements.buyStock.value = preferred.symbol;
  elements.sellFuture.value = preferred.symbol;
}

function handleBuyInstrumentChange() {
  const buyItem = findSymbol(elements.buyStock.value);
  if (buyItem && (!findSymbol(elements.sellFuture.value) || currentMarketType() === "commodity")) {
    elements.sellFuture.value = buyItem.symbol;
  }
  renderExpiryOptions();
}

function renderExpiryOptions() {
  const buyItem = findSymbol(elements.buyStock.value);
  const sellItem = findSymbol(elements.sellFuture.value) || buyItem;
  renderContractOptions(elements.buyExpiry, buyItem, "Select buy future first", true);
  renderContractOptions(elements.sellExpiry, sellItem, "Select sell future first", true);
}

function renderContractOptions(select, item, emptyText) {
  if (!item) {
    select.innerHTML = `<option value="">${emptyText}</option>`;
    return;
  }
  select.innerHTML = item.contracts
    .map((contract) => `
      <option value="${escapeHtml(contract.futureSymbol)}">
        ${escapeHtml(`${contract.expiry} · ${contract.futureSymbol}`)}
      </option>
    `)
    .join("");
}

function renderChargeRules(rules = null) {
  const commodity = currentMarketType() === "commodity";
  const currentRules = Array.isArray(rules) ? rules : (state.chargeRules[commodity ? "commodity" : "equity"] || []);
  elements.chargeRulesDescription.textContent = commodity
    ? "Commodity-futures charges are selected automatically from the contract exchange and commodity class."
    : "Cash-equity delivery and NSE stock-futures charges are applied automatically to every calculation.";
  elements.chargeRulesList.innerHTML = currentRules.map((rule) => `<li>${escapeHtml(rule)}</li>`).join("");
}

async function calculateArbitrage({ automatic = false } = {}) {
  if (state.isLoading) return;
  const commodity = currentMarketType() === "commodity";
  setLoading(true, automatic);
  try {
    const payload = {
      marketType: currentMarketType(),
      buySymbol: elements.buyStock.value.trim(),
      sellSymbol: elements.sellFuture.value.trim() || elements.buyStock.value.trim(),
      lots: elements.lots.value,
    };
    if (commodity) {
      payload.buyFutureContract = elements.buyExpiry.value;
      payload.sellFutureContract = elements.sellExpiry.value;
      payload.commodityClass = elements.commodityClass.value;
    } else {
      payload.futureExpiry = elements.sellExpiry.value;
      payload.settlementPrice = elements.settlementPrice.value || null;
    }

    const response = await fetch("/api/arbitrage/calculate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || "Unable to calculate the live difference.");

    state.hasCalculated = true;
    renderResult(data);
    if (data.warnings?.length) {
      showMessage(data.warnings.join(" | "));
    } else {
      hideMessage();
    }
  } catch (error) {
    showMessage(error.message || "Unable to calculate the live difference.");
  } finally {
    setLoading(false);
    if (state.hasCalculated && !document.hidden) scheduleNextRefresh();
  }
}

function renderResult(data) {
  const commodity = data.marketType === "commodity";
  elements.calculatedAt.textContent = formatDateTime(data.generated_at);
  setMetricLabels(commodity);
  setMetric(elements.cashRequired, formatCurrency(data.result?.cashRequired));
  setMetric(elements.netProfit, formatCurrency(data.result?.netProfit), data.result?.netProfit);
  setMetric(elements.netReturn, formatPercent(data.result?.netReturnPct), data.result?.netReturnPct);
  setMetric(
    elements.annualizedReturn,
    commodity ? formatCurrency(data.prices?.grossSpreadPerShare) : formatPercent(data.result?.annualizedNetReturnPct),
    commodity ? data.prices?.grossSpreadPerShare : data.result?.annualizedNetReturnPct,
  );
  setMetric(elements.totalCharges, formatCurrency(data.charges?.total));

  elements.selectedContract.textContent = commodity
    ? `${data.instruments?.buyFuture?.futureSymbol || "--"} → ${data.instruments?.sellFuture?.futureSymbol || "--"}`
    : (data.instruments?.sellFuture?.futureSymbol || "--");
  elements.chargeTotalMeta.textContent = formatCurrency(data.charges?.total);
  elements.snapshotBody.innerHTML = (commodity ? commoditySnapshotRows(data) : equitySnapshotRows(data))
    .map(renderKeyValueRow)
    .join("");
  elements.chargesBody.innerHTML = chargeRows(data).map(renderKeyValueRow).join("");
  renderChargeRules(data.chargeRules);
}

function setMetricLabels(commodity) {
  elements.cashRequiredLabel.textContent = commodity ? "Indicative Margin" : "Cash Required";
  elements.netProfitLabel.textContent = commodity ? "Net Difference" : "Expected Net Profit";
  elements.netReturnLabel.textContent = commodity ? "Net Difference %" : "Net Return";
  elements.annualizedReturnLabel.textContent = commodity ? "Spread / Unit" : "Annualized Return";
  elements.totalChargesLabel.textContent = commodity ? "Entry Charges" : "Total Charges";
}

function equitySnapshotRows(data) {
  return [
    ["Buy Stock", `${data.instruments.buyStock.symbol} - ${data.instruments.buyStock.stockName}`],
    ["Sell Future", `${data.instruments.sellFuture.futureSymbol} (${data.instruments.sellFuture.expiry})`],
    ["Lot Size / Shares", `${formatInteger(data.quantity.lotSize)} x ${formatInteger(data.quantity.lots)} = ${formatInteger(data.quantity.shares)}`],
    ["Spot Price", formatCurrency(data.prices.spotPrice)],
    ["Future Price", formatCurrency(data.prices.futurePrice)],
    ["Settlement Price", formatCurrency(data.prices.settlementPrice)],
    ["Gross Spread / Share", formatCurrency(data.prices.grossSpreadPerShare)],
    ["Break-even Spread / Share", formatCurrency(data.prices.breakEvenSpreadPerShare)],
    ["Gross Profit", formatCurrency(data.result.grossProfit)],
    ["Future Margin", formatCurrency(data.result.futureMargin)],
    ["Stock Buy Amount", formatCurrency(data.turnover.stockBuy)],
    ["Future Sell Notional", formatCurrency(data.turnover.futureSell)],
    ["Total Trade Value", formatCurrency(data.turnover.total)],
    ["Days To Expiry", data.quantity.daysToExpiry ?? "--"],
  ];
}

function commoditySnapshotRows(data) {
  const commodityClass = data.inputs.commodityClass === "agri" ? "Agri" : "Non-agri";
  return [
    ["Buy Commodity Future", `${data.instruments.buyFuture.futureSymbol} (${data.instruments.buyFuture.expiry})`],
    ["Sell Commodity Future", `${data.instruments.sellFuture.futureSymbol} (${data.instruments.sellFuture.expiry})`],
    ["Exchange / Commodity Class", `${data.instruments.buyFuture.exchange} / ${commodityClass}`],
    ["Lot Size / Quantity", `${formatInteger(data.quantity.lotSize)} x ${formatInteger(data.quantity.lots)} = ${formatInteger(data.quantity.shares)}`],
    ["Buy Future Price", formatCurrency(data.prices.buyFuturePrice)],
    ["Sell Future Price", formatCurrency(data.prices.sellFuturePrice)],
    ["Live Spread / Unit", formatCurrency(data.prices.grossSpreadPerShare)],
    ["Break-even Spread / Unit", formatCurrency(data.prices.breakEvenSpreadPerShare)],
    ["Gross Difference", formatCurrency(data.result.grossProfit)],
    ["Net Difference After Charges", formatCurrency(data.result.netProfit)],
    ["Indicative Margin", formatCurrency(data.result.futureMargin)],
    ["Total Futures Notional", formatCurrency(data.turnover.total)],
    ["Nearest Expiry In", `${data.quantity.daysToExpiry ?? "--"} days`],
  ];
}

function chargeRows(data) {
  const commodity = data.marketType === "commodity";
  const sections = commodity
    ? [
      ["Entry Charges", formatCurrency(data.charges.opening)],
      ["Total Entry Charges", formatCurrency(data.charges.total)],
    ]
    : [
      ["Opening Charges", formatCurrency(data.charges.opening)],
      ["Closing Charges", formatCurrency(data.charges.closing)],
      ["Total Charges", formatCurrency(data.charges.total)],
    ];
  const breakdown = (data.charges.breakdown || []).map((item) => [item.label, formatCurrency(item.amount)]);
  const legs = (data.charges.legs || []).map((item) => [item.label, formatCurrency(item.amount)]);
  return [...sections, ...breakdown, ...legs];
}

function renderKeyValueRow([label, value]) {
  return `
    <tr>
      <th>${escapeHtml(label)}</th>
      <td>${escapeHtml(value)}</td>
    </tr>
  `;
}

function setMetric(element, text, value = null) {
  element.textContent = text;
  element.classList.remove("profit", "loss");
  if (value !== null && Number.isFinite(Number(value))) {
    element.classList.add(percentClass(value));
  }
}

function findSymbol(value) {
  const needle = String(value || "").trim().toUpperCase();
  if (!needle) return null;
  return currentSymbols().find((item) => (
    item.symbol.toUpperCase() === needle
    || String(item.spotSymbol || "").toUpperCase() === needle
    || item.stockName.toUpperCase() === needle
    || item.stockName.toUpperCase().includes(needle)
  ));
}

function scheduleNextRefresh() {
  window.clearTimeout(state.refreshTimer);
  if (!state.hasCalculated || document.hidden) {
    updateRefreshText();
    return;
  }
  state.nextRefreshAt = Date.now() + state.refreshInterval * 1000;
  state.refreshTimer = window.setTimeout(
    () => calculateArbitrage({ automatic: true }),
    state.refreshInterval * 1000,
  );
  updateRefreshText();
}

function stopAutoRefresh({ keepStatus = false } = {}) {
  window.clearTimeout(state.refreshTimer);
  state.refreshTimer = null;
  state.nextRefreshAt = null;
  if (!keepStatus) updateRefreshText();
}

function updateRefreshText() {
  if (!state.hasCalculated) {
    elements.nextRefresh.textContent = "Calculate to start";
    return;
  }
  if (state.isLoading) {
    elements.nextRefresh.textContent = "Refreshing...";
    return;
  }
  if (document.hidden) {
    elements.nextRefresh.textContent = "Paused while tab is hidden";
    return;
  }
  if (!state.nextRefreshAt) {
    elements.nextRefresh.textContent = "Waiting";
    return;
  }
  const seconds = Math.max(0, Math.ceil((state.nextRefreshAt - Date.now()) / 1000));
  elements.nextRefresh.textContent = `${seconds}s`;
}

function setLoading(isLoading, automatic = false) {
  state.isLoading = isLoading;
  elements.calculate.disabled = isLoading;
  elements.calculate.textContent = isLoading ? (automatic ? "Refreshing..." : "Calculating...") : "Calculate";
  if (!state.countdownTimer) {
    state.countdownTimer = window.setInterval(updateRefreshText, 500);
  }
  updateRefreshText();
}

function showMessage(message) {
  elements.message.hidden = false;
  elements.message.textContent = message;
}

function hideMessage() {
  elements.message.hidden = true;
  elements.message.textContent = "";
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
