import numpy as np
import pandas as pd

from src.indicators import sma, ema, rsi, add_smas


def _series(values):
    return pd.Series(values, dtype=float)


def test_sma_basic():
    s = _series([1, 2, 3, 4, 5])
    out = sma(s, 3).tolist()
    assert np.isnan(out[0])
    assert np.isnan(out[1])
    assert out[2] == 2.0
    assert out[3] == 3.0
    assert out[4] == 4.0


def test_ema_monotonic_for_constant_series():
    s = _series([10] * 20)
    out = ema(s, 5).dropna().tolist()
    assert all(abs(v - 10) < 1e-9 for v in out)


def test_rsi_bounds():
    # RSI must stay in [0, 100]
    rng = np.random.default_rng(42)
    s = _series(rng.normal(loc=100, scale=2, size=300).cumsum())
    out = rsi(s, 14).dropna()
    assert (out >= 0).all() and (out <= 100).all()


def test_add_smas_adds_two_columns():
    df = pd.DataFrame({"close": np.arange(100, dtype=float)})
    enriched = add_smas(df, 5, 20)
    assert "sma_5" in enriched.columns
    assert "sma_20" in enriched.columns
    assert len(enriched) == len(df)
