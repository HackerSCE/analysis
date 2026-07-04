export function downloadAnalyticsWorkbook(rows, summary, generatedAt) {
  const XLSX = window.XLSX;
  if (!XLSX) {
    throw new Error("Excel export library is still loading. Try again in a moment.");
  }

  const exportedAt = new Date().toISOString();
  const dataRows = rows.map((row) => ({
    "Timestamp": generatedAt || exportedAt,
    "NSE Stock Name": `${row.symbol} - ${row.stockName}`,
    "Spot Price": row.spotPrice,
    "Near Month Future Price": row.nearFuturePrice,
    "Next Month Future Price": row.nextFuturePrice,
    "Far Month Future Price": row.farFuturePrice,
    "% Difference (Near Future - Spot)": row.nearDiffPct,
    "% Difference (Next Future - Spot)": row.nextDiffPct,
    "% Difference (Far Future - Spot)": row.farDiffPct,
    "Lot Size": row.lotSize,
    "Contract Value": row.contractValue,
    "Spot Symbol": row.spotSymbol,
    "Near Future Symbol": row.nearFutureSymbol,
    "Next Future Symbol": row.nextFutureSymbol,
    "Far Future Symbol": row.farFutureSymbol,
    "Quote Status": row.quoteStatus,
  }));

  const summaryRows = [
    { "Metric": "Exported At", "Value": exportedAt },
    { "Metric": "Data Timestamp", "Value": generatedAt || "" },
    { "Metric": "Total Stocks", "Value": summary?.totalStocks ?? rows.length },
    { "Metric": "Average Near Premium %", "Value": summary?.averageNearPremiumPct ?? "" },
    { "Metric": "Highest Premium Stock", "Value": formatSummaryStock(summary?.highestPremiumStock) },
    { "Metric": "Highest Discount Stock", "Value": formatSummaryStock(summary?.highestDiscountStock) },
    { "Metric": "Total Market Contract Value", "Value": summary?.totalMarketContractValue ?? "" },
  ];

  const workbook = XLSX.utils.book_new();
  const dataSheet = XLSX.utils.json_to_sheet(dataRows);
  const summarySheet = XLSX.utils.json_to_sheet(summaryRows);
  applyDataFormats(XLSX, dataSheet, dataRows.length);

  dataSheet["!cols"] = [
    { wch: 24 },
    { wch: 34 },
    { wch: 14 },
    { wch: 22 },
    { wch: 22 },
    { wch: 22 },
    { wch: 28 },
    { wch: 28 },
    { wch: 28 },
    { wch: 10 },
    { wch: 18 },
    { wch: 20 },
    { wch: 24 },
    { wch: 24 },
    { wch: 24 },
    { wch: 28 },
  ];
  summarySheet["!cols"] = [{ wch: 30 }, { wch: 34 }];

  XLSX.utils.book_append_sheet(workbook, dataSheet, "NSE F&O Analytics");
  XLSX.utils.book_append_sheet(workbook, summarySheet, "Summary");
  XLSX.writeFile(workbook, `NSE_FO_Analytics_${filenameTimestamp(exportedAt)}.xlsx`);
}

function formatSummaryStock(stock) {
  if (!stock) return "";
  return `${stock.symbol} (${Number(stock.value).toFixed(2)}%)`;
}

function filenameTimestamp(value) {
  return value.replace(/[-:]/g, "").replace(/\..+$/, "").replace("T", "_");
}

function applyDataFormats(XLSX, sheet, rowCount) {
  const priceColumns = [2, 3, 4, 5, 10];
  const percentColumns = [6, 7, 8];
  const integerColumns = [9];

  for (let rowIndex = 1; rowIndex <= rowCount; rowIndex += 1) {
    priceColumns.forEach((columnIndex) => setCellFormat(XLSX, sheet, rowIndex, columnIndex, "#,##0.00"));
    percentColumns.forEach((columnIndex) => setCellFormat(XLSX, sheet, rowIndex, columnIndex, "0.00"));
    integerColumns.forEach((columnIndex) => setCellFormat(XLSX, sheet, rowIndex, columnIndex, "0"));
  }
}

function setCellFormat(XLSX, sheet, rowIndex, columnIndex, format) {
  const cellRef = XLSX.utils.encode_cell({ r: rowIndex, c: columnIndex });
  if (sheet[cellRef]) {
    sheet[cellRef].z = format;
  }
}
