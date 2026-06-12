# bitget-sma-bot

A small, readable crypto trading bot for Bitget USDT-M futures. It uses a moving-average crossover, runs in paper mode by default, sends Telegram alerts when it opens or closes a trade, and exposes a tiny Flask page so you can change a few settings without editing files.

The goal of this repo is to be **useful as a starting point**, not to make you rich. The strategy is intentionally simple so you can read the code in an evening and modify what you want.

> **This project is for learning. Do not run it in live mode with money you cannot afford to lose. Read [DISCLAIMER.md](DISCLAIMER.md) before going further.**

---

## What it does

- Pulls OHLCV candles from Bitget through [ccxt](https://github.com/ccxt/ccxt).
- Computes two simple moving averages (fast: 20, slow: 50) and trades the crossover.
- Runs in three modes:
  - `paper` — default, no real orders, balance simulated in memory
  - `dry` — places no orders but logs what it *would* do, useful for staging
  - `live` — actually places market orders on Bitget (requires explicit opt-in)
- Sends a Telegram message on entry, exit, and error.
- Backtest script (`examples/run_backtest.py`) using `backtrader`.
- Minimal Flask UI on `http://localhost:5000` to change symbol, timeframe and SMA lengths without restarting.

## What it does NOT do

- Multi-strategy switching.
- Position sizing beyond a fixed % of balance.
- Stop-loss / take-profit on the exchange side (only logical exits on crossover).
- Anything ML-related.

If you want any of that, it is meant to be hackable — see [docs/architecture.md](docs/architecture.md).

---

## Quick start

```bash
git clone https://github.com/alexch03/bitget-sma-bot
cd bitget-sma-bot
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env               # then edit .env with your Bitget keys
python -m src.main                 # starts the bot in paper mode
```

For the web UI:

```bash
python -m src.web
```

For a backtest on BTC/USDT with the last 6 months of 1h candles:

```bash
python examples/run_backtest.py --symbol BTC/USDT:USDT --timeframe 1h --days 180
```

A PNG and a CSV land in `examples/results/`.

---

## Configuration

Everything lives in `.env`. The `.env.example` is the reference:

| Variable | What it is | Default |
|---|---|---|
| `BITGET_API_KEY` | Bitget API key (read+trade if live) | empty |
| `BITGET_API_SECRET` | Bitget API secret | empty |
| `BITGET_API_PASSWORD` | Bitget API passphrase | empty |
| `MODE` | `paper`, `dry`, or `live` | `paper` |
| `SYMBOL` | ccxt symbol, e.g. `BTC/USDT:USDT` | `BTC/USDT:USDT` |
| `TIMEFRAME` | `1m`, `5m`, `15m`, `1h`, `4h`, `1d` | `1h` |
| `SMA_FAST` | fast SMA length | `20` |
| `SMA_SLOW` | slow SMA length | `50` |
| `RISK_PCT` | % of balance per trade | `2.0` |
| `TELEGRAM_BOT_TOKEN` | from @BotFather | empty |
| `TELEGRAM_CHAT_ID` | your chat id | empty |
| `PAPER_BALANCE` | starting balance for paper mode | `1000` |

If `MODE=live` is set without a confirmation flag, the bot refuses to start. See `src/config.py`.

---

## Backtest results

The numbers below are from real Bitget OHLCV data fetched at the time the
backtest was run. They are reproducible from `examples/run_backtest.py` and
saved under `examples/results/` (PNG equity curve + trades CSV + summary JSON).

| Symbol | Timeframe | Period | Trades | Win rate | Return | Max DD | Sharpe |
|---|---|---|---|---|---|---|---|
| BTC/USDT:USDT | 1h | ~80 days | 34 | 44.1% | +0.59% | 0.38% | 0.10 |
| BTC/USDT:USDT | 4h | ~365 days | 31 | 35.5% | +0.02% | 0.88% | 0.00 |
| BTC/USDT:USDT | 1d | ~720 days | 16 | 43.8% | +1.19% | 0.64% | 0.04 |

Start balance: 1000 USDT. Risk per trade: 2% of cash. Commission: 0.06%.

![Equity curve — BTC 1d](examples/results/BTC_USDT_USDT_1d_20_50_equity.png)

A few honest takeaways:

- The strategy survives, it does not thrive. Tiny edge, low drawdown because
  the position size is small (2% of cash per trade).
- Win rate is below 50% across all timeframes — typical of trend-following.
- The 1d setup has the cleanest equity curve, which is the usual pattern.

The whole point of this repo is to give you a working baseline you can beat.
Run the script on your own period and symbol before drawing any conclusion —
crypto markets change.

---

## Project layout

```
src/
  config.py            env loading + mode safety check
  exchange.py          ccxt wrapper around Bitget
  indicators.py        SMA, EMA, RSI helpers
  strategy.py          crossover signal generator
  trader.py            main loop: poll, decide, act
  backtest.py          backtrader engine
  telegram_notifier.py async Telegram client
  web.py               Flask UI for runtime config
  main.py              entry point

tests/                 pytest unit tests (no network)
examples/              runnable scripts + results
docs/                  strategy + architecture notes
```

## Testing

```bash
pytest
```

The tests don't hit the network. The exchange module is mocked.

## License

MIT — see [LICENSE](LICENSE).

## Disclaimer

Educational only. The author is not a financial advisor. Trading futures with leverage can wipe out your account in minutes. Read [DISCLAIMER.md](DISCLAIMER.md).
