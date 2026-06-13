# Disclaimer

[🇬🇧 English](DISCLAIMER.md) | [🇫🇷 Français](DISCLAIMER.fr.md)

This software is provided for **educational purposes only**. It is a compact example of how to build a crypto trading bot — nothing more.

By using this code, you agree that:

1. **No financial advice.** The authors are not financial advisors, brokers, or licensed professionals. Nothing in this repository should be interpreted as a recommendation to buy, sell, or hold any asset.

2. **No guarantees.** Past backtest results do not predict future returns. The included strategies (SMA crossover, Bollinger breakout, RSI mean-revert) are well-known baselines and intentionally simple. They lose money in many market conditions.

3. **You are responsible for your funds.** If you set `MODE=live`, the bot will place real orders on your Bitget account. Losses can exceed your initial deposit when using leverage. The authors accept no liability for any financial loss.

4. **Test in paper and demo first.** Run the bot for at least a few weeks in `paper` or `demo` mode before considering `live`. Make sure you understand every line of `src/strategies/` and `src/trader.py` before going real.

5. **API keys.** Never share your `.env` file, never commit it to git, and give your Bitget key the minimum permissions you need. **Disable withdrawals** on any key used by this bot.

6. **Legal use.** Trading derivatives is regulated in many jurisdictions and prohibited for retail users in some. It is your responsibility to know and follow your local laws.

If any of the above is not acceptable to you, do not use this software.
