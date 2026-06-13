# Setup

[🇬🇧 English](setup.md) | [🇫🇷 Français](setup.fr.md)

## Requirements

- Python 3.11 or newer
- A Bitget account (only if you want `demo` or `live` mode)

## Install

### 1-click (recommended)

**Windows**:
1. Double-click `install.bat`
2. Edit `.env` with your Bitget keys
3. Double-click `start_web.bat` to open the dashboard

**Linux / macOS**:
```bash
chmod +x *.sh
./install.sh
./start_web.sh
```

### Manual

```bash
git clone https://github.com/alexch03/bitget-sma-bot
cd bitget-sma-bot

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env               # then edit with your keys
```

## Bitget API keys

Only needed for `demo` and `live` modes. `paper` mode needs no keys at all.

> **No Bitget account yet?** Sign up via [the project's referral link](https://www.bitget.com/expressly?languageType=0&channelCode=9K5D7K4J&vipCode=9K5D7K4J) (code `9K5D7K4J`).
> You get the current Bitget welcome bonus + fee discounts. In return, the project earns a share of the trading fees you pay to Bitget (zero extra cost on your side) — this is what funds the open-source bot. For the affiliation to count, sign up via this link (the code is pre-filled) and complete KYC. Commissions only trigger on real trading volume, not on `demo` mode.

### For demo mode (recommended for testing)

1. https://www.bitget.com/asset/demo-trading
2. Activate the demo account (virtual USDT)
3. Switch to demo mode in the Bitget dashboard (button at the top)
4. Personal Center → API Key Management → **Create Demo API Key**
5. Permissions: Read + Trade + Futures. **No** Withdrawal.
6. Save the passphrase — it can only be set at creation time

### For live mode (CAREFUL)

1. https://www.bitget.com/account/newapi
2. Generate a key. Permissions: Read + Trade. **Disable Withdrawal.**
3. Restrict by IP if possible

In `.env`:

```env
BITGET_API_KEY=your_key
BITGET_API_SECRET=your_secret
BITGET_API_PASSWORD=your_passphrase
```

## Telegram (optional)

1. Talk to [@BotFather](https://t.me/BotFather), `/newbot`, follow the steps → token
2. Talk to [@userinfobot](https://t.me/userinfobot) to get your chat id
3. Send `/start` to your bot once so it can message you

In `.env`:

```env
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```

## Run the bot

```bash
# Main bot (uses MODE from .env)
python -m src.main

# Dashboard in another terminal
python -m src.web
# -> http://127.0.0.1:5000

# Backtest
python examples/run_backtest.py --symbol BTC/USDT:USDT --timeframe 1h --days 180

# Showcase (18 backtests + comparison chart)
python examples/showcase.py --days 180

# Grid search
python examples/optimize.py --strategy sma_crossover --symbol BTC/USDT:USDT \
    --timeframe 1h --days 180 --grid '{"fast":[10,20,50],"slow":[50,100,200]}'
```

## Tests

```bash
pytest                              # 54 unit + API tests
python scripts/e2e_full_demo.py     # 9 end-to-end tests on Bitget demo
python scripts/test_ui_smoke.py     # 6 Playwright UI tests
```

The pytest suite does not hit the network (the exchange is mocked).

## Before going live (read twice)

1. Run the bot for at least a week in `paper` mode and review every generated trade.
2. Switch to `demo` mode (virtual money, same endpoints) to validate that orders are placed correctly.
3. Set `MODE=live` and `CONFIRM_LIVE=yes` in `.env`.
4. Use a Bitget sub-account with a small balance (~100 USDT) for the first run.
5. Re-read [DISCLAIMER.md](../DISCLAIMER.md) one last time.
