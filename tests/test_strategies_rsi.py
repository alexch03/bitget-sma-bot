import numpy as np
import pandas as pd

from src.strategies import RSIMeanRevert


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
    strat = RSIMeanRevert(period=14, oversold=30, overbought=70)
    df = _df_from_close([100.0] * 5)
    decision = strat.signal(df)
    assert decision.signal == "flat"


def test_detects_rebound_from_oversold():
    # steep drop drives RSI to ~0, then a strong bounce lifts it above 30
    values = list(np.linspace(200, 100, 25)) + [140.0]
    df = _df_from_close(values)
    strat = RSIMeanRevert(period=14, oversold=30, overbought=70)
    decision = strat.signal(df)
    assert decision.signal == "long", decision.reason


def test_detects_drop_from_overbought():
    # mostly rising with tiny dips so RSI is well above 70, then a sharp drop
    rng = np.random.default_rng(7)
    deltas = np.abs(rng.normal(2, 1, 40))
    deltas[::5] = -np.abs(rng.normal(0.3, 0.1, len(deltas[::5])))
    values = (100 + np.cumsum(deltas)).tolist()
    values.append(values[-1] - 30)
    df = _df_from_close(values)
    strat = RSIMeanRevert(period=14, oversold=30, overbought=70)
    decision = strat.signal(df)
    assert decision.signal == "short", decision.reason


def test_neutral_mid_range():
    rng = np.random.default_rng(42)
    values = (100 + rng.normal(0, 1, 25)).tolist()
    df = _df_from_close(values)
    strat = RSIMeanRevert(period=14, oversold=30, overbought=70)
    decision = strat.signal(df)
    assert decision.signal == "flat"


def test_invalid_thresholds_raise():
    import pytest
    with pytest.raises(ValueError):
        RSIMeanRevert(period=14, oversold=80, overbought=20)
