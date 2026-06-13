# Architecture

[🇬🇧 English](architecture.md) | [🇫🇷 Français](architecture.fr.md)

The bot has four core components, kept deliberately decoupled.

```
+------------+      +---------+      +-----------+      +----------+
|   config   | ---> | trader  | ---> | exchange  | ---> |  Bitget  |
|  (.env)    |      |  loop   |      |  (ccxt)   |      |   API    |
+------------+      +----+----+      +-----------+      +----------+
                         |
                         v
                  +-------------+      +-----------+
                  |  notifier   | ---> | Telegram  |
                  +-------------+      +-----------+
```

Full SVG diagram: [docs/images/architecture.svg](images/architecture.svg)

## `config.py`

Single source of truth at runtime. Reads `.env`, validates, returns a `Config` dataclass. The `live` mode requires `CONFIRM_LIVE=yes` — a guard against accidental real-money runs. Same idea for `demo` mode, which checks that API keys are present.

## `exchange.py`

Wraps the `ccxt.bitget` client. Public methods (`fetch_ohlcv`, `fetch_ohlcv_range`, `fetch_ticker_price`) work without credentials. Trading methods need them. This is the only place that touches the network for trading; everything else operates on DataFrames.

In `demo` mode, the wrapper explicitly adds the `paptrading: 1` header to requests (per Bitget's official documentation) on top of ccxt's `set_sandbox_mode(True)` call.

## `strategies/`

Pluggable framework. Every strategy inherits `Strategy(ABC)` and implements two methods:

- `signal(df) -> Decision`: pure rule over the candles DataFrame, returns `long`, `short`, or `flat` plus a textual reason
- `warmup() -> int`: minimum number of candles required before `signal()` can return anything other than `flat`

The `strategies` module exposes a `STRATEGIES` registry and a `make_strategy(name, **kwargs)` factory. The trader and the optimizer are completely strategy-agnostic — they call strategies by name.

Strategies know nothing about exchanges, money, or Telegram. They only know `pandas`. That is what makes them testable (unit tests feed in synthetic DataFrames).

## `trader.py`

The main loop. Holds the `PaperBook` in memory (balance + position), persists state to `state.json` so paper-mode runs survive restarts, and dispatches orders to the exchange in `demo` or `live` mode.

On every tick:

1. Read `control.json`: if `paused=true`, skip. If `force_close=true`, close the position and reset the flag.
2. Fetch recent candles.
3. If a position is open, check SL / TP. If triggered → close.
4. Call `strategy.signal(df)`. Decide: open, close, or flip.
5. Write `bot_status.json` (read by the dashboard to show the last signal).

On every close (signal, SL, TP, manual), append a line to `trades.jsonl`.

## `telegram_notifier.py`

Fire-and-forget messages. If `TELEGRAM_BOT_TOKEN` is empty, the notifier silently no-ops and the bot keeps running.

## `web.py`

Flask dashboard + API endpoints. The dashboard is a single-file SPA served via `render_template_string` with:

- Tailwind CSS via CDN
- `lightweight-charts` (TradingView) via CDN
- Vanilla JS for polling and actions

The dashboard manages **the bot's lifecycle**: `POST /api/bot/start` spawns `python -m src.main` via `subprocess.Popen` and stores its handle. Stdout is read in a daemon thread and pushed into a ring buffer exposed by `/api/logs`.

Config changes go through `POST /api/config`, which writes to `.env` (whitelisted keys only) and offers to restart the bot.

## Runtime files (all gitignored)

| File | Role | Written by | Read by |
|---|---|---|---|
| `.env` | secrets + config parameters | the user or `/api/config` | `config.py` at startup |
| `state.json` | balance + position (paper mode) | `trader.py` | `trader.py` on restart, dashboard |
| `control.json` | `paused`, `force_close` flags | dashboard, trader | `trader.py` on every tick |
| `bot_status.json` | last tick, signal, price, position | `trader.py` | dashboard |
| `trades.jsonl` | append-only trade history | `trader._close()` | dashboard, equity curve |
| `runtime.json` | temporary UI overrides | dashboard | (reserved for future hot-reload) |

## Backtester

Two engines coexist:

- **`backtest.py`**: full `backtrader` engine, equivalent to what you find in the backtrader docs. Used by `examples/run_backtest.py`. Generates equity PNG + trades CSV.
- **`simple_backtest.py`**: small hand-rolled engine that iterates bar by bar. Compatible with any `Strategy`. Used by `examples/optimize.py` and `examples/showcase.py` because it is ~10x faster than cerebro for grids of 100+ combos.

Both support SL / TP / commission. The simple engine is easier to read if you want to understand how the rules chain together.
