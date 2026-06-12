"""A small, generic backtest engine that works with any Strategy.

backtrader (used by examples/run_backtest.py) is great for one-off runs but
the cerebro setup is heavy for a grid search across hundreds of param combos.
This module walks the price series candle by candle, calls strategy.signal(),
applies SL/TP and commission, and returns the same shape of metrics.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .strategies import Strategy


@dataclass
class TradeRecord:
    side: str
    entry_price: float
    exit_price: float
    amount: float
    pnl: float
    exit_reason: str
    entry_idx: int
    exit_idx: int


@dataclass
class BacktestMetrics:
    n_trades: int
    n_wins: int
    win_rate: float
    return_pct: float
    max_drawdown_pct: float
    sharpe: float
    final_balance: float
    trades: list[TradeRecord] = field(default_factory=list)
    equity_curve: list[float] = field(default_factory=list)


def run_simple_backtest(
    df: pd.DataFrame,
    strategy: Strategy,
    start_cash: float = 1000.0,
    risk_pct: float = 2.0,
    stop_loss_pct: float = 0.0,
    take_profit_pct: float = 0.0,
    commission: float = 0.0006,
) -> BacktestMetrics:
    """Walk df bar by bar, call strategy.signal(), apply SL/TP, track PnL.

    Returns metrics + per-trade records + equity curve.
    """
    balance = start_cash
    position: dict | None = None
    trades: list[TradeRecord] = []
    equity_curve: list[float] = []

    warmup = strategy.warmup()
    if len(df) <= warmup:
        return BacktestMetrics(0, 0, 0.0, 0.0, 0.0, 0.0, start_cash)

    for i in range(warmup, len(df)):
        sub = df.iloc[: i + 1]
        price = float(sub["close"].iloc[-1])

        # SL/TP first
        if position is not None:
            reason = _sl_tp_hit(position, price, stop_loss_pct, take_profit_pct)
            if reason is not None:
                pnl = _close(position, price, commission)
                balance += pnl
                trades.append(TradeRecord(
                    side=position["side"],
                    entry_price=position["entry"],
                    exit_price=price,
                    amount=position["amount"],
                    pnl=pnl,
                    exit_reason=reason,
                    entry_idx=position["idx"],
                    exit_idx=i,
                ))
                position = None

        decision = strategy.signal(sub)

        if decision.signal == "flat":
            equity_curve.append(_mark_to_market(balance, position, price))
            continue

        if position is None:
            position = _open(balance, price, risk_pct, decision.signal, commission, i)
            balance -= position["amount"] * price * commission  # entry fee
        elif (
            (position["side"] == "long" and decision.signal == "short")
            or (position["side"] == "short" and decision.signal == "long")
        ):
            pnl = _close(position, price, commission)
            balance += pnl
            trades.append(TradeRecord(
                side=position["side"],
                entry_price=position["entry"],
                exit_price=price,
                amount=position["amount"],
                pnl=pnl,
                exit_reason="signal_flip",
                entry_idx=position["idx"],
                exit_idx=i,
            ))
            position = _open(balance, price, risk_pct, decision.signal, commission, i)
            balance -= position["amount"] * price * commission

        equity_curve.append(_mark_to_market(balance, position, price))

    # Close any open position at the last price
    if position is not None:
        last_price = float(df["close"].iloc[-1])
        pnl = _close(position, last_price, commission)
        balance += pnl
        trades.append(TradeRecord(
            side=position["side"],
            entry_price=position["entry"],
            exit_price=last_price,
            amount=position["amount"],
            pnl=pnl,
            exit_reason="eod",
            entry_idx=position["idx"],
            exit_idx=len(df) - 1,
        ))

    return _build_metrics(start_cash, balance, trades, equity_curve)


def _open(balance: float, price: float, risk_pct: float, side: str, commission: float, idx: int) -> dict:
    notional = balance * (risk_pct / 100.0)
    amount = notional / max(price, 1e-9)
    return {"side": side, "amount": amount, "entry": price, "idx": idx}


def _close(position: dict, price: float, commission: float) -> float:
    direction = 1 if position["side"] == "long" else -1
    gross = direction * (price - position["entry"]) * position["amount"]
    fee = position["amount"] * price * commission
    return gross - fee


def _sl_tp_hit(position: dict, price: float, sl_pct: float, tp_pct: float) -> str | None:
    side = position["side"]
    entry = position["entry"]
    if sl_pct > 0:
        if side == "long" and price <= entry * (1 - sl_pct / 100):
            return "SL"
        if side == "short" and price >= entry * (1 + sl_pct / 100):
            return "SL"
    if tp_pct > 0:
        if side == "long" and price >= entry * (1 + tp_pct / 100):
            return "TP"
        if side == "short" and price <= entry * (1 - tp_pct / 100):
            return "TP"
    return None


def _mark_to_market(balance: float, position: dict | None, price: float) -> float:
    if position is None:
        return balance
    direction = 1 if position["side"] == "long" else -1
    unrealised = direction * (price - position["entry"]) * position["amount"]
    return balance + unrealised


def _build_metrics(start_cash: float, balance: float, trades: list[TradeRecord], equity: list[float]) -> BacktestMetrics:
    if not trades:
        return BacktestMetrics(0, 0, 0.0, 0.0, 0.0, 0.0, balance, [], equity)

    n_wins = sum(1 for t in trades if t.pnl > 0)
    return_pct = (balance - start_cash) / start_cash * 100

    arr = np.asarray(equity, dtype=float)
    if len(arr) > 1:
        running_max = np.maximum.accumulate(arr)
        dd = (running_max - arr) / np.where(running_max > 0, running_max, 1.0)
        max_dd_pct = float(dd.max() * 100)

        # Daily-ish Sharpe: per-bar returns annualized assuming 365 bars/day at 1h tf is wrong,
        # but we just compute a rough indicator. Production code should sample per day.
        rets = np.diff(arr) / np.where(arr[:-1] != 0, arr[:-1], 1.0)
        rets = rets[np.isfinite(rets)]
        sharpe = float((rets.mean() / rets.std()) * (252 ** 0.5)) if rets.std() > 0 else 0.0
    else:
        max_dd_pct = 0.0
        sharpe = 0.0

    return BacktestMetrics(
        n_trades=len(trades),
        n_wins=n_wins,
        win_rate=n_wins / len(trades),
        return_pct=return_pct,
        max_drawdown_pct=max_dd_pct,
        sharpe=sharpe,
        final_balance=balance,
        trades=trades,
        equity_curve=equity,
    )
