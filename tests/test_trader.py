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


def _cfg(mode, stop_loss_pct=0.0, take_profit_pct=0.0, strategy="sma_crossover"):
    return Config(
        api_key="k", api_secret="s", api_password="p",
        mode=mode, confirm_live=True,
        symbol="BTC/USDT:USDT", timeframe="1h",
        strategy=strategy,
        sma_fast=5, sma_slow=20,
        bb_period=20, bb_std=2.0,
        rsi_period=14, rsi_oversold=30, rsi_overbought=70,
        risk_pct=2.0,
        stop_loss_pct=stop_loss_pct,
        take_profit_pct=take_profit_pct,
        paper_balance=1000.0,
        telegram_bot_token="", telegram_chat_id="",
        web_host="127.0.0.1", web_port=5000,
        log_level="WARNING",
    )


def _trader(mode, df, monkeypatch, tmp_path, **cfg_overrides):
    cfg = _cfg(mode, **cfg_overrides)
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


def test_demo_places_orders_like_live(monkeypatch, tmp_path):
    """Demo mode = real orders on the demo exchange. Same code path as live,
    just different keys and paptrading: 1 header set in exchange.py."""
    df = _df([100.0] * 34 + [115.0])
    trader, exchange = _trader("demo", df, monkeypatch, tmp_path)
    trader.step()
    assert exchange.market_order.call_count == 1
    assert exchange.market_order.call_args.args[1] == "buy"
    assert trader.book.position is not None
    assert trader.book.position.side == "long"


def test_demo_flip_closes_and_reopens(monkeypatch, tmp_path):
    df_up = _df([100.0] * 34 + [115.0])
    df_down = _df([100.0] * 34 + [85.0])
    trader, exchange = _trader("demo", df_up, monkeypatch, tmp_path)
    trader.step()
    exchange.fetch_ohlcv.return_value = df_down
    trader.step()
    assert exchange.market_order.call_count == 3
    assert trader.book.position.side == "short"


def test_stop_loss_closes_long(monkeypatch, tmp_path):
    # Open a long, then next tick the price has dropped past the SL
    df_up = _df([100.0] * 34 + [115.0])
    trader, exchange = _trader("paper", df_up, monkeypatch, tmp_path, stop_loss_pct=5.0)
    trader.step()
    assert trader.book.position.side == "long"
    entry = trader.book.position.entry_price

    # Next tick: price drops more than 5% below entry → SL triggers
    df_drop = _df([100.0] * 34 + [115.0] + [entry * 0.93])
    exchange.fetch_ohlcv.return_value = df_drop
    trader.step()
    assert trader.book.position is None


def test_take_profit_closes_long(monkeypatch, tmp_path):
    df_up = _df([100.0] * 34 + [115.0])
    trader, exchange = _trader("paper", df_up, monkeypatch, tmp_path, take_profit_pct=3.0)
    trader.step()
    assert trader.book.position.side == "long"
    entry = trader.book.position.entry_price

    df_pump = _df([100.0] * 34 + [115.0] + [entry * 1.05])
    exchange.fetch_ohlcv.return_value = df_pump
    trader.step()
    assert trader.book.position is None


def test_stop_loss_closes_short(monkeypatch, tmp_path):
    df_down = _df([100.0] * 34 + [85.0])
    trader, exchange = _trader("paper", df_down, monkeypatch, tmp_path, stop_loss_pct=5.0)
    trader.step()
    assert trader.book.position.side == "short"
    entry = trader.book.position.entry_price

    df_pump = _df([100.0] * 34 + [85.0] + [entry * 1.07])
    exchange.fetch_ohlcv.return_value = df_pump
    trader.step()
    assert trader.book.position is None


def test_no_sl_tp_when_disabled(monkeypatch, tmp_path):
    df_up = _df([100.0] * 34 + [115.0])
    trader, exchange = _trader("paper", df_up, monkeypatch, tmp_path,
                                stop_loss_pct=0.0, take_profit_pct=0.0)
    trader.step()
    assert trader.book.position is not None
    entry = trader.book.position.entry_price

    # Even with a massive drop, no SL exit because SL_PCT=0 (disabled)
    df_crash = _df([100.0] * 34 + [115.0] + [entry * 0.5])
    exchange.fetch_ohlcv.return_value = df_crash
    trader.step()
    # position is still open (no signal flip, no SL)
    assert trader.book.position is not None


def test_strategy_switch_to_bollinger(monkeypatch, tmp_path):
    # Use a price series that triggers a Bollinger breakout up on the last bar
    closes = [100.0] * 30 + [100.5, 99.5, 100.5, 99.5, 130.0]
    df = _df(closes)
    trader, _ = _trader("paper", df, monkeypatch, tmp_path, strategy="bollinger")
    trader.step()
    assert trader.strategy.name == "bollinger"
