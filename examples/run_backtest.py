"""Run a backtest on Bitget public OHLCV data.

Usage:
    python examples/run_backtest.py --symbol BTC/USDT:USDT --timeframe 1h --days 180
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# allow `python examples/run_backtest.py` to import src/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ccxt  # noqa: E402

from src.backtest import run_backtest, save_results  # noqa: E402
from src.exchange import BitgetExchange  # noqa: E402
from src.config import Config  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="BTC/USDT:USDT")
    parser.add_argument("--timeframe", default="1h")
    parser.add_argument("--days", type=int, default=180)
    parser.add_argument("--fast", type=int, default=20)
    parser.add_argument("--slow", type=int, default=50)
    parser.add_argument("--risk-pct", type=float, default=2.0)
    parser.add_argument("--start-cash", type=float, default=1000.0)
    parser.add_argument("--commission", type=float, default=0.0006)
    parser.add_argument("--out", default="examples/results")
    args = parser.parse_args()

    cfg = Config(
        api_key="", api_secret="", api_password="",
        mode="paper", confirm_live=False,
        symbol=args.symbol, timeframe=args.timeframe,
        sma_fast=args.fast, sma_slow=args.slow,
        risk_pct=args.risk_pct, paper_balance=args.start_cash,
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

    if len(df) < args.slow * 2:
        print("not enough candles for a meaningful backtest", file=sys.stderr)
        sys.exit(1)

    print(f"running backtest sma {args.fast}/{args.slow} risk_pct={args.risk_pct}%...")
    result = run_backtest(
        df,
        fast=args.fast,
        slow=args.slow,
        risk_pct=args.risk_pct,
        start_cash=args.start_cash,
        commission=args.commission,
    )

    print()
    print("=== RESULTS ===")
    print(f"  trades         {result.n_trades}")
    print(f"  wins           {result.n_wins}")
    print(f"  win rate       {result.win_rate * 100:.1f}%")
    print(f"  total return   {result.return_pct:+.2f}%")
    print(f"  max drawdown   {result.max_drawdown_pct:.2f}%")
    print(f"  sharpe         {result.sharpe if result.sharpe is not None else 'n/a'}")
    print(f"  final balance  {result.end_cash:.2f} USDT")

    label = f"{args.symbol.replace('/', '_').replace(':', '_')}_{args.timeframe}_{args.fast}_{args.slow}"
    out_dir = Path(args.out)
    paths = save_results(result, out_dir, label)
    print()
    print("=== FILES ===")
    for k, v in paths.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
