"""Grid-search a strategy's parameters on real Bitget data.

Usage:
    python examples/optimize.py \
        --strategy sma_crossover \
        --symbol BTC/USDT:USDT --timeframe 1h --days 180 \
        --grid '{"fast": [10, 20, 50], "slow": [50, 100, 200]}' \
        --risk-pct 2 --sl-pct 3 --tp-pct 6

The script fetches OHLCV once, runs all combinations using src.simple_backtest,
ranks the results, prints the top 10, and saves a CSV under examples/results/.
"""
from __future__ import annotations

import argparse
import itertools
import json
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import Config              # noqa: E402
from src.exchange import BitgetExchange    # noqa: E402
from src.simple_backtest import run_simple_backtest  # noqa: E402
from src.strategies import make_strategy   # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy", required=True, choices=["sma_crossover", "bollinger", "rsi_mean_revert"])
    parser.add_argument("--symbol", default="BTC/USDT:USDT")
    parser.add_argument("--timeframe", default="1h")
    parser.add_argument("--days", type=int, default=180)
    parser.add_argument("--grid", required=True, help='JSON dict of params to grid-search, e.g. {"fast":[10,20]}')
    parser.add_argument("--risk-pct", type=float, default=2.0)
    parser.add_argument("--sl-pct", type=float, default=0.0)
    parser.add_argument("--tp-pct", type=float, default=0.0)
    parser.add_argument("--start-cash", type=float, default=1000.0)
    parser.add_argument("--commission", type=float, default=0.0006)
    parser.add_argument("--sort-by", default="return_pct", choices=["return_pct", "sharpe", "win_rate"])
    parser.add_argument("--out", default="examples/results")
    args = parser.parse_args()

    try:
        grid = json.loads(args.grid)
    except json.JSONDecodeError as exc:
        sys.exit(f"--grid must be a JSON dict: {exc}")

    if not isinstance(grid, dict) or not all(isinstance(v, list) for v in grid.values()):
        sys.exit('--grid must look like {"fast":[10,20], "slow":[50,100]}')

    cfg = Config(
        api_key="", api_secret="", api_password="",
        mode="paper", confirm_live=False,
        symbol=args.symbol, timeframe=args.timeframe,
        strategy=args.strategy,
        sma_fast=20, sma_slow=50,
        bb_period=20, bb_std=2.0,
        rsi_period=14, rsi_oversold=30, rsi_overbought=70,
        risk_pct=args.risk_pct,
        stop_loss_pct=args.sl_pct,
        take_profit_pct=args.tp_pct,
        paper_balance=args.start_cash,
        telegram_bot_token="", telegram_chat_id="",
        web_host="127.0.0.1", web_port=5000,
        log_level="INFO",
    )

    exchange = BitgetExchange(cfg)
    now_ms = int(time.time() * 1000)
    since_ms = now_ms - args.days * 24 * 3600 * 1000

    print(f"fetching {args.symbol} {args.timeframe} for {args.days} days...")
    df = exchange.fetch_ohlcv_range(args.symbol, args.timeframe, since_ms, now_ms)
    print(f"got {len(df)} candles from {df.index.min()} to {df.index.max()}")

    keys = list(grid.keys())
    combos = list(itertools.product(*grid.values()))
    print(f"running {len(combos)} backtests on strategy={args.strategy}...")

    rows = []
    for n, combo in enumerate(combos, start=1):
        params = dict(zip(keys, combo))
        try:
            strat = make_strategy(args.strategy, **params)
        except (ValueError, TypeError) as exc:
            print(f"  [{n}/{len(combos)}] {params} -> skip ({exc})")
            continue

        metrics = run_simple_backtest(
            df,
            strat,
            start_cash=args.start_cash,
            risk_pct=args.risk_pct,
            stop_loss_pct=args.sl_pct,
            take_profit_pct=args.tp_pct,
            commission=args.commission,
        )
        row = {
            **params,
            "n_trades": metrics.n_trades,
            "win_rate": round(metrics.win_rate * 100, 1),
            "return_pct": round(metrics.return_pct, 2),
            "max_drawdown_pct": round(metrics.max_drawdown_pct, 2),
            "sharpe": round(metrics.sharpe, 3),
            "final_balance": round(metrics.final_balance, 2),
        }
        rows.append(row)
        print(f"  [{n}/{len(combos)}] {params} -> ret={row['return_pct']:+.2f}%  "
              f"trades={row['n_trades']}  win={row['win_rate']}%  sharpe={row['sharpe']}")

    if not rows:
        sys.exit("no successful backtests")

    df_rows = pd.DataFrame(rows).sort_values(args.sort_by, ascending=False).reset_index(drop=True)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    label = f"optim_{args.strategy}_{args.symbol.replace('/', '_').replace(':', '_')}_{args.timeframe}_{args.days}d"
    csv_path = out_dir / f"{label}.csv"
    df_rows.to_csv(csv_path, index=False)

    print()
    print(f"=== TOP 10 BY {args.sort_by} ===")
    print(df_rows.head(10).to_string(index=False))
    print()
    print(f"saved {len(rows)} rows to {csv_path}")


if __name__ == "__main__":
    main()
