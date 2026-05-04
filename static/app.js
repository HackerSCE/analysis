const analyzeBtn = document.getElementById("analyzeBtn");
const downloadBtn = document.getElementById("downloadBtn");
const symbolInput = document.getElementById("symbolInput");
const dateFromInput = document.getElementById("dateFromInput");
const dateToInput = document.getElementById("dateToInput");
const sessionStartInput = document.getElementById("sessionStartInput");
const signalStartInput = document.getElementById("signalStartInput");
const sessionExitInput = document.getElementById("sessionExitInput");
const emptyState = document.getElementById("emptyState");
const tradesBody = document.getElementById("tradesBody");
const logoutBtn = document.getElementById("logoutBtn");
let latestAnalysis = null;

analyzeBtn.addEventListener("click", analyze);
downloadBtn.addEventListener("click", downloadExcel);
symbolInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter") analyze();
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
