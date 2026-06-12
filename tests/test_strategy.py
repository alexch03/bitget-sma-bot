import numpy as np
import pandas as pd

from src.strategy import latest_signal, position_size


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
    df = _df_from_close([100.0] * 10)
    decision = latest_signal(df, fast=5, slow=20)
    assert decision.signal == "flat"


def test_detects_bullish_cross():
    # 34 flat candles then a single spike up — the cross lands on the last bar
    baseline = [100.0] * 34
    spike = [115.0]
    df = _df_from_close(baseline + spike)
    decision = latest_signal(df, fast=5, slow=20)
    assert decision.signal == "long", decision.reason


def test_detects_bearish_cross():
    baseline = [100.0] * 34
    drop = [80.0]
    df = _df_from_close(baseline + drop)
    decision = latest_signal(df, fast=5, slow=20)
    assert decision.signal == "short", decision.reason


def test_position_size_uses_risk_pct():
    size = position_size(balance_usdt=1000.0, price=50000.0, risk_pct=2.0)
    # 1000 * 0.02 / 50000 = 0.0004
    assert abs(size - 0.0004) < 1e-9


def test_position_size_zero_price_safe():
    # should not divide by zero
    size = position_size(balance_usdt=1000.0, price=0.0, risk_pct=2.0)
    assert size > 0
