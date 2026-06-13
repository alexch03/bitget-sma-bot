# Strategies

[🇬🇧 English](strategy.md) | [🇫🇷 Français](strategy.fr.md)

The bot ships with three strategies, all inheriting from `Strategy(ABC)` (see [`src/strategies/base.py`](../src/strategies/base.py)). Each implements a `signal(df) -> Decision` method that returns `long`, `short`, or `flat`.

## 1. SMA Crossover (`sma_crossover`)

The classic two-moving-average trend-following rule.

**Rules:**

Let `f` be the fast SMA (default 20) and `s` the slow SMA (default 50), both computed on close prices.

- **Long** when `f` crosses above `s` (the sign of `f - s` flips from ≤ 0 to > 0).
- **Short** when `f` crosses below `s`.
- **Exit** on the opposite signal. No stop-loss or take-profit in the rule itself — those are handled at the `Trader` level.

**When it does well:**
- Trending markets with low whipsaw
- Higher timeframes (4h, 1d) where the signal-to-noise ratio is better

**When it loses:**
- Range-bound or choppy markets: the bot flips constantly and burns fees
- High-leverage instruments where the small per-trade edge is dominated by funding

## 2. Bollinger Breakout (`bollinger`)

A **breakout** strategy based on Bollinger Bands.

**Rules:**

Let `period` (default 20) be the band length and `std` (default 2.0) the standard-deviation multiplier.

- Upper band = SMA(close, period) + std × σ(close, period)
- Lower band = SMA(close, period) - std × σ(close, period)

- **Long** when the close price breaks above the upper band (and was inside or below the previous bar).
- **Short** when the close price breaks below the lower band.
- **Exit** on the opposite signal.

**When it does well:**
- Markets that fake a range then explode (compression followed by expansion)
- Cryptos that drift sideways before a violent move

**When it loses:**
- True tight ranges where price keeps coming back inside the bands
- Smooth trending markets with no visible compression phase

## 3. RSI Mean Revert (`rsi_mean_revert`)

A **contrarian** RSI strategy.

**Rules:**

Let `period` (default 14), `oversold` (default 30), and `overbought` (default 70).

- **Long** when RSI rebounds above the oversold threshold (crosses 30 from below).
- **Short** when RSI drops below the overbought threshold (crosses 70 from above).
- **Exit** on the opposite signal.

**When it does well:**
- Range-bound markets oscillating around a mean
- 4h timeframes where the market's breathing is clearest
- ETH on 4h yields the best Sharpe in the showcase backtest (+0.63)

**When it loses:**
- Strong trends where RSI stays glued to the extreme without bouncing
- Daily timeframe where the signal is too slow

## Sweet-spot summary

From the 180-day showcase backtest:

| Strategy | Sweet spot | Why |
|---|---|---|
| SMA crossover | 1h | Enough candles to confirm a cross without falling into noise |
| Bollinger breakout | 1d | Volatility is more structured, breakouts are rarer but more reliable |
| RSI mean revert | 4h | Short-to-mid cycles where RSI has room to breathe |

## Adding your own strategy

```python
# src/strategies/my_strategy.py
import pandas as pd
from .base import Strategy, Decision


class MyStrategy(Strategy):
    name = "my_strategy"

    def __init__(self, lookback: int = 20, threshold: float = 0.02):
        self.lookback = lookback
        self.threshold = threshold

    def warmup(self) -> int:
        """Minimum number of candles needed before signal() can return anything other than flat."""
        return self.lookback + 1

    def signal(self, df: pd.DataFrame) -> Decision:
        if len(df) < self.warmup():
            return Decision("flat", "not enough history")

        # Example: long if the last close is X% above the moving average
        closes = df["close"]
        ma = closes.tail(self.lookback).mean()
        last = closes.iloc[-1]
        delta = (last - ma) / ma

        if delta > self.threshold:
            return Decision("long", f"price {delta * 100:.2f}% above MA{self.lookback}")
        if delta < -self.threshold:
            return Decision("short", f"price {delta * 100:.2f}% below MA{self.lookback}")
        return Decision("flat", "inside neutral zone")
```

Then register the strategy in the registry:

```python
# src/strategies/__init__.py
from .my_strategy import MyStrategy

STRATEGIES = {
    "sma_crossover": SMACrossover,
    "bollinger": BollingerBreakout,
    "rsi_mean_revert": RSIMeanRevert,
    "my_strategy": MyStrategy,  # new entry
}
```

From there:
- The dashboard automatically lists it in the selector
- The optimizer (`examples/optimize.py --strategy my_strategy`) can grid-search its params
- The trader can load it via `STRATEGY=my_strategy` in `.env`

## Risk management (at the trader level, not the strategy)

SL / TP / sizing are handled at the `Trader` level rather than inside each strategy. This avoids duplicating those rules everywhere:

- **`RISK_PCT`**: fraction of balance risked per trade. Trade size is computed as `notional = balance × RISK_PCT / 100`.
- **`STOP_LOSS_PCT`**: automatic exit if the price moves X% against the position (0 = disabled).
- **`TAKE_PROFIT_PCT`**: automatic exit if the price moves X% in favor of the position (0 = disabled).

These checks happen locally on every tick. **No stop order is placed exchange-side.** If the bot is down while the price moves, no exit fires — a known limitation. For `live` mode, plugging in broker-side stops is the natural next step.
