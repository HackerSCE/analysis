from __future__ import annotations

from dataclasses import dataclass
from datetime import time

import pandas as pd


SESSION_START = time(9, 15)
SIGNAL_START = time(9, 20)
SESSION_EXIT = time(15, 15)


@dataclass
class PendingSignal:
    side: str
    level: float
    signal_time: pd.Timestamp


def run_por_backtest(
    df: pd.DataFrame,
    session_start: time = SESSION_START,
    signal_start: time = SIGNAL_START,
    session_exit: time = SESSION_EXIT,
):
    trades = []
    equity = []
    cumulative_pnl = 0.0

    working = df.copy()
    working["date"] = working["datetime"].dt.date
    working["clock"] = working["datetime"].dt.time

    for _, day in working.groupby("date", sort=True):
        day = day[(day["clock"] >= session_start) & (day["clock"] <= session_exit)].reset_index(drop=True)
        if day.empty:
            continue

        ref = day[day["clock"] == session_start]
        if ref.empty:
            continue
        por = float(ref.iloc[0]["close"])

        position = None
        pending = None
        stop_pending = None

        for _, row in day.iterrows():
            clock = row["clock"]
            if clock < signal_start:
                continue

            if position is None:
                if pending is None:
                    if row["close"] > por:
                        pending = PendingSignal("LONG", float(row["high"]), row["datetime"])
                    elif row["close"] < por:
                        pending = PendingSignal("SHORT", float(row["low"]), row["datetime"])
                    continue

                if pending.side == "LONG" and row["close"] < por:
                    pending = PendingSignal("SHORT", float(row["low"]), row["datetime"])
                    continue
                if pending.side == "SHORT" and row["close"] > por:
                    pending = PendingSignal("LONG", float(row["high"]), row["datetime"])
                    continue

                if row["datetime"] <= pending.signal_time:
                    continue
                if pending.side == "LONG" and row["high"] > pending.level:
                    position = open_position("LONG", pending.level, row, por)
                    pending = None
                elif pending.side == "SHORT" and row["low"] < pending.level:
                    position = open_position("SHORT", pending.level, row, por)
                    pending = None
                continue

            if position["side"] == "LONG":
                if stop_pending is None and row["close"] < por:
                    stop_pending = {"level": float(row["low"]), "time": row["datetime"]}
                elif stop_pending and row["datetime"] > stop_pending["time"] and row["low"] < stop_pending["level"]:
                    cumulative_pnl = close_position(position, stop_pending["level"], row, "stop_loss", trades, cumulative_pnl)
                    equity.append(cumulative_pnl)
                    position = None
                    stop_pending = None
            else:
                if stop_pending is None and row["close"] > por:
                    stop_pending = {"level": float(row["high"]), "time": row["datetime"]}
                elif stop_pending and row["datetime"] > stop_pending["time"] and row["high"] > stop_pending["level"]:
                    cumulative_pnl = close_position(position, stop_pending["level"], row, "stop_loss", trades, cumulative_pnl)
                    equity.append(cumulative_pnl)
                    position = None
                    stop_pending = None

            if position is not None and clock >= session_exit:
                cumulative_pnl = close_position(position, float(row["close"]), row, "session_exit", trades, cumulative_pnl)
                equity.append(cumulative_pnl)
                position = None
                stop_pending = None

        if position is not None:
            last_row = day.iloc[-1]
            cumulative_pnl = close_position(position, float(last_row["close"]), last_row, "session_exit", trades, cumulative_pnl)
            equity.append(cumulative_pnl)

    metrics = calculate_metrics(trades, equity)
    return trades, metrics


def open_position(side, entry_price, row, por):
    return {
        "side": side,
        "entry_time": row["datetime"],
        "entry_price": float(entry_price),
        "por": float(por),
    }


def close_position(position, exit_price, row, reason, trades, cumulative_pnl):
    exit_price = float(exit_price)
    pnl = exit_price - position["entry_price"] if position["side"] == "LONG" else position["entry_price"] - exit_price
    trade = {
        "side": position["side"],
        "entry_time": position["entry_time"].isoformat(),
        "entry_price": round(position["entry_price"], 2),
        "exit_time": row["datetime"].isoformat(),
        "exit_price": round(exit_price, 2),
        "exit_reason": reason,
        "pnl": round(pnl, 2),
        "por": round(position["por"], 2),
    }
    trades.append(trade)
    return cumulative_pnl + pnl


def calculate_metrics(trades, equity):
    total = sum(t["pnl"] for t in trades)
    wins = [t for t in trades if t["pnl"] > 0]
    win_rate = (len(wins) / len(trades) * 100) if trades else 0.0

    peak = 0.0
    max_drawdown = 0.0
    for value in equity:
        peak = max(peak, value)
        max_drawdown = min(max_drawdown, value - peak)

    return {
        "total_pnl": round(total, 2),
        "win_rate": round(win_rate, 2),
        "drawdown": round(max_drawdown, 2),
        "trade_count": len(trades),
    }


def build_chart_payload(df: pd.DataFrame, trades):
    safe = df.copy()
    safe["datetime"] = safe["datetime"].astype(str)
    cols = ["datetime", "open", "high", "low", "close", "volume"]
    candles = safe[cols].where(pd.notnull(safe[cols]), None).to_dict("records")

    markers = []
    for trade in trades:
        markers.append({
            "time": trade["entry_time"],
            "price": trade["entry_price"],
            "side": "BUY" if trade["side"] == "LONG" else "SELL",
        })
        markers.append({
            "time": trade["exit_time"],
            "price": trade["exit_price"],
            "side": "EXIT",
        })
    return {"candles": candles, "markers": markers}
