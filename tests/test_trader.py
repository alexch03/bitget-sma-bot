from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

from src.config import Config
from src.trader import Trader


def _df(close_values):
    n = len(close_values)
    idx = pd.date_range("2026-01-01", periods=n, freq="1h", tz="UTC")
    return pd.DataFrame({
        "open": close_values,
        "high": close_values,
        "low": close_values,
        "close": close_values,
        "volume": [1.0] * n,
    }, index=idx)


def _cfg(mode):
    return Config(
        api_key="k", api_secret="s", api_password="p",
        mode=mode, confirm_live=True,
        symbol="BTC/USDT:USDT", timeframe="1h",
        sma_fast=5, sma_slow=20,
        risk_pct=2.0, paper_balance=1000.0,
        telegram_bot_token="", telegram_chat_id="",
        web_host="127.0.0.1", web_port=5000,
        log_level="WARNING",
    )


def _trader(mode, df, monkeypatch, tmp_path):
    cfg = _cfg(mode)
    # isolate state.json per test
    from src import trader as trader_mod
    monkeypatch.setattr(trader_mod, "STATE_FILE", tmp_path / "state.json")
    exchange = MagicMock()
    exchange.fetch_ohlcv.return_value = df
    exchange.fetch_balance_usdt.return_value = 1000.0
    exchange.market_order.return_value = {"id": "fake", "status": "closed"}
    notifier = MagicMock()
    notifier.is_enabled.return_value = False
    return Trader(cfg, exchange, notifier), exchange


def test_paper_open_updates_book(monkeypatch, tmp_path):
    df = _df([100.0] * 34 + [115.0])  # bullish cross at last bar
    trader, _ = _trader("paper", df, monkeypatch, tmp_path)
    assert trader.book.position is None
    trader.step()
    assert trader.book.position is not None
    assert trader.book.position.side == "long"


def test_live_open_places_order_AND_tracks_position(monkeypatch, tmp_path):
    """Regression: in live mode, _open must update book.position too,
    otherwise the next tick would think we are flat and open a duplicate order.
    """
    df = _df([100.0] * 34 + [115.0])
    trader, exchange = _trader("live", df, monkeypatch, tmp_path)
    trader.step()
    # order placed once
    assert exchange.market_order.call_count == 1
    args = exchange.market_order.call_args.args
    assert args[1] == "buy"
    # AND local position tracked
    assert trader.book.position is not None
    assert trader.book.position.side == "long"


def test_live_does_not_re_open_on_next_tick_if_no_cross(monkeypatch, tmp_path):
    df = _df([100.0] * 34 + [115.0])
    trader, exchange = _trader("live", df, monkeypatch, tmp_path)
    trader.step()
    # second tick: same data → decision is "no cross" → must not place a new order
    trader.step()
    assert exchange.market_order.call_count == 1


def test_live_flip_closes_and_reopens(monkeypatch, tmp_path):
    df_up = _df([100.0] * 34 + [115.0])         # bullish cross
    df_down = _df([100.0] * 34 + [85.0])        # bearish cross
    trader, exchange = _trader("live", df_up, monkeypatch, tmp_path)
    trader.step()
    assert trader.book.position.side == "long"
    # next tick: data shows a bearish cross → close + open short
    exchange.fetch_ohlcv.return_value = df_down
    trader.step()
    assert exchange.market_order.call_count == 3  # close long + open short
    assert trader.book.position.side == "short"


def test_dry_places_no_order_but_logs(monkeypatch, tmp_path):
    df = _df([100.0] * 34 + [115.0])
    trader, exchange = _trader("dry", df, monkeypatch, tmp_path)
    trader.step()
    exchange.market_order.assert_not_called()
    # in dry we do not track a fake position either
    assert trader.book.position is None
