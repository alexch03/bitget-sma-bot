# Disclaimer

This software is provided for **educational purposes only**. It is a small
example of how to build a crypto trading bot — nothing more.

By using this code, you agree that:

1. **No financial advice.** The author is not a financial advisor, broker, or
   licensed professional. Nothing in this repository should be interpreted
   as a recommendation to buy, sell, or hold any asset.

2. **No guarantees.** Past backtest results do not predict future returns.
   The included strategy (SMA crossover) is well-known and intentionally
   simple. It loses money in many market conditions.

3. **You are responsible for your funds.** If you set `MODE=live`, the bot
   will place real orders on your Bitget account. Losses can exceed your
   initial deposit if you use leverage. The author accepts no liability for
   any financial loss.

4. **Test in paper mode first.** Run the bot for at least a few weeks in
   `paper` or `dry` mode before considering anything else. Make sure you
   understand every line of `src/strategy.py` and `src/trader.py` before
   going live.

5. **API keys.** Never share your `.env` file, never commit it to git, and
   give your Bitget API key the minimum permissions you need. Disable
   withdrawal permissions on any key used by this bot.

6. **Legal use.** Trading derivatives is regulated in many jurisdictions
   and prohibited for retail users in some. It is your responsibility to
   know and follow your local laws.

If any of the above is not acceptable to you, do not use this software.
