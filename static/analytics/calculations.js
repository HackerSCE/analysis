export const REFRESH_INTERVAL_SECONDS = 60;

const numberFormatter = new Intl.NumberFormat("en-IN", {
  maximumFractionDigits: 2,
});

const compactCurrencyFormatter = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  notation: "compact",
  maximumFractionDigits: 2,
});

const currencyFormatter = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  maximumFractionDigits: 2,
});

export function formatNumber(value, digits = 2) {
  if (!Number.isFinite(Number(value))) return "--";
  return Number(value).toLocaleString("en-IN", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

export function formatInteger(value) {
  if (!Number.isFinite(Number(value))) return "--";
  return numberFormatter.format(Number(value));
}

export function formatCurrency(value, compact = false) {
  if (!Number.isFinite(Number(value))) return "--";
  return compact ? compactCurrencyFormatter.format(Number(value)) : currencyFormatter.format(Number(value));
}

export function formatPercent(value) {
  if (!Number.isFinite(Number(value))) return "--";
  return `${Number(value).toFixed(2)}%`;
}

export function percentClass(value) {
  if (!Number.isFinite(Number(value))) return "";
  return Number(value) >= 0 ? "profit" : "loss";
}

export function sortValue(row, key) {
  const value = row[key];
  return Number.isFinite(Number(value)) ? Number(value) : null;
}

export function formatDateTime(value) {
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
