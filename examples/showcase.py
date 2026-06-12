"""Showcase: run every strategy on multiple symbols and timeframes,
print a clean recap table and save a comparison equity-curve PNG.

Usage:
    python examples/showcase.py --days 365
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import Config                      # noqa: E402
from src.exchange import BitgetExchange            # noqa: E402
from src.simple_backtest import run_simple_backtest  # noqa: E402
from src.strategies import make_strategy           # noqa: E402


# Sensible default params per strategy
CONFIGS = [
    {"name": "sma_crossover", "params": {"fast": 20, "slow": 50}, "label": "SMA 20/50"},
    {"name": "bollinger",     "params": {"period": 20, "std": 2.0}, "label": "Bollinger 20/2"},
    {"name": "rsi_mean_revert","params": {"period": 14, "oversold": 30, "overbought": 70}, "label": "RSI 14 30/70"},
]

SYMBOLS = ["BTC/USDT:USDT", "ETH/USDT:USDT"]
TIMEFRAMES = ["1h", "4h", "1d"]


def _cfg(symbol, timeframe) -> Config:
    return Config(
        api_key="", api_secret="", api_password="",
        mode="paper", confirm_live=False,
        symbol=symbol, timeframe=timeframe,
        strategy="sma_crossover",
        sma_fast=20, sma_slow=50,
        bb_period=20, bb_std=2.0,
        rsi_period=14, rsi_oversold=30, rsi_overbought=70,
        risk_pct=2.0,
        stop_loss_pct=3.0,
        take_profit_pct=6.0,
        paper_balance=1000.0,
        telegram_bot_token="", telegram_chat_id="",
        web_host="127.0.0.1", web_port=5000,
        log_level="WARNING",
    )


def fetch_ohlcv(symbol: str, timeframe: str, days: int) -> pd.DataFrame:
    cfg = _cfg(symbol, timeframe)
    ex = BitgetExchange(cfg)
    now_ms = int(time.time() * 1000)
    since_ms = now_ms - days * 24 * 3600 * 1000
    return ex.fetch_ohlcv_range(symbol, timeframe, since_ms, now_ms)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=180)
    parser.add_argument("--start-cash", type=float, default=1000.0)
    parser.add_argument("--risk-pct", type=float, default=2.0)
    parser.add_argument("--sl-pct", type=float, default=3.0)
    parser.add_argument("--tp-pct", type=float, default=6.0)
    parser.add_argument("--commission", type=float, default=0.0006)
    parser.add_argument("--out", default="examples/results/showcase")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    equity_for_chart: dict[str, list] = {}  # used for the comparison png on BTC 4h

    # cache fetched data so we don't refetch 3x per (symbol, tf)
    data_cache: dict[tuple, pd.DataFrame] = {}

    total = len(SYMBOLS) * len(TIMEFRAMES) * len(CONFIGS)
    n = 0

    for symbol in SYMBOLS:
        for tf in TIMEFRAMES:
            print()
            print(f"=== fetching {symbol} {tf} ({args.days}d) ===")
            try:
                df = fetch_ohlcv(symbol, tf, args.days)
            except Exception as exc:
                print(f"  fetch FAILED: {exc}")
                continue
            print(f"  got {len(df)} candles from {df.index.min()} to {df.index.max()}")
            data_cache[(symbol, tf)] = df

            for c in CONFIGS:
                n += 1
                strat = make_strategy(c["name"], **c["params"])
                metrics = run_simple_backtest(
                    df, strat,
                    start_cash=args.start_cash,
                    risk_pct=args.risk_pct,
                    stop_loss_pct=args.sl_pct,
                    take_profit_pct=args.tp_pct,
                    commission=args.commission,
                )
                row = {
                    "symbol": symbol,
                    "timeframe": tf,
                    "strategy": c["label"],
                    "trades": metrics.n_trades,
                    "win_rate_pct": round(metrics.win_rate * 100, 1),
                    "return_pct": round(metrics.return_pct, 2),
                    "max_dd_pct": round(metrics.max_drawdown_pct, 2),
                    "sharpe": round(metrics.sharpe, 2),
                    "final_balance": round(metrics.final_balance, 2),
                }
                rows.append(row)
                print(f"  [{n}/{total}] {c['label']:18s}  trades={row['trades']:>3}  "
                      f"win={row['win_rate_pct']:>5.1f}%  ret={row['return_pct']:+.2f}%  "
                      f"dd={row['max_dd_pct']:.2f}%  sharpe={row['sharpe']:+.2f}")

                # Save equity for BTC 4h comparison chart
                if symbol == "BTC/USDT:USDT" and tf == "4h":
                    # convert equity_curve (list of values) to (time, value) using df index
                    warmup = strat.warmup()
                    times = df.index[warmup:warmup + len(metrics.equity_curve)]
                    equity_for_chart[c["label"]] = list(zip(times, metrics.equity_curve))

    if not rows:
        print("no backtest results", file=sys.stderr)
        return 1

    # ----- recap table -----
    recap = pd.DataFrame(rows)
    csv_path = out_dir / "summary.csv"
    recap.to_csv(csv_path, index=False)

    print()
    print("=" * 100)
    print("SHOWCASE SUMMARY")
    print("=" * 100)
    print(recap.to_string(index=False))
    print()
    print(f"saved {csv_path}")

    # ----- comparison PNG on BTC 4h -----
    if equity_for_chart:
        png_path = out_dir / "comparison_BTC_4h.png"
        _save_comparison_chart(equity_for_chart, data_cache.get(("BTC/USDT:USDT", "4h")),
                                args.start_cash, args.days, png_path)
        print(f"saved {png_path}")

    return 0


def _save_comparison_chart(equity_per_strategy: dict, df: pd.DataFrame | None,
                            start_cash: float, days: int, path: Path) -> None:
    fig, axes = plt.subplots(2, 1, figsize=(12, 7), gridspec_kw={"height_ratios": [3, 1]}, sharex=True)
    ax1, ax2 = axes
    colors = {"SMA 20/50": "#2563eb", "Bollinger 20/2": "#16a34a", "RSI 14 30/70": "#dc2626"}
    for label, pts in equity_per_strategy.items():
        times = [p[0] for p in pts]
        values = [p[1] for p in pts]
        ax1.plot(times, values, label=label, color=colors.get(label, "gray"), linewidth=1.3)

    # buy-and-hold baseline on the price for comparison
    if df is not None and len(df) > 0:
        normalized = df["close"] * (start_cash / df["close"].iloc[0])
        ax1.plot(df.index, normalized, label="buy & hold", color="#9ca3af", linewidth=1, linestyle="--", alpha=0.7)
        ax2.plot(df.index, df["close"], color="#1f2937", linewidth=0.7)
        ax2.set_ylabel("BTC price", fontsize=9)
        ax2.grid(True, alpha=0.3)

    ax1.set_title(f"BTC/USDT 4h - {days} days - strategies equity vs buy-and-hold")
    ax1.set_ylabel("equity (USDT)", fontsize=9)
    ax1.legend(loc="best", fontsize=9)
    ax1.grid(True, alpha=0.3)
    ax1.axhline(y=start_cash, color="#6b7280", linewidth=0.6, linestyle=":")

    plt.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


if __name__ == "__main__":
    sys.exit(main())
