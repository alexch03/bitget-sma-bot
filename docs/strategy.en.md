# Strategy

The included strategy is the classic two-moving-average crossover.

## Rule

Let `f` be the fast SMA (default 20) and `s` the slow SMA (default 50), both
computed on close prices.

- **Long entry** when `f` crosses above `s` (i.e. `f - s` goes from ≤ 0 to > 0).
- **Short entry** when `f` crosses below `s`.
- **Exit** on the opposite cross. Existing position is closed and a new one is opened.

There is no stop-loss, no take-profit, no time-based exit. Exits are purely
signal-driven. This is intentional — the goal is to keep the example readable.

## Why this strategy

- It is widely understood.
- It implements correctly in a few lines of pandas.
- It has the expected failure mode (chops in ranging markets), which makes it
  a good baseline to compare against any improvement you try.

## When it does well

- Strong trending markets with low whipsaw.
- Higher timeframes (4h, 1d) generally have a better signal-to-noise ratio
  for this rule.

## When it loses

- Range-bound or choppy markets: the bot keeps flipping and burning fees.
- High-leverage instruments where the small per-trade edge is dominated by funding.

## Things to try

If you want to improve on the baseline:

1. Add a trend filter (e.g. only take longs if the daily SMA is rising).
2. Add an ATR-based stop-loss.
3. Replace SMA with EMA — see `src/indicators.py::ema`.
4. Use Bollinger Band width to gate entries (skip when bands are tight).
5. Add a volatility-scaled position size instead of a fixed % notional.

Each of these can be added without touching anything outside `src/strategy.py`.
