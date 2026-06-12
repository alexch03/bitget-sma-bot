from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import backtrader as bt
import pandas as pd


class SMACrossover(bt.Strategy):
    params = dict(fast=20, slow=50, risk_pct=2.0)

    def __init__(self):
        self.sma_fast = bt.ind.SMA(self.data.close, period=self.p.fast)
        self.sma_slow = bt.ind.SMA(self.data.close, period=self.p.slow)
        self.crossover = bt.ind.CrossOver(self.sma_fast, self.sma_slow)
        self.trades_log: list[dict] = []

    def next(self):
        price = float(self.data.close[0])

        if not self.position:
            if self.crossover > 0:
                size = self._size(price)
                if size > 0:
                    self.buy(size=size)
            elif self.crossover < 0:
                size = self._size(price)
                if size > 0:
                    self.sell(size=size)
        else:
            if self.position.size > 0 and self.crossover < 0:
                self.close()
                size = self._size(price)
                if size > 0:
                    self.sell(size=size)
            elif self.position.size < 0 and self.crossover > 0:
                self.close()
                size = self._size(price)
                if size > 0:
                    self.buy(size=size)

    def _size(self, price: float) -> float:
        cash = float(self.broker.getcash())
        notional = cash * (self.p.risk_pct / 100.0)
        return round(notional / max(price, 1e-9), 6)

    def notify_trade(self, trade: bt.Trade):
        if trade.isclosed:
            self.trades_log.append({
                "ref": trade.ref,
                "size": trade.size,
                "pnl": float(trade.pnl),
                "pnlcomm": float(trade.pnlcomm),
                "opened": bt.num2date(trade.dtopen).isoformat() if trade.dtopen else None,
                "closed": bt.num2date(trade.dtclose).isoformat() if trade.dtclose else None,
            })


@dataclass
class BacktestResult:
    start_cash: float
    end_cash: float
    return_pct: float
    n_trades: int
    n_wins: int
    win_rate: float
    max_drawdown_pct: float
    sharpe: Optional[float]
    trades: list[dict]
    equity_curve: pd.DataFrame


def run_backtest(
    df: pd.DataFrame,
    fast: int = 20,
    slow: int = 50,
    risk_pct: float = 2.0,
    start_cash: float = 1000.0,
    commission: float = 0.0006,
) -> BacktestResult:
    """Run an SMA crossover backtest on a candle DataFrame.

    df must have columns [open, high, low, close, volume] and a DatetimeIndex.
    """
    cerebro = bt.Cerebro(stdstats=False)
    cerebro.broker.setcash(start_cash)
    cerebro.broker.setcommission(commission=commission)

    data = bt.feeds.PandasData(dataname=df)
    cerebro.adddata(data)
    cerebro.addstrategy(SMACrossover, fast=fast, slow=slow, risk_pct=risk_pct)

    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="dd")
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe", timeframe=bt.TimeFrame.Days, riskfreerate=0)
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")
    cerebro.addobserver(bt.observers.Broker)

    strats = cerebro.run()
    strat = strats[0]

    end_cash = float(cerebro.broker.getvalue())
    dd = strat.analyzers.dd.get_analysis()
    sharpe_raw = strat.analyzers.sharpe.get_analysis()
    trades_an = strat.analyzers.trades.get_analysis()

    n_trades = trades_an.get("total", {}).get("closed", 0)
    n_wins = trades_an.get("won", {}).get("total", 0)
    win_rate = (n_wins / n_trades) if n_trades else 0.0

    return BacktestResult(
        start_cash=start_cash,
        end_cash=end_cash,
        return_pct=(end_cash - start_cash) / start_cash * 100,
        n_trades=n_trades,
        n_wins=n_wins,
        win_rate=win_rate,
        max_drawdown_pct=float(dd.get("max", {}).get("drawdown", 0.0) or 0.0),
        sharpe=sharpe_raw.get("sharperatio"),
        trades=strat.trades_log,
        equity_curve=_equity_from_broker(strat),
    )


def _equity_from_broker(strat) -> pd.DataFrame:
    """Reconstruct a cash + value series from the broker observer."""
    obs = next((o for o in strat.observers if isinstance(o, bt.observers.Broker)), None)
    if obs is None:
        return pd.DataFrame()

    cash = list(obs.lines.cash.array)
    value = list(obs.lines.value.array)
    dates = [bt.num2date(d) for d in strat.data.datetime.array]

    n = min(len(dates), len(value))
    return pd.DataFrame({"date": dates[:n], "cash": cash[:n], "value": value[:n]})


def save_results(result: BacktestResult, out_dir: Path, label: str) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {}

    # CSV with trades
    trades_path = out_dir / f"{label}_trades.csv"
    pd.DataFrame(result.trades).to_csv(trades_path, index=False)
    paths["trades_csv"] = trades_path

    # Equity curve PNG
    png_path = out_dir / f"{label}_equity.png"
    _save_equity_plot(result.equity_curve, png_path, label)
    paths["equity_png"] = png_path

    # Summary JSON
    import json
    summary = {
        "start_cash": result.start_cash,
        "end_cash": result.end_cash,
        "return_pct": result.return_pct,
        "n_trades": result.n_trades,
        "n_wins": result.n_wins,
        "win_rate": result.win_rate,
        "max_drawdown_pct": result.max_drawdown_pct,
        "sharpe": result.sharpe,
    }
    summary_path = out_dir / f"{label}_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2))
    paths["summary_json"] = summary_path

    return paths


def _save_equity_plot(equity: pd.DataFrame, path: Path, title: str) -> None:
    if equity.empty:
        return
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(equity["date"], equity["value"], label="equity")
    ax.set_title(title)
    ax.set_xlabel("date")
    ax.set_ylabel("USDT")
    ax.grid(True, alpha=0.3)
    ax.legend()
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)
