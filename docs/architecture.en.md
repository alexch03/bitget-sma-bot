# Architecture

The bot has four moving pieces, kept deliberately decoupled.

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

## `config.py`

Single source of truth at runtime. Reads `.env`, validates, returns a
`Config` dataclass. The `live` mode requires `CONFIRM_LIVE=yes` — this
prevents accidental real-money runs.

## `exchange.py`

Wraps ccxt's Bitget client. Public methods (`fetch_ohlcv`,
`fetch_ohlcv_range`, `fetch_ticker_price`) work without credentials. Trading
methods need them. The wrapper is the only place that touches the network for
trading; everything else operates on dataframes.

## `strategy.py`

Pure functions over a `pd.DataFrame`. `latest_signal(df, fast, slow)`
returns a `Decision` (`long` / `short` / `flat` + reason). The strategy
module knows nothing about exchanges, money, or Telegram.

## `trader.py`

The main loop. Holds the in-memory paper book (`PaperBook`), persists to
`state.json` between restarts, and dispatches to the exchange in `live`
mode. Decides:

- if no position and signal → open
- if position and opposite signal → close + open the other way
- otherwise → do nothing

## `telegram_notifier.py`

Fire-and-forget messages. If `TELEGRAM_BOT_TOKEN` is empty, the notifier
silently no-ops and the bot still runs.

## `web.py`

A tiny Flask page that writes `runtime.json`. **The current main loop reads
`.env` only at startup**, so changes via the web UI are saved but require a
restart to take effect. Wiring `runtime.json` into the loop's config refresh
is left as an exercise (see `Trader` — read overrides at the top of each `step()`).

## Files at runtime

| File | Purpose | In `.gitignore`? |
|---|---|---|
| `.env` | secrets and config | yes |
| `state.json` | paper-mode balance + open position | yes |
| `runtime.json` | overrides written by the web UI | yes |
| `examples/results/*.csv` | backtest outputs | yes |
| `examples/results/*.png` | equity curve plots | yes |
