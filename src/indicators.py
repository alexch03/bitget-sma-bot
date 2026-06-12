import numpy as np
import pandas as pd


def sma(series: pd.Series, length: int) -> pd.Series:
    return series.rolling(window=length, min_periods=length).mean()


def ema(series: pd.Series, length: int) -> pd.Series:
    return series.ewm(span=length, adjust=False, min_periods=length).mean()


def rsi(series: pd.Series, length: int = 14) -> pd.Series:
    delta = series.diff()
    up = delta.clip(lower=0).rolling(length).mean()
    down = -delta.clip(upper=0).rolling(length).mean()
    rs = up / down.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def add_smas(df: pd.DataFrame, fast: int, slow: int) -> pd.DataFrame:
    out = df.copy()
    out[f"sma_{fast}"] = sma(out["close"], fast)
    out[f"sma_{slow}"] = sma(out["close"], slow)
    return out


def bollinger_bands(series: pd.Series, period: int = 20, std: float = 2.0):
    """Return (middle, upper, lower) bands. Middle is SMA, std is the multiplier."""
    middle = series.rolling(window=period, min_periods=period).mean()
    sd = series.rolling(window=period, min_periods=period).std(ddof=0)
    upper = middle + std * sd
    lower = middle - std * sd
    return middle, upper, lower
