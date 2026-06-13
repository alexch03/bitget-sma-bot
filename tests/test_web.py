"""API contract tests for src.web — Flask endpoints.

No network: the BitgetExchange wrapper is monkey-patched to return canned
DataFrames and balances. The bot subprocess is never actually spawned in
unit tests; we only verify our endpoints' behaviour and JSON shapes.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# Fixtures


def _fake_ohlcv(n: int = 60, base: float = 60000.0) -> pd.DataFrame:
    idx = pd.date_range("2026-01-01", periods=n, freq="1h", tz="UTC")
    return pd.DataFrame({
        "open": [base + i for i in range(n)],
        "high": [base + i + 5 for i in range(n)],
        "low":  [base + i - 5 for i in range(n)],
        "close":[base + i + 1 for i in range(n)],
        "volume": [1.0] * n,
    }, index=idx)


@pytest.fixture
def isolated_repo(tmp_path, monkeypatch):
    """Run each test against a temporary REPO_ROOT so .env / state.json /
    control.json never leak between tests."""
    env_file = tmp_path / ".env"
    env_file.write_text(
        "MODE=paper\n"
        "STRATEGY=sma_crossover\n"
        "SYMBOL=BTC/USDT:USDT\n"
        "TIMEFRAME=1h\n"
        "SMA_FAST=20\n"
        "SMA_SLOW=50\n"
        "RISK_PCT=2.0\n"
        "STOP_LOSS_PCT=0\n"
        "TAKE_PROFIT_PCT=0\n"
        "PAPER_BALANCE=1000\n"
        "BB_PERIOD=20\nBB_STD=2.0\n"
        "RSI_PERIOD=14\nRSI_OVERSOLD=30\nRSI_OVERBOUGHT=70\n"
        "WEB_HOST=127.0.0.1\nWEB_PORT=5000\n"
        "LOG_LEVEL=WARNING\n"
        "BITGET_API_KEY=\nBITGET_API_SECRET=\nBITGET_API_PASSWORD=\n"
        "TELEGRAM_BOT_TOKEN=\nTELEGRAM_CHAT_ID=\n"
    )

    # Point every src module that holds a REPO_ROOT to tmp_path
    import importlib
    from src import config as cfg_mod
    from src import web as web_mod
    from src import trader as trader_mod

    monkeypatch.setattr(cfg_mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(web_mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(web_mod, "ENV_FILE", env_file)
    monkeypatch.setattr(web_mod, "RUNTIME_FILE", tmp_path / "runtime.json")
    monkeypatch.setattr(web_mod, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(web_mod, "CONTROL_FILE", tmp_path / "control.json")
    monkeypatch.setattr(web_mod, "STATUS_FILE", tmp_path / "bot_status.json")
    monkeypatch.setattr(web_mod, "TRADES_FILE", tmp_path / "trades.jsonl")
    monkeypatch.setattr(trader_mod, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(trader_mod, "CONTROL_FILE", tmp_path / "control.json")
    monkeypatch.setattr(trader_mod, "STATUS_FILE", tmp_path / "bot_status.json")
    monkeypatch.setattr(trader_mod, "TRADES_FILE", tmp_path / "trades.jsonl")

    # Force the dotenv loader to re-read from the new path
    from dotenv import load_dotenv
    load_dotenv(env_file, override=True)

    # Also override env vars that may have leaked from the developer's real .env
    for key, value in [
        ("MODE", "paper"),
        ("STRATEGY", "sma_crossover"),
        ("SYMBOL", "BTC/USDT:USDT"),
        ("TIMEFRAME", "1h"),
        ("BITGET_API_KEY", ""),
        ("BITGET_API_SECRET", ""),
        ("BITGET_API_PASSWORD", ""),
        ("CONFIRM_LIVE", "no"),
        ("STOP_LOSS_PCT", "0"),
        ("TAKE_PROFIT_PCT", "0"),
        ("RISK_PCT", "2.0"),
        ("SMA_FAST", "20"),
        ("SMA_SLOW", "50"),
    ]:
        monkeypatch.setenv(key, value)

    return tmp_path


@pytest.fixture
def client(isolated_repo, monkeypatch):
    """A Flask test client with the exchange mocked out (no network)."""
    fake_ex = MagicMock()
    fake_ex.fetch_ohlcv.return_value = _fake_ohlcv()
    fake_ex.fetch_ticker_price.return_value = 60010.0
    fake_ex.fetch_balance_usdt.return_value = 5000.0
    fake_ex.client.load_markets.return_value = {
        "BTC/USDT:USDT": {"swap": True, "linear": True, "quote": "USDT", "active": True},
        "ETH/USDT:USDT": {"swap": True, "linear": True, "quote": "USDT", "active": True},
        "DOGE/USDT:USDT": {"swap": True, "linear": True, "quote": "USDT", "active": True},
        "BTCUSD_PERP": {"swap": True, "linear": False, "quote": "USD", "active": True},  # filtered out
    }

    from src import web as web_mod
    monkeypatch.setattr(web_mod, "build_exchange", lambda cfg: fake_ex, raising=False)

    # Also patch the import inside _ensure_exchange (lazy import)
    import src.exchange as ex_mod
    monkeypatch.setattr(ex_mod, "BitgetExchange", lambda cfg: fake_ex, raising=False)
    monkeypatch.setattr(ex_mod, "build_exchange", lambda cfg: fake_ex, raising=False)

    app = web_mod.create_app()
    app.testing = True
    return app.test_client()


# ---------------------------------------------------------------------------
# GET endpoints


def test_index_returns_dashboard_html(client):
    r = client.get("/")
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "bitget-sma-bot" in body
    assert "lightweight-charts" in body
    assert "/api/status" in body


def test_status_shape(client):
    r = client.get("/api/status")
    assert r.status_code == 200
    s = r.get_json()
    expected_keys = {
        "mode", "symbol", "timeframe", "strategy", "strategy_params",
        "risk_pct", "stop_loss_pct", "take_profit_pct",
        "sma_fast", "sma_slow", "bb_period", "bb_std",
        "rsi_period", "rsi_oversold", "rsi_overbought",
        "paper_balance", "current_price", "balance", "balance_source",
        "position", "unrealized_pnl", "unrealized_pnl_pct",
        "telegram_enabled", "api_auth_ok", "fetched_at",
        "bot", "available_strategies", "available_modes",
    }
    missing = expected_keys - set(s)
    assert not missing, f"missing keys: {missing}"
    assert s["mode"] == "paper"
    assert set(s["available_strategies"]) == {"sma_crossover", "bollinger", "rsi_mean_revert"}
    assert "running" in s["bot"]


def test_candles_returns_list_of_ohlcv(client):
    r = client.get("/api/candles?limit=30")
    assert r.status_code == 200
    data = r.get_json()
    assert isinstance(data, list)
    assert len(data) > 0
    for k in ("time", "open", "high", "low", "close"):
        assert k in data[0]


def test_indicators_aligned_with_candles(client):
    r = client.get("/api/indicators")
    assert r.status_code == 200
    ind = r.get_json()
    assert "sma_fast" in ind and "sma_slow" in ind
    if ind["sma_fast"]:
        assert {"time", "value"} <= set(ind["sma_fast"][0])


def test_trades_empty_when_no_history(client):
    r = client.get("/api/trades")
    assert r.status_code == 200
    assert r.get_json() == []


def test_trades_returns_appended_entries(client, isolated_repo):
    trades = [
        {"closed_at": 1, "side": "long", "entry_price": 100, "exit_price": 110, "pnl": 1.0, "reason": "signal"},
        {"closed_at": 2, "side": "short", "entry_price": 110, "exit_price": 105, "pnl": 0.5, "reason": "TP"},
    ]
    (isolated_repo / "trades.jsonl").write_text("\n".join(json.dumps(t) for t in trades))
    r = client.get("/api/trades")
    assert r.status_code == 200
    data = r.get_json()
    assert len(data) == 2
    # newest first
    assert data[0]["reason"] == "TP"


def test_equity_curve_built_from_trades(client, isolated_repo):
    (isolated_repo / "trades.jsonl").write_text(
        json.dumps({"closed_at": 1, "pnl": 10.0}) + "\n" +
        json.dumps({"closed_at": 2, "pnl": -3.0}) + "\n"
    )
    r = client.get("/api/equity")
    assert r.status_code == 200
    data = r.get_json()
    assert len(data) == 2
    # paper balance starts at 1000, so: 1010, 1007
    assert data[0]["value"] == 1010.0
    assert data[1]["value"] == 1007.0


def test_logs_initially_empty(client):
    r = client.get("/api/logs")
    assert r.status_code == 200
    assert r.get_json() == {"lines": []}


def test_symbols_returns_filtered_swap_usdt(client):
    r = client.get("/api/symbols")
    assert r.status_code == 200
    data = r.get_json()
    assert isinstance(data, list)
    # only swap + linear + USDT should pass the filter
    assert "BTC/USDT:USDT" in data
    assert "ETH/USDT:USDT" in data
    assert "BTCUSD_PERP" not in data
    # BTC must be first thanks to the priority list
    assert data[0] == "BTC/USDT:USDT"


# ---------------------------------------------------------------------------
# POST /api/config — env writer


def test_config_post_updates_env_file(client, isolated_repo):
    r = client.post("/api/config", json={"SMA_FAST": "10", "SMA_SLOW": "40"})
    assert r.status_code == 200
    j = r.get_json()
    assert j["ok"] is True
    assert set(j["updated"]) == {"SMA_FAST", "SMA_SLOW"}
    env_text = (isolated_repo / ".env").read_text()
    assert "SMA_FAST=10" in env_text
    assert "SMA_SLOW=40" in env_text


def test_config_post_rejects_unknown_keys(client):
    r = client.post("/api/config", json={"EVIL_KEY": "ha"})
    assert r.status_code == 400
    assert "forbidden" in r.get_json()["error"].lower()


def test_config_post_validates_mode_enum(client):
    r = client.post("/api/config", json={"MODE": "blockchain"})
    assert r.status_code == 400
    assert "MODE" in r.get_json()["error"]


def test_config_post_validates_strategy_enum(client):
    r = client.post("/api/config", json={"STRATEGY": "ai_alpha"})
    assert r.status_code == 400
    assert "STRATEGY" in r.get_json()["error"]


def test_config_post_invalid_json(client):
    r = client.post("/api/config", data="not json", content_type="application/json")
    assert r.status_code == 400


def test_config_post_keys_not_in_whitelist_not_exposed(client):
    # BITGET_API_KEY must not be settable via the UI for safety
    r = client.post("/api/config", json={"BITGET_API_KEY": "lol"})
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# Bot control endpoints (subprocess mocked)


def test_bot_pause_then_resume_roundtrip(client, isolated_repo):
    r1 = client.post("/api/bot/pause")
    assert r1.status_code == 200
    assert r1.get_json()["paused"] is True
    ctrl = json.loads((isolated_repo / "control.json").read_text())
    assert ctrl["paused"] is True

    r2 = client.post("/api/bot/resume")
    assert r2.status_code == 200
    assert r2.get_json()["paused"] is False


def test_position_close_sets_force_close_flag(client, isolated_repo):
    r = client.post("/api/position/close")
    assert r.status_code == 200
    assert r.get_json()["ok"] is True
    ctrl = json.loads((isolated_repo / "control.json").read_text())
    assert ctrl["force_close"] is True


def test_bot_start_when_not_running(client, monkeypatch):
    """We mock Popen so we never actually spawn the bot."""
    from src import web as web_mod

    fake_proc = MagicMock()
    fake_proc.poll.return_value = None
    fake_proc.pid = 42424
    fake_proc.stdout = MagicMock()
    monkeypatch.setattr(web_mod, "_bot_process", None, raising=False)
    monkeypatch.setattr(web_mod.subprocess, "Popen", lambda *a, **k: fake_proc)

    r = client.post("/api/bot/start")
    assert r.status_code == 200
    assert r.get_json()["ok"] is True

    # second start should refuse
    r2 = client.post("/api/bot/start")
    assert r2.status_code == 409


def test_bot_stop_when_not_running(client, monkeypatch):
    from src import web as web_mod
    monkeypatch.setattr(web_mod, "_bot_process", None, raising=False)
    r = client.post("/api/bot/stop")
    assert r.status_code == 409
    assert r.get_json()["ok"] is False


# ---------------------------------------------------------------------------
# encoding sanity


def test_no_em_dashes_in_python_outputs():
    """Anything printed to stdout from our code should be 7-bit ASCII so it
    doesn't crash on a Windows cp1252 console without explicit UTF-8."""
    repo = Path(__file__).resolve().parent.parent
    offenders = []
    bad_chars = {"—", "–", "‘", "’", "“", "”", "→"}
    for py in repo.rglob("src/**/*.py"):
        text = py.read_text(encoding="utf-8")
        for ln, line in enumerate(text.splitlines(), 1):
            stripped = line.split("#", 1)[0]  # ignore comments
            for ch in bad_chars:
                if ch in stripped:
                    # skip if it's clearly inside an html template string
                    if "DASHBOARD_HTML" in py.read_text(encoding="utf-8"):
                        # the html template uses em-dashes but those go to the
                        # browser as utf-8 — that's fine
                        continue
                    offenders.append(f"{py.name}:{ln} contains {ch!r}: {line[:80]}")
    assert not offenders, "non-ascii output chars found:\n" + "\n".join(offenders)
