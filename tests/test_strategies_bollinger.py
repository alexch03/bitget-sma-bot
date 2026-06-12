import pandas as pd

from src.strategies import BollingerBreakout
from src.strategy import position_size


def _df_from_close(close_values):
    n = len(close_values)
    idx = pd.date_range("2026-01-01", periods=n, freq="1h", tz="UTC")
    return pd.DataFrame({
        "open": close_values,
        "high": close_values,
        "low": close_values,
        "close": close_values,
        "volume": [1.0] * n,
    }, index=idx)


def test_flat_when_not_enough_data():
    strat = BollingerBreakout(period=20, std=2.0)
    df = _df_from_close([100.0] * 10)
    decision = strat.signal(df)
    assert decision.signal == "flat"


def test_detects_breakout_up():
    # 24 flat candles tighten the band, then a spike pushes close above upper
    strat = BollingerBreakout(period=20, std=2.0)
    df = _df_from_close([100.0] * 24 + [110.0])
    decision = strat.signal(df)
    assert decision.signal == "long", decision.reason


def test_detects_breakout_down():
    strat = BollingerBreakout(period=20, std=2.0)
    df = _df_from_close([100.0] * 24 + [90.0])
    decision = strat.signal(df)
    assert decision.signal == "short", decision.reason


def test_no_signal_when_already_above():
    # prev bar already broke out, curr bar still above -> not a fresh breakout
    strat = BollingerBreakout(period=20, std=2.0)
    df = _df_from_close([100.0] * 23 + [110.0, 111.0])
    decision = strat.signal(df)
    assert decision.signal == "flat"


def test_position_size_works_with_breakout_price():
    strat = BollingerBreakout(period=20, std=2.0)
    df = _df_from_close([100.0] * 24 + [110.0])
    decision = strat.signal(df)
    assert decision.signal == "long"
    size = position_size(balance_usdt=1000.0, price=df["close"].iloc[-1], risk_pct=2.0)
    assert size > 0
