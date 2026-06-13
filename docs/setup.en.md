# Setup

## Requirements

- Python 3.11 or newer
- A Bitget account if you want to run in `live` mode

## Install

```bash
git clone https://github.com/alexch03/bitget-sma-bot
cd bitget-sma-bot
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Bitget API key

You only need this if you plan to run in `live` mode.

> **No Bitget account yet?** Sign up via [the project's referral link](https://www.bitget.com/expressly?languageType=0&channelCode=9K5D7K4J&vipCode=9K5D7K4J) (code `9K5D7K4J`).
> You get the current Bitget welcome bonus + fee discounts. In return, the project earns a share of the trading fees you pay to Bitget (no extra cost on your side) — this is what funds the open-source bot. For the affiliation to count, sign up via this link (the code is pre-filled) and complete KYC. Commissions only trigger on real trading volume, not on `demo` mode.

1. Go to https://www.bitget.com/account/newapi
2. Create a key. Give it **Read + Trade** permission. **Disable withdrawals.**
3. Save the API key, secret, and passphrase. The passphrase is set at creation
   time and cannot be recovered later.

Set them in `.env`:

```
BITGET_API_KEY=...
BITGET_API_SECRET=...
BITGET_API_PASSWORD=...
```

## Telegram (optional)

1. Talk to [@BotFather](https://t.me/BotFather), `/newbot`, follow prompts → token.
2. Talk to [@userinfobot](https://t.me/userinfobot) to get your chat id.
3. Send `/start` to your new bot once so it can message you.

Then set:

```
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```

## Run

```bash
# main loop (uses MODE from .env)
python -m src.main

# web UI in another terminal
python -m src.web
# -> http://127.0.0.1:5000

# backtest
python examples/run_backtest.py --symbol BTC/USDT:USDT --timeframe 1h --days 180
```

## Tests

```bash
pytest
```

The tests do not hit the network.

## Going live (read carefully)

1. Run for at least a week in `paper` mode and review the trades.
2. Set `MODE=live` and `CONFIRM_LIVE=yes` in `.env`.
3. Use a Bitget sub-account with a small balance (e.g. 100 USDT) for the first run.
4. Read [DISCLAIMER.md](../DISCLAIMER.md) again.
