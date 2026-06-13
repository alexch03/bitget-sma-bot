from __future__ import annotations

import json
import logging
import os
import re
import signal
import subprocess
import sys
import time
from collections import deque
from pathlib import Path
from threading import Lock, Thread
from typing import Any

from flask import Flask, jsonify, render_template_string, request

from .config import VALID_MODES, VALID_STRATEGIES, load_config


log = logging.getLogger(__name__)


REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = REPO_ROOT / ".env"
RUNTIME_FILE = REPO_ROOT / "runtime.json"
STATE_FILE = REPO_ROOT / "state.json"
CONTROL_FILE = REPO_ROOT / "control.json"
STATUS_FILE = REPO_ROOT / "bot_status.json"
TRADES_FILE = REPO_ROOT / "trades.jsonl"

# Bitget partner / referral link maintained by the project owner.
# Used in the dashboard CTA and shown in the docs.
BITGET_REFERRAL_CODE = "9K5D7K4J"
BITGET_REFERRAL_URL = (
    f"https://www.bitget.com/expressly?languageType=0"
    f"&channelCode={BITGET_REFERRAL_CODE}&vipCode={BITGET_REFERRAL_CODE}"
)


# ---------------------------------------------------------------------------
# Bot subprocess management


_bot_lock = Lock()
_bot_process: subprocess.Popen | None = None
_bot_log: deque[str] = deque(maxlen=400)
_bot_started_at: float | None = None


def _read_json(path: Path) -> dict[str, Any]:
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            return {}
    return {}


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2))


def _read_trades(limit: int = 50) -> list[dict]:
    if not TRADES_FILE.exists():
        return []
    try:
        lines = TRADES_FILE.read_text().strip().splitlines()
        out = []
        for line in lines[-limit:]:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return list(reversed(out))
    except Exception:
        return []


def _is_bot_running() -> bool:
    global _bot_process
    if _bot_process is None:
        return False
    if _bot_process.poll() is not None:
        _bot_process = None
        return False
    return True


def _bot_reader(stream) -> None:
    """Forward bot subprocess output into our in-memory log ring."""
    try:
        for line in iter(stream.readline, ""):
            if not line:
                break
            _bot_log.append(line.rstrip())
    except Exception:
        pass


def _spawn_bot() -> tuple[bool, str]:
    global _bot_process, _bot_started_at
    with _bot_lock:
        if _is_bot_running():
            return False, "bot is already running"

        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        env.setdefault("PYTHONIOENCODING", "utf-8")
        _bot_process = subprocess.Popen(
            [sys.executable, "-m", "src.main"],
            cwd=str(REPO_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",      # explicit so windows doesn't default to cp1252
            errors="replace",      # never raise on a bad byte
            bufsize=1,
            env=env,
        )
        _bot_started_at = time.time()
        Thread(target=_bot_reader, args=(_bot_process.stdout,), daemon=True).start()
        # Make sure control.json is in a clean "running, not paused" state
        ctrl = _read_json(CONTROL_FILE)
        ctrl.update({"paused": False, "force_close": False})
        _write_json(CONTROL_FILE, ctrl)
        return True, f"started (pid={_bot_process.pid})"


def _stop_bot() -> tuple[bool, str]:
    global _bot_process, _bot_started_at
    with _bot_lock:
        if not _is_bot_running():
            return False, "bot was not running"

        proc = _bot_process
        try:
            if sys.platform == "win32":
                proc.terminate()
            else:
                proc.send_signal(signal.SIGTERM)
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()
        except Exception as exc:
            log.warning("error stopping bot: %s", exc)

        _bot_process = None
        _bot_started_at = None
        return True, "stopped"


# ---------------------------------------------------------------------------
# .env editor — minimal, only known keys


ENV_KEYS_ALLOWED = {
    "MODE", "STRATEGY",
    "SYMBOL", "TIMEFRAME",
    "SMA_FAST", "SMA_SLOW",
    "BB_PERIOD", "BB_STD",
    "RSI_PERIOD", "RSI_OVERSOLD", "RSI_OVERBOUGHT",
    "RISK_PCT", "STOP_LOSS_PCT", "TAKE_PROFIT_PCT",
    "PAPER_BALANCE",
    "CONFIRM_LIVE",
    "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID",
    # NOT exposed to the UI: BITGET_* keys — edit manually for safety
}


def _env_set(updates: dict[str, str]) -> None:
    """Update / create the listed keys in .env (preserves the rest)."""
    text = ENV_FILE.read_text() if ENV_FILE.exists() else ""
    lines = text.splitlines()
    remaining = dict(updates)

    new_lines: list[str] = []
    for line in lines:
        m = re.match(r"^([A-Z_][A-Z0-9_]*)=", line)
        if m and m.group(1) in remaining:
            key = m.group(1)
            new_lines.append(f"{key}={remaining.pop(key)}")
        else:
            new_lines.append(line)
    for key, value in remaining.items():
        new_lines.append(f"{key}={value}")

    ENV_FILE.write_text("\n".join(new_lines) + "\n")


# ---------------------------------------------------------------------------
# Indicators helper (for chart overlay)


def _sma(values: list[float], length: int) -> list[float | None]:
    out: list[float | None] = []
    s = 0.0
    for i, v in enumerate(values):
        s += v
        if i >= length:
            s -= values[i - length]
        if i >= length - 1:
            out.append(s / length)
        else:
            out.append(None)
    return out


# ---------------------------------------------------------------------------
# Flask app


def create_app():
    app = Flask(__name__)

    cache: dict[str, Any] = {"ts": 0, "balance": None, "price": None, "candles": None,
                              "candles_ts": 0, "auth_ok": None, "exchange": None}

    def _cfg():
        # Reload config on every request so config changes take effect for the UI
        # without restarting Flask. The bot subprocess gets the changes via the
        # restart cycle (Save Config -> Restart Bot button).
        return load_config()

    def _ensure_exchange():
        cfg = _cfg()
        cur = cache.get("exchange")
        cur_signature = (cfg.mode, cfg.api_key, cfg.api_secret)
        if cur is None or cache.get("exchange_sig") != cur_signature:
            from .exchange import build_exchange
            cache["exchange"] = build_exchange(cfg)
            cache["exchange_sig"] = cur_signature
        return cache["exchange"]

    def _fresh_price_and_balance(force: bool = False):
        cfg = _cfg()
        now = time.time()
        if not force and now - cache["ts"] < 5 and cache["price"] is not None:
            return cache["price"], cache["balance"], cache["auth_ok"]
        try:
            ex = _ensure_exchange()
            cache["price"] = ex.fetch_ticker_price(cfg.symbol)
        except Exception:
            cache["price"] = None
        if cfg.mode == "paper":
            cache["balance"] = None
            cache["auth_ok"] = None
        else:
            try:
                ex = _ensure_exchange()
                cache["balance"] = ex.fetch_balance_usdt()
                cache["auth_ok"] = True
            except Exception:
                cache["balance"] = None
                cache["auth_ok"] = False
        cache["ts"] = now
        return cache["price"], cache["balance"], cache["auth_ok"]

    def _fresh_candles_for(symbol: str, timeframe: str, limit: int = 200):
        """Fetch (and cache for 25s) the OHLCV of any symbol/timeframe pair."""
        key = (symbol, timeframe)
        candles_cache = cache.setdefault("candles_by_key", {})
        cached = candles_cache.get(key)
        now = time.time()
        if cached and now - cached["ts"] < 25:
            return cached["data"]
        try:
            ex = _ensure_exchange()
            df = ex.fetch_ohlcv(symbol, timeframe, limit=limit)
            arr = []
            for ts, row in df.iterrows():
                arr.append({
                    "time": int(ts.timestamp()),
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                })
            candles_cache[key] = {"ts": now, "data": arr}
            return arr
        except Exception:
            return cached["data"] if cached else []

    # ----- routes ----------------------------------------------------------

    @app.route("/", methods=["GET"])
    def index():
        return render_template_string(
            DASHBOARD_HTML,
            BITGET_REFERRAL_URL=BITGET_REFERRAL_URL,
            BITGET_REFERRAL_CODE=BITGET_REFERRAL_CODE,
        )

    @app.route("/api/status", methods=["GET"])
    def api_status():
        cfg = _cfg()
        overrides = _read_json(RUNTIME_FILE)
        state = _read_json(STATE_FILE)
        bot_status = _read_json(STATUS_FILE)
        ctrl = _read_json(CONTROL_FILE)

        price, balance, auth_ok = _fresh_price_and_balance()

        pos = state.get("position") or (bot_status.get("position") if bot_status else None)
        position_obj = None
        unrealized_pnl = None
        unrealized_pnl_pct = None
        if pos and price is not None:
            direction = 1 if pos["side"] == "long" else -1
            unrealized_pnl = direction * (price - pos["entry_price"]) * pos["amount"]
            unrealized_pnl_pct = direction * (price - pos["entry_price"]) / pos["entry_price"] * 100
        if pos:
            position_obj = {
                "side": pos["side"],
                "amount": pos["amount"],
                "entry_price": pos["entry_price"],
                "opened_at": pos.get("opened_at"),
            }

        if cfg.mode == "paper":
            balance_val = state.get("balance", cfg.paper_balance)
            balance_source = "paper"
        else:
            balance_val = balance
            balance_source = "exchange"

        running = _is_bot_running()
        bot_running_for = (time.time() - _bot_started_at) if (running and _bot_started_at) else None

        return jsonify({
            "mode": cfg.mode,
            "symbol": cfg.symbol,
            "timeframe": cfg.timeframe,
            "strategy": cfg.strategy,
            "strategy_params": cfg.strategy_params(),
            "risk_pct": cfg.risk_pct,
            "stop_loss_pct": cfg.stop_loss_pct,
            "take_profit_pct": cfg.take_profit_pct,
            "sma_fast": cfg.sma_fast,
            "sma_slow": cfg.sma_slow,
            "bb_period": cfg.bb_period,
            "bb_std": cfg.bb_std,
            "rsi_period": cfg.rsi_period,
            "rsi_oversold": cfg.rsi_oversold,
            "rsi_overbought": cfg.rsi_overbought,
            "paper_balance": cfg.paper_balance,
            "current_price": price,
            "balance": balance_val,
            "balance_source": balance_source,
            "position": position_obj,
            "unrealized_pnl": unrealized_pnl,
            "unrealized_pnl_pct": unrealized_pnl_pct,
            "telegram_enabled": cfg.telegram_enabled,
            "api_auth_ok": auth_ok,
            "fetched_at": int(cache["ts"]),
            "bot": {
                "running": running,
                "running_for_seconds": bot_running_for,
                "paused": bool(ctrl.get("paused")),
                "force_close_pending": bool(ctrl.get("force_close")),
                "last_tick_at": bot_status.get("last_tick_at"),
                "last_signal": bot_status.get("last_signal"),
                "last_reason": bot_status.get("last_reason"),
                "last_price": bot_status.get("last_price"),
            },
            "available_strategies": list(VALID_STRATEGIES),
            "available_modes": list(VALID_MODES),
        })

    @app.route("/api/candles", methods=["GET"])
    def api_candles():
        cfg = _cfg()
        symbol = request.args.get("symbol", cfg.symbol)
        timeframe = request.args.get("timeframe", cfg.timeframe)
        limit = int(request.args.get("limit", 200))
        return jsonify(_fresh_candles_for(symbol, timeframe, limit))

    @app.route("/api/indicators", methods=["GET"])
    def api_indicators():
        """SMA fast/slow series for the requested symbol/timeframe.

        The SMA lengths still come from the bot config (the strategy itself),
        only the underlying price series changes."""
        cfg = _cfg()
        symbol = request.args.get("symbol", cfg.symbol)
        timeframe = request.args.get("timeframe", cfg.timeframe)
        arr = _fresh_candles_for(symbol, timeframe, 200)
        closes = [c["close"] for c in arr]
        fast = _sma(closes, cfg.sma_fast)
        slow = _sma(closes, cfg.sma_slow)
        out = {"sma_fast": [], "sma_slow": []}
        for i, c in enumerate(arr):
            if fast[i] is not None:
                out["sma_fast"].append({"time": c["time"], "value": fast[i]})
            if slow[i] is not None:
                out["sma_slow"].append({"time": c["time"], "value": slow[i]})
        return jsonify(out)

    @app.route("/api/trades", methods=["GET"])
    def api_trades():
        return jsonify(_read_trades(50))

    @app.route("/api/equity", methods=["GET"])
    def api_equity():
        trades = _read_trades(500)[::-1]  # oldest first
        cfg = _cfg()
        bal = cfg.paper_balance
        out = []
        for t in trades:
            bal += float(t.get("pnl") or 0.0)
            out.append({"time": int(t.get("closed_at", 0)), "value": round(bal, 4)})
        return jsonify(out)

    @app.route("/api/logs", methods=["GET"])
    def api_logs():
        return jsonify({"lines": list(_bot_log)[-200:]})

    @app.route("/api/symbols", methods=["GET"])
    def api_symbols():
        """Return the list of Bitget USDT-M swap symbols. Cached 1h."""
        now = time.time()
        if cache.get("symbols_ts") and now - cache["symbols_ts"] < 3600 and cache.get("symbols"):
            return jsonify(cache["symbols"])
        try:
            ex = _ensure_exchange()
            markets = ex.client.load_markets()
            symbols = []
            for sym, m in markets.items():
                if m.get("swap") and m.get("linear") and m.get("quote") == "USDT" and m.get("active", True):
                    symbols.append(sym)
            # put the popular ones first for a nicer dropdown
            priority = ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT",
                        "BNB/USDT:USDT", "XRP/USDT:USDT", "DOGE/USDT:USDT"]
            head = [s for s in priority if s in symbols]
            tail = sorted(s for s in symbols if s not in head)
            symbols = head + tail
            cache["symbols"] = symbols
            cache["symbols_ts"] = now
            return jsonify(symbols)
        except Exception as exc:
            return jsonify({"error": str(exc), "fallback": cache.get("symbols") or []}), 200

    # ----- control endpoints ----------------------------------------------

    @app.route("/api/bot/start", methods=["POST"])
    def api_bot_start():
        ok, msg = _spawn_bot()
        return (jsonify({"ok": ok, "message": msg}), 200 if ok else 409)

    @app.route("/api/bot/stop", methods=["POST"])
    def api_bot_stop():
        ok, msg = _stop_bot()
        return (jsonify({"ok": ok, "message": msg}), 200 if ok else 409)

    @app.route("/api/bot/pause", methods=["POST"])
    def api_bot_pause():
        ctrl = _read_json(CONTROL_FILE)
        ctrl["paused"] = True
        _write_json(CONTROL_FILE, ctrl)
        return jsonify({"ok": True, "paused": True})

    @app.route("/api/bot/resume", methods=["POST"])
    def api_bot_resume():
        ctrl = _read_json(CONTROL_FILE)
        ctrl["paused"] = False
        _write_json(CONTROL_FILE, ctrl)
        return jsonify({"ok": True, "paused": False})

    @app.route("/api/position/close", methods=["POST"])
    def api_position_close():
        ctrl = _read_json(CONTROL_FILE)
        ctrl["force_close"] = True
        _write_json(CONTROL_FILE, ctrl)
        return jsonify({"ok": True, "message": "force_close flag set, bot will close on the next tick"})

    @app.route("/api/config", methods=["POST"])
    def api_config_update():
        """Update .env with the submitted keys. Doesn't auto-restart the bot.

        Body: JSON object with any of the keys in ENV_KEYS_ALLOWED. Values are
        coerced to strings.
        """
        try:
            payload = request.get_json(force=True)
        except Exception:
            return jsonify({"ok": False, "error": "invalid JSON"}), 400

        if not isinstance(payload, dict):
            return jsonify({"ok": False, "error": "JSON object expected"}), 400

        bad = [k for k in payload if k not in ENV_KEYS_ALLOWED]
        if bad:
            return jsonify({"ok": False, "error": f"unknown / forbidden keys: {bad}"}), 400

        updates = {k: str(v) for k, v in payload.items()}

        # Light sanity checks
        if "MODE" in updates and updates["MODE"] not in VALID_MODES:
            return jsonify({"ok": False, "error": f"MODE must be one of {VALID_MODES}"}), 400
        if "STRATEGY" in updates and updates["STRATEGY"] not in VALID_STRATEGIES:
            return jsonify({"ok": False, "error": f"STRATEGY must be one of {VALID_STRATEGIES}"}), 400

        _env_set(updates)

        cache["candles_ts"] = 0  # force candle re-fetch on next poll
        cache["ts"] = 0           # force balance/ticker re-fetch
        cache["exchange"] = None  # rebuild exchange (new mode/keys)

        return jsonify({
            "ok": True,
            "updated": list(updates.keys()),
            "bot_restart_recommended": _is_bot_running(),
        })

    @app.route("/api/bot/restart", methods=["POST"])
    def api_bot_restart():
        was_running = _is_bot_running()
        if was_running:
            _stop_bot()
            time.sleep(0.6)
        ok, msg = _spawn_bot()
        return jsonify({"ok": ok, "was_running": was_running, "message": msg})

    return app


# ---------------------------------------------------------------------------
# Frontend (single page)


DASHBOARD_HTML = r"""<!doctype html>
<html lang="en" class="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>bitget-sma-bot · control panel</title>
<script src="https://cdn.tailwindcss.com"></script>
<script src="https://unpkg.com/lightweight-charts@4.2.2/dist/lightweight-charts.standalone.production.js"></script>
<style>
  :root { --bg:#0b0e14; --panel:#11151f; --panel2:#0f1422; --border:#1f2937; --text:#e5e7eb; --muted:#94a3b8; --accent:#2563eb; }
  html, body { background: var(--bg); color: var(--text); }
  body { font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif; }
  .panel { background: var(--panel); border: 1px solid var(--border); border-radius: 12px; }
  .badge { display:inline-flex; align-items:center; gap:.35rem; padding:.2rem .6rem; border-radius:9999px; font-size:.72rem; font-weight:600; letter-spacing:.02em; }
  .badge-mode-paper { background:#1e293b; color:#cbd5e1; }
  .badge-mode-dry   { background:#3f3f46; color:#fbbf24; }
  .badge-mode-demo  { background:#0f3a2f; color:#34d399; }
  .badge-mode-live  { background:#3f1d1d; color:#fca5a5; }
  .badge-long  { background:#0a3a2a; color:#34d399; }
  .badge-short { background:#3a0a1f; color:#fb7185; }
  .badge-flat  { background:#1e293b; color:#94a3b8; }
  .badge-running { background:#0a3a2a; color:#34d399; }
  .badge-stopped { background:#3a0a1f; color:#fb7185; }
  .badge-paused { background:#3a2a0a; color:#fbbf24; }
  .pulse { width:.5rem; height:.5rem; border-radius:9999px; background:#34d399; box-shadow:0 0 10px #34d399; animation:pulse 2s infinite; }
  @keyframes pulse { 0%{opacity:1} 50%{opacity:.4} 100%{opacity:1} }
  input, select { background:#0b0e14; border:1px solid var(--border); color:var(--text); border-radius:8px; padding:.45rem .7rem; width:100%; font-size:.85rem; }
  input:focus, select:focus { outline: none; border-color:#3b82f6; }
  label { display:block; font-size:.7rem; color:var(--muted); margin-bottom:.2rem; text-transform: uppercase; letter-spacing:.04em; }
  button { transition: all .15s; cursor: pointer; }
  button.btn { padding:.5rem .9rem; border-radius:8px; font-weight:600; font-size:.85rem; }
  button.btn-primary { background:#2563eb; color:#fff; }
  button.btn-primary:hover { background:#1d4ed8; }
  button.btn-green { background:#059669; color:#fff; }
  button.btn-green:hover { background:#047857; }
  button.btn-red { background:#dc2626; color:#fff; }
  button.btn-red:hover { background:#b91c1c; }
  button.btn-amber { background:#d97706; color:#fff; }
  button.btn-amber:hover { background:#b45309; }
  button.btn-ghost { background:transparent; border:1px solid var(--border); color:var(--text); }
  button.btn-ghost:hover { background:#1e293b; }
  button:disabled { opacity:.4; cursor:not-allowed; }
  .stat-label { color: var(--muted); font-size:.7rem; text-transform: uppercase; letter-spacing:.05em; }
  .stat-value { font-size:1.4rem; font-weight:700; font-variant-numeric: tabular-nums; }
  .stat-value.green { color:#34d399; }
  .stat-value.red { color:#fb7185; }
  .stat-value.muted { color:#94a3b8; }
  .trade-row { display:grid; grid-template-columns: 36px 1fr 1fr 1fr 70px; gap:.4rem; padding:.45rem .6rem; border-bottom:1px solid #1f2937; font-size:.78rem; align-items:center; }
  .trade-row:last-child { border-bottom: none; }
  table.cfg { width:100%; font-size:.78rem; }
  table.cfg td { padding: .28rem .2rem; }
  table.cfg td:first-child { color: var(--muted); }
  table.cfg td:last-child { text-align: right; font-variant-numeric: tabular-nums; }
  .log-line { font-family: 'JetBrains Mono', ui-monospace, SFMono-Regular, monospace; font-size:.72rem; color:#cbd5e1; padding:.15rem 0; border-bottom:1px solid #131826; white-space:nowrap; overflow:hidden; text-overflow: ellipsis; }
  .log-line:last-child { border-bottom: none; }
  .toast { position:fixed; right:1.5rem; bottom:1.5rem; padding:.7rem 1rem; border-radius:8px; font-size:.85rem; box-shadow:0 4px 14px rgba(0,0,0,.5); animation: slidein .25s ease-out; z-index:50; }
  .toast-ok { background:#059669; color:#fff; }
  .toast-err { background:#dc2626; color:#fff; }
  @keyframes slidein { from { transform: translateY(20px); opacity:0; } to { transform: translateY(0); opacity:1; } }
  .section-title { font-size:.85rem; font-weight:600; color:#cbd5e1; margin-bottom:.6rem; display:flex; align-items:center; gap:.5rem; }
  .section-title svg { width:14px; height:14px; }
  .divider { border-top:1px solid var(--border); margin: .8rem 0; }
</style>
</head>
<body class="min-h-screen">

<!-- REFERRAL BANNER (top, always visible) -->
<div class="border-b border-emerald-500/30" style="background: linear-gradient(90deg, rgba(245,158,11,.12), rgba(16,185,129,.10), rgba(37,99,235,.12));">
  <div class="max-w-[1500px] mx-auto px-6 py-2.5 flex items-center justify-between gap-3 flex-wrap">
    <div class="flex items-center gap-3 text-sm">
      <span class="text-xl leading-none">🎁</span>
      <div class="leading-snug">
        <div>
          <strong class="text-emerald-300">Free &amp; open-source — funded by Bitget referrals.</strong>
          Sign up via this link to grab the current Bitget welcome bonus and support the project.
        </div>
        <div class="text-xs text-slate-400">
          Affiliate code <code class="bg-slate-800/80 px-1.5 py-0.5 rounded text-amber-300 font-mono">{{ BITGET_REFERRAL_CODE }}</code>
          is applied automatically when you sign up through the button.
          <a href="#referral-details" class="underline text-slate-300 hover:text-white">How does it work?</a>
        </div>
      </div>
    </div>
    <a href="{{ BITGET_REFERRAL_URL }}" target="_blank" rel="noopener"
       class="btn btn-primary inline-flex items-center gap-2 whitespace-nowrap">
      Open a Bitget account
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M5 12h14M13 6l6 6-6 6"/></svg>
    </a>
  </div>
</div>

<!-- HEADER -->
<header class="border-b border-slate-800 sticky top-0 z-10 backdrop-blur bg-slate-950/80">
  <div class="max-w-[1500px] mx-auto px-6 py-3 flex items-center justify-between flex-wrap gap-3">
    <div class="flex items-center gap-3">
      <svg width="30" height="30" viewBox="0 0 32 32" fill="none">
        <rect x="2" y="6" width="28" height="20" rx="4" fill="#2563eb"/>
        <path d="M6 19 L11 14 L15 17 L20 11 L26 14" stroke="#fff" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
        <circle cx="20" cy="11" r="1.6" fill="#fbbf24"/>
      </svg>
      <div>
        <div class="font-bold text-lg leading-tight">bitget-sma-bot</div>
        <div class="text-xs text-slate-400" id="header-sub">loading...</div>
      </div>
    </div>

    <div class="flex items-center gap-2">
      <span id="bot-state-badge" class="badge badge-stopped">STOPPED</span>
      <span id="bot-uptime" class="text-xs text-slate-400">—</span>

      <div class="ml-3 flex gap-2">
        <button id="btn-start" class="btn btn-green">Start Bot</button>
        <button id="btn-stop" class="btn btn-red" disabled>Stop Bot</button>
        <button id="btn-pause" class="btn btn-amber" disabled>Pause</button>
        <button id="btn-restart" class="btn btn-ghost" title="Stop + Start">Restart</button>
      </div>
    </div>
  </div>
</header>

<main class="max-w-[1500px] mx-auto px-6 py-5 space-y-5">

  <!-- STAT CARDS -->
  <section class="grid grid-cols-2 md:grid-cols-5 gap-3">
    <div class="panel p-3">
      <div class="stat-label">Balance</div>
      <div class="stat-value" id="stat-balance">—</div>
      <div class="text-xs text-slate-500 mt-1" id="stat-balance-source">—</div>
    </div>
    <div class="panel p-3">
      <div class="stat-label">Position</div>
      <div class="stat-value" id="stat-position"><span class="badge badge-flat">FLAT</span></div>
      <div class="text-xs text-slate-500 mt-1" id="stat-position-detail">no open position</div>
    </div>
    <div class="panel p-3">
      <div class="stat-label">Unrealized PnL</div>
      <div class="stat-value muted" id="stat-pnl">—</div>
      <div class="text-xs text-slate-500 mt-1" id="stat-pnl-pct">—</div>
    </div>
    <div class="panel p-3">
      <div class="stat-label">Last price</div>
      <div class="stat-value" id="stat-price">—</div>
      <div class="text-xs text-slate-500 mt-1" id="stat-symbol">—</div>
    </div>
    <div class="panel p-3">
      <div class="stat-label">Last signal</div>
      <div class="stat-value" id="stat-signal"><span class="badge badge-flat">—</span></div>
      <div class="text-xs text-slate-500 mt-1" id="stat-signal-when">no tick yet</div>
    </div>
  </section>

  <!-- ROW: chart + side -->
  <section class="grid grid-cols-1 lg:grid-cols-3 gap-5">
    <div class="panel p-4 lg:col-span-2">
      <div class="flex items-center justify-between mb-3 flex-wrap gap-2">
        <div>
          <div class="section-title">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 17 9 11 13 15 21 7"/></svg>
            <span id="chart-title">price</span>
          </div>
          <div class="text-xs text-slate-500" id="chart-sub">—</div>
        </div>
        <div class="flex items-center gap-2">
          <select id="chart-symbol-pick" class="text-xs" style="width:auto; min-width:160px;"></select>
          <select id="chart-tf-pick" class="text-xs" style="width:auto;">
            <option>1m</option><option>5m</option><option>15m</option>
            <option>1h</option><option>4h</option><option>1d</option>
          </select>
        </div>
      </div>
      <div id="chart-bot-notice" class="hidden text-xs text-amber-300 bg-amber-950/40 border border-amber-900 rounded-md px-3 py-2 mb-2">
        Bot is trading <strong id="chart-bot-info">—</strong> — this chart is a preview only.
        <button id="chart-reset-to-bot" class="ml-2 underline text-amber-200 hover:text-amber-100">match bot</button>
      </div>
      <div id="chart" style="width:100%;height:380px;"></div>
      <div class="mt-2 flex items-center gap-4 text-xs text-slate-400">
        <span class="flex items-center gap-1"><span class="inline-block w-3 h-0.5 bg-emerald-400"></span> SMA fast</span>
        <span class="flex items-center gap-1"><span class="inline-block w-3 h-0.5 bg-rose-400"></span> SMA slow</span>
        <span class="flex items-center gap-1"><span class="inline-block w-3 h-0.5 bg-amber-400" style="border-top:1px dashed #fbbf24"></span> entry</span>
      </div>
    </div>

    <div class="panel p-4 space-y-4">
      <div>
        <div class="section-title">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
          <span>Quick actions</span>
        </div>
        <div class="grid grid-cols-1 gap-2">
          <button id="btn-force-close" class="btn btn-amber" disabled>Force close position</button>
          <button id="btn-clear-trades" class="btn btn-ghost">Clear trade history</button>
        </div>
      </div>
      <div class="divider"></div>
      <div>
        <div class="section-title">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>
          <span>Last tick</span>
        </div>
        <table class="cfg">
          <tr><td>signal</td><td id="ticker-signal">—</td></tr>
          <tr><td>reason</td><td id="ticker-reason">—</td></tr>
          <tr><td>price</td><td id="ticker-price">—</td></tr>
          <tr><td>at</td><td id="ticker-when">—</td></tr>
        </table>
      </div>
      <div class="divider"></div>
      <div>
        <div class="section-title">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2 4 5v6c0 5 4 9 8 11 4-2 8-6 8-11V5l-8-3z"/></svg>
          <span>Connection</span>
        </div>
        <table class="cfg">
          <tr><td>mode</td><td id="conn-mode"><span class="badge">—</span></td></tr>
          <tr><td>paptrading</td><td id="conn-paptrading">—</td></tr>
          <tr><td>api auth</td><td id="conn-auth">—</td></tr>
          <tr><td>telegram</td><td id="conn-tg">—</td></tr>
        </table>
      </div>
      <div class="divider"></div>
      <div id="referral-details">
        <div class="section-title">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 12v9H4v-9"/><path d="M22 7H2v5h20V7z"/><path d="M12 22V7"/><path d="M12 7H7.5a2.5 2.5 0 0 1 0-5C11 2 12 7 12 7z"/><path d="M12 7h4.5a2.5 2.5 0 0 0 0-5C13 2 12 7 12 7z"/></svg>
          <span>How the referral funds this bot</span>
        </div>
        <div class="text-xs text-slate-400 space-y-2">
          <div>
            <div class="text-emerald-300 font-semibold mb-0.5">✓ What you get</div>
            <p>The current Bitget welcome bonus + fee discounts. The exact amount is set by Bitget and shown on the signup page.</p>
          </div>
          <div>
            <div class="text-amber-300 font-semibold mb-0.5">✓ What the project gets</div>
            <p>A share of the trading fees you pay to Bitget (no cost added to you). This is how the bot stays free and open-source — full disclosure.</p>
          </div>
          <div>
            <div class="text-blue-300 font-semibold mb-0.5">⚙ How the affiliation tracks</div>
            <p>You must register via the button above (code <code class="text-slate-300">{{ BITGET_REFERRAL_CODE }}</code> is pre-filled). KYC must be completed. The commission only kicks in on real trading volume — not on <code class="bg-slate-800 px-1 rounded">demo</code> mode.</p>
          </div>
        </div>
        <a href="{{ BITGET_REFERRAL_URL }}" target="_blank" rel="noopener"
           class="btn btn-primary block text-center mt-3">
          Open a Bitget account
        </a>
      </div>
    </div>
  </section>

  <!-- ROW: equity + trades + logs -->
  <section class="grid grid-cols-1 lg:grid-cols-3 gap-5">
    <div class="panel p-4">
      <div class="section-title">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="3" y1="12" x2="21" y2="12"/><polyline points="6 17 10 9 14 13 18 5"/></svg>
        <span>Equity curve</span>
      </div>
      <div id="equity-chart" style="width:100%;height:220px;"></div>
      <div class="text-xs text-slate-500 mt-2" id="equity-sub">built from trade pnl, starting at paper balance</div>
    </div>

    <div class="panel p-4">
      <div class="section-title">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
        <span>Recent trades</span>
      </div>
      <div class="trade-row text-xs text-slate-500 border-b border-slate-800">
        <span>side</span><span>entry</span><span>exit</span><span>pnl</span><span class="text-right">reason</span>
      </div>
      <div id="trades-body" style="max-height:220px; overflow-y:auto;">
        <div class="text-center text-slate-500 text-sm py-6">no trades yet</div>
      </div>
    </div>

    <div class="panel p-4">
      <div class="section-title">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/></svg>
        <span>Bot activity log</span>
      </div>
      <div id="logs-body" style="max-height:240px; overflow-y:auto;">
        <div class="text-center text-slate-500 text-sm py-6">no output yet — Start the bot</div>
      </div>
    </div>
  </section>

  <!-- ROW: config panels -->
  <section class="grid grid-cols-1 lg:grid-cols-3 gap-5">
    <div class="panel p-4">
      <div class="section-title">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.6 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9 1.65 1.65 0 0 0 4.27 7.18l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.6a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09A1.65 1.65 0 0 0 15 4.6a1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9c.07.32.18.62.32.91.13.29.31.55.51.78V12.61c-.2.23-.38.49-.51.78-.14.29-.25.59-.32.91z"/></svg>
        <span>Strategy</span>
      </div>
      <form id="form-strategy" class="space-y-3">
        <div>
          <label>strategy</label>
          <select name="STRATEGY" id="form-strategy-name"></select>
        </div>
        <div>
          <label>symbol <span class="text-slate-500 normal-case text-[10px]" id="symbol-count">(loading...)</span></label>
          <select name="SYMBOL" id="form-symbol"></select>
        </div>
        <div class="grid grid-cols-2 gap-2">
          <div><label>timeframe</label>
            <select name="TIMEFRAME" id="form-timeframe">
              <option>1m</option><option>5m</option><option>15m</option>
              <option>1h</option><option>4h</option><option>1d</option>
            </select>
          </div>
          <div></div>
        </div>
        <div id="strategy-params-sma" class="strategy-params grid grid-cols-2 gap-2">
          <div><label>SMA fast</label><input name="SMA_FAST" type="number" min="2"/></div>
          <div><label>SMA slow</label><input name="SMA_SLOW" type="number" min="3"/></div>
        </div>
        <div id="strategy-params-bollinger" class="strategy-params grid grid-cols-2 gap-2 hidden">
          <div><label>BB period</label><input name="BB_PERIOD" type="number" min="2"/></div>
          <div><label>BB std</label><input name="BB_STD" type="number" step="0.1" min="0.1"/></div>
        </div>
        <div id="strategy-params-rsi" class="strategy-params grid grid-cols-3 gap-2 hidden">
          <div><label>RSI period</label><input name="RSI_PERIOD" type="number" min="2"/></div>
          <div><label>oversold</label><input name="RSI_OVERSOLD" type="number" min="1" max="99"/></div>
          <div><label>overbought</label><input name="RSI_OVERBOUGHT" type="number" min="1" max="99"/></div>
        </div>
        <button type="submit" class="btn btn-primary w-full">Save strategy</button>
      </form>
    </div>

    <div class="panel p-4">
      <div class="section-title">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 11 22 2 13 21 11 13 3 11"/></svg>
        <span>Risk management</span>
      </div>
      <form id="form-risk" class="space-y-3">
        <div><label>risk per trade (%)</label><input name="RISK_PCT" type="number" step="0.1" min="0.1" max="100"/></div>
        <div><label>stop loss (% from entry, 0 = off)</label><input name="STOP_LOSS_PCT" type="number" step="0.1" min="0" max="100"/></div>
        <div><label>take profit (% from entry, 0 = off)</label><input name="TAKE_PROFIT_PCT" type="number" step="0.1" min="0"/></div>
        <div><label>paper starting balance (USDT)</label><input name="PAPER_BALANCE" type="number" min="1"/></div>
        <button type="submit" class="btn btn-primary w-full">Save risk</button>
      </form>
    </div>

    <div class="panel p-4">
      <div class="section-title">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><line x1="9" y1="9" x2="15" y2="9"/><line x1="9" y1="13" x2="15" y2="13"/><line x1="9" y1="17" x2="13" y2="17"/></svg>
        <span>Mode & alerts</span>
      </div>
      <form id="form-mode" class="space-y-3">
        <div><label>mode</label><select name="MODE" id="form-mode-select"></select></div>
        <div>
          <label>CONFIRM_LIVE (required for live)</label>
          <select name="CONFIRM_LIVE">
            <option value="no">no</option><option value="yes">yes</option>
          </select>
        </div>
        <div><label>Telegram bot token</label><input name="TELEGRAM_BOT_TOKEN" type="password" placeholder="optional"/></div>
        <div><label>Telegram chat id</label><input name="TELEGRAM_CHAT_ID" placeholder="optional"/></div>
        <button type="submit" class="btn btn-primary w-full">Save mode & alerts</button>
        <p class="text-xs text-slate-500 mt-1">Bitget keys are not exposed here. Edit <code>.env</code> directly if you need to change them.</p>
      </form>
    </div>
  </section>

  <footer class="text-center text-xs text-slate-500 pt-4 pb-8">
    bitget-sma-bot · <a href="https://github.com/alexch03/bitget-sma-bot" class="underline hover:text-slate-300">github</a> · educational use only
  </footer>
</main>

<script>
const fmt = {
  usdt: (n) => (n == null || isNaN(n)) ? '—' : Number(n).toLocaleString(undefined, {minimumFractionDigits:2, maximumFractionDigits:2}) + ' USDT',
  pct: (n) => (n == null || isNaN(n)) ? '—' : (n>=0?'+':'') + Number(n).toFixed(2) + '%',
  num: (n, d=2) => (n == null || isNaN(n)) ? '—' : Number(n).toLocaleString(undefined, {minimumFractionDigits:d, maximumFractionDigits:d}),
  duration: (s) => {
    if (s == null) return '—';
    s = Math.floor(s);
    const m = Math.floor(s/60), sec = s%60;
    if (m < 60) return m + 'm ' + sec.toString().padStart(2,'0') + 's';
    const h = Math.floor(m/60);
    return h + 'h ' + (m%60) + 'm';
  },
  ago: (ts) => {
    if (!ts) return 'never';
    const diff = (Date.now()/1000) - ts;
    if (diff < 60) return Math.floor(diff) + 's ago';
    if (diff < 3600) return Math.floor(diff/60) + 'm ago';
    return Math.floor(diff/3600) + 'h ago';
  },
};

// ----- toast --------------------------------------------------------------
function toast(msg, ok = true) {
  const el = document.createElement('div');
  el.className = 'toast ' + (ok ? 'toast-ok' : 'toast-err');
  el.textContent = msg;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 2800);
}

// ----- chart --------------------------------------------------------------
const chartWrap = document.getElementById('chart');
const chart = LightweightCharts.createChart(chartWrap, {
  layout: { background: { color: '#11151f' }, textColor: '#94a3b8' },
  grid: { vertLines: { color: '#1f2937' }, horzLines: { color: '#1f2937' } },
  timeScale: { borderColor: '#1f2937', timeVisible: true, secondsVisible: false },
  rightPriceScale: { borderColor: '#1f2937' },
  crosshair: { mode: 0 },
});
const candleSeries = chart.addCandlestickSeries({
  upColor: '#34d399', downColor: '#fb7185',
  borderUpColor: '#34d399', borderDownColor: '#fb7185',
  wickUpColor: '#34d399', wickDownColor: '#fb7185',
});
const fastSeries = chart.addLineSeries({ color: '#34d399', lineWidth: 1.5, priceLineVisible: false });
const slowSeries = chart.addLineSeries({ color: '#fb7185', lineWidth: 1.5, priceLineVisible: false });
let entryPriceLine = null;

new ResizeObserver(() => chart.applyOptions({ width: chartWrap.clientWidth })).observe(chartWrap);
chart.applyOptions({ width: chartWrap.clientWidth });

const equityWrap = document.getElementById('equity-chart');
const equityChart = LightweightCharts.createChart(equityWrap, {
  layout: { background: { color: '#11151f' }, textColor: '#94a3b8' },
  grid: { vertLines: { visible: false }, horzLines: { color: '#1f2937' } },
  timeScale: { borderColor: '#1f2937', timeVisible: true, secondsVisible: false },
  rightPriceScale: { borderColor: '#1f2937' },
});
const equitySeries = equityChart.addAreaSeries({
  lineColor: '#60a5fa', topColor: 'rgba(96,165,250,0.4)', bottomColor: 'rgba(96,165,250,0.0)',
});
new ResizeObserver(() => equityChart.applyOptions({ width: equityWrap.clientWidth })).observe(equityWrap);
equityChart.applyOptions({ width: equityWrap.clientWidth });

// ----- loaders ------------------------------------------------------------
// chart selector state, persisted in localStorage
let chartSymbol = localStorage.getItem('chart_symbol') || null;
let chartTimeframe = localStorage.getItem('chart_timeframe') || null;
let botSymbol = null;
let botTimeframe = null;

async function loadCandles() {
  try {
    const sym = chartSymbol || botSymbol;
    const tf = chartTimeframe || botTimeframe;
    if (!sym || !tf) return;
    const q = `symbol=${encodeURIComponent(sym)}&timeframe=${encodeURIComponent(tf)}&limit=200`;
    const [c, ind] = await Promise.all([
      fetch('/api/candles?' + q).then(r => r.json()),
      fetch('/api/indicators?' + q).then(r => r.json()),
    ]);
    candleSeries.setData(c);
    fastSeries.setData(ind.sma_fast || []);
    slowSeries.setData(ind.sma_slow || []);
  } catch (e) { /* ignore */ }
}

function syncChartSelectors() {
  document.getElementById('chart-symbol-pick').value = chartSymbol || botSymbol || '';
  document.getElementById('chart-tf-pick').value = chartTimeframe || botTimeframe || '1h';
  const notice = document.getElementById('chart-bot-notice');
  const differs = (chartSymbol && chartSymbol !== botSymbol) || (chartTimeframe && chartTimeframe !== botTimeframe);
  if (differs) {
    notice.classList.remove('hidden');
    document.getElementById('chart-bot-info').textContent = `${botSymbol} ${botTimeframe}`;
  } else {
    notice.classList.add('hidden');
  }
}

async function loadStatus() {
  try {
    const s = await fetch('/api/status').then(r => r.json());

    // header
    document.getElementById('header-sub').textContent =
      `${s.symbol} · ${s.timeframe} · strategy: ${s.strategy}`;

    // bot state badge
    const stateBadge = document.getElementById('bot-state-badge');
    if (s.bot.running) {
      if (s.bot.paused) {
        stateBadge.textContent = 'PAUSED';
        stateBadge.className = 'badge badge-paused';
      } else {
        stateBadge.textContent = 'RUNNING';
        stateBadge.className = 'badge badge-running';
      }
    } else {
      stateBadge.textContent = 'STOPPED';
      stateBadge.className = 'badge badge-stopped';
    }
    document.getElementById('bot-uptime').textContent = s.bot.running ? fmt.duration(s.bot.running_for_seconds) : '—';

    document.getElementById('btn-start').disabled = s.bot.running;
    document.getElementById('btn-stop').disabled = !s.bot.running;
    document.getElementById('btn-pause').disabled = !s.bot.running;
    document.getElementById('btn-pause').textContent = s.bot.paused ? 'Resume' : 'Pause';
    document.getElementById('btn-force-close').disabled = !s.position;

    // stat cards
    document.getElementById('stat-balance').textContent = fmt.usdt(s.balance);
    document.getElementById('stat-balance-source').textContent =
      s.balance_source === 'exchange' ? `live from ${s.mode} account` : 'paper book';
    document.getElementById('stat-price').textContent = fmt.num(s.current_price, 2);
    document.getElementById('stat-symbol').textContent = s.symbol;

    if (s.position) {
      const sideBadge = s.position.side === 'long' ? 'badge-long' : 'badge-short';
      document.getElementById('stat-position').innerHTML =
        `<span class="badge ${sideBadge}">${s.position.side.toUpperCase()}</span>`;
      document.getElementById('stat-position-detail').textContent =
        `${Number(s.position.amount).toFixed(6)} @ ${fmt.num(s.position.entry_price, 2)}`;
      const pnl = s.unrealized_pnl ?? 0;
      const pnlEl = document.getElementById('stat-pnl');
      pnlEl.textContent = (pnl >= 0 ? '+' : '') + fmt.num(pnl, 2) + ' USDT';
      pnlEl.className = 'stat-value ' + (pnl >= 0 ? 'green' : 'red');
      document.getElementById('stat-pnl-pct').textContent = fmt.pct(s.unrealized_pnl_pct);
      // draw entry line
      if (entryPriceLine) candleSeries.removePriceLine(entryPriceLine);
      entryPriceLine = candleSeries.createPriceLine({
        price: s.position.entry_price, color: '#fbbf24', lineStyle: 2, lineWidth: 1.5, title: 'entry',
      });
    } else {
      document.getElementById('stat-position').innerHTML = '<span class="badge badge-flat">FLAT</span>';
      document.getElementById('stat-position-detail').textContent = 'no open position';
      document.getElementById('stat-pnl').textContent = '—';
      document.getElementById('stat-pnl').className = 'stat-value muted';
      document.getElementById('stat-pnl-pct').textContent = '—';
      if (entryPriceLine) { candleSeries.removePriceLine(entryPriceLine); entryPriceLine = null; }
    }

    // signal card
    if (s.bot.last_signal) {
      const sigBadge = s.bot.last_signal === 'long' ? 'badge-long'
                       : s.bot.last_signal === 'short' ? 'badge-short' : 'badge-flat';
      document.getElementById('stat-signal').innerHTML =
        `<span class="badge ${sigBadge}">${(s.bot.last_signal || '—').toUpperCase()}</span>`;
      document.getElementById('stat-signal-when').textContent =
        (s.bot.last_reason || '') + ' · ' + fmt.ago(s.bot.last_tick_at);
    }

    // chart titles
    botSymbol = s.symbol;
    botTimeframe = s.timeframe;
    document.getElementById('chart-title').textContent = chartSymbol || s.symbol;
    document.getElementById('chart-sub').textContent =
      `${s.strategy} ${JSON.stringify(s.strategy_params)}  ·  risk ${s.risk_pct}%  ·  SL ${s.stop_loss_pct||'off'}%  ·  TP ${s.take_profit_pct||'off'}%`;
    syncChartSelectors();

    // last tick panel
    document.getElementById('ticker-signal').textContent = s.bot.last_signal || '—';
    document.getElementById('ticker-reason').textContent = s.bot.last_reason || '—';
    document.getElementById('ticker-price').textContent = fmt.num(s.bot.last_price, 2);
    document.getElementById('ticker-when').textContent = fmt.ago(s.bot.last_tick_at);

    // connection card
    const modeBadge = document.getElementById('conn-mode');
    modeBadge.innerHTML = `<span class="badge badge-mode-${s.mode}">${s.mode}</span>`;
    document.getElementById('conn-paptrading').textContent = s.mode === 'demo' ? 'set' : 'n/a';
    document.getElementById('conn-auth').textContent = s.api_auth_ok ? 'ok' : (s.mode === 'paper' ? 'not needed' : 'check');
    document.getElementById('conn-tg').textContent = s.telegram_enabled ? 'connected' : 'disabled';

    // populate config forms once
    if (!window._initForms) {
      // strategy options
      const stratSel = document.getElementById('form-strategy-name');
      s.available_strategies.forEach(x => {
        const opt = document.createElement('option');
        opt.value = x; opt.textContent = x;
        stratSel.appendChild(opt);
      });
      stratSel.value = s.strategy;
      stratSel.addEventListener('change', toggleStrategyParams);

      // mode options
      const modeSel = document.getElementById('form-mode-select');
      s.available_modes.forEach(x => {
        const opt = document.createElement('option');
        opt.value = x; opt.textContent = x;
        modeSel.appendChild(opt);
      });
      modeSel.value = s.mode;

      // fill all values
      // SYMBOL is a select populated by loadSymbols() — wait until populated to set value
      const trySetSymbol = () => {
        const sel = document.querySelector('select[name="SYMBOL"]');
        if (sel && sel.options.length > 0) {
          if ([...sel.options].some(o => o.value === s.symbol)) {
            sel.value = s.symbol;
          } else {
            // not in list (custom one?) — add it
            const opt = document.createElement('option');
            opt.value = s.symbol; opt.textContent = s.symbol;
            sel.insertBefore(opt, sel.firstChild);
            sel.value = s.symbol;
          }
        } else {
          setTimeout(trySetSymbol, 200);
        }
      };
      trySetSymbol();
      document.querySelector('select[name="TIMEFRAME"]').value = s.timeframe;
      document.querySelector('input[name="SMA_FAST"]').value = s.sma_fast;
      document.querySelector('input[name="SMA_SLOW"]').value = s.sma_slow;
      document.querySelector('input[name="BB_PERIOD"]').value = s.bb_period;
      document.querySelector('input[name="BB_STD"]').value = s.bb_std;
      document.querySelector('input[name="RSI_PERIOD"]').value = s.rsi_period;
      document.querySelector('input[name="RSI_OVERSOLD"]').value = s.rsi_oversold;
      document.querySelector('input[name="RSI_OVERBOUGHT"]').value = s.rsi_overbought;
      document.querySelector('input[name="RISK_PCT"]').value = s.risk_pct;
      document.querySelector('input[name="STOP_LOSS_PCT"]').value = s.stop_loss_pct;
      document.querySelector('input[name="TAKE_PROFIT_PCT"]').value = s.take_profit_pct;
      document.querySelector('input[name="PAPER_BALANCE"]').value = s.paper_balance;

      toggleStrategyParams();
      window._initForms = true;
    }
  } catch (e) { /* ignore */ }
}

function toggleStrategyParams() {
  const name = document.getElementById('form-strategy-name').value;
  document.querySelectorAll('.strategy-params').forEach(el => el.classList.add('hidden'));
  const target = document.getElementById('strategy-params-' + (name === 'sma_crossover' ? 'sma' : name === 'bollinger' ? 'bollinger' : 'rsi'));
  if (target) target.classList.remove('hidden');
}

async function loadTrades() {
  try {
    const trades = await fetch('/api/trades').then(r => r.json());
    const body = document.getElementById('trades-body');
    if (!trades.length) {
      body.innerHTML = '<div class="text-center text-slate-500 text-sm py-6">no trades yet</div>';
      return;
    }
    body.innerHTML = trades.map(t => {
      const sideBadge = t.side === 'long' ? 'badge-long' : 'badge-short';
      const pnlClass = t.pnl >= 0 ? 'text-emerald-400' : 'text-rose-400';
      return `
        <div class="trade-row">
          <span class="badge ${sideBadge}">${t.side.slice(0,1).toUpperCase()}</span>
          <span>${fmt.num(t.entry_price, 2)}</span>
          <span>${fmt.num(t.exit_price, 2)}</span>
          <span class="${pnlClass}">${(t.pnl>=0?'+':'') + fmt.num(t.pnl, 2)}</span>
          <span class="text-right text-slate-500 text-xs">${t.reason || '—'}</span>
        </div>`;
    }).join('');
  } catch (e) { /* ignore */ }
}

async function loadEquity() {
  try {
    const data = await fetch('/api/equity').then(r => r.json());
    if (!data.length) {
      equitySeries.setData([]);
      return;
    }
    equitySeries.setData(data);
  } catch (e) { /* ignore */ }
}

async function loadLogs() {
  try {
    const r = await fetch('/api/logs');
    const j = await r.json();
    const body = document.getElementById('logs-body');
    if (!j.lines.length) {
      body.innerHTML = '<div class="text-center text-slate-500 text-sm py-6">no output yet — Start the bot</div>';
      return;
    }
    body.innerHTML = j.lines.slice(-150).reverse().map(l => `<div class="log-line">${escapeHtml(l)}</div>`).join('');
  } catch (e) { /* ignore */ }
}

function escapeHtml(s) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// ----- control actions ----------------------------------------------------
async function post(path, body) {
  const r = await fetch(path, {
    method: 'POST',
    headers: body ? { 'Content-Type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : null,
  });
  let j; try { j = await r.json(); } catch (e) { j = {}; }
  return { ok: r.ok, json: j };
}

document.getElementById('btn-start').addEventListener('click', async () => {
  const r = await post('/api/bot/start');
  if (r.ok) toast('Bot started'); else toast(r.json.message || 'error', false);
  loadStatus();
});
document.getElementById('btn-stop').addEventListener('click', async () => {
  const r = await post('/api/bot/stop');
  if (r.ok) toast('Bot stopped'); else toast(r.json.message || 'error', false);
  loadStatus();
});
document.getElementById('btn-pause').addEventListener('click', async () => {
  const isPaused = document.getElementById('btn-pause').textContent === 'Resume';
  const r = await post(isPaused ? '/api/bot/resume' : '/api/bot/pause');
  if (r.ok) toast(isPaused ? 'Resumed' : 'Paused'); else toast('error', false);
  loadStatus();
});
document.getElementById('btn-restart').addEventListener('click', async () => {
  const r = await post('/api/bot/restart');
  if (r.ok) toast('Bot restarted'); else toast(r.json.message || 'error', false);
  loadStatus();
});
document.getElementById('btn-force-close').addEventListener('click', async () => {
  if (!confirm('Force close the current position? The bot will close it on the next tick.')) return;
  const r = await post('/api/position/close');
  if (r.ok) toast('Close requested'); else toast('error', false);
  loadStatus();
});
document.getElementById('btn-clear-trades').addEventListener('click', async () => {
  if (!confirm('Clear all recorded trades?')) return;
  // dirty client-side fallback: ask server to overwrite empty
  // (we don't have an endpoint for that — workaround: nothing; instruct user)
  toast('Delete trades.jsonl manually for now', false);
});

async function saveConfig(formId, fieldNames) {
  const form = document.getElementById(formId);
  const payload = {};
  fieldNames.forEach(n => {
    const el = form.querySelector(`[name="${n}"]`);
    if (el && el.value !== '') payload[n] = el.value;
  });
  const r = await post('/api/config', payload);
  if (r.ok) {
    toast('Saved' + (r.json.bot_restart_recommended ? ' — restart bot to apply' : ''));
    if (r.json.bot_restart_recommended) {
      if (confirm('Restart the bot now to apply the new settings?')) {
        await post('/api/bot/restart');
        toast('Restarted');
      }
    }
    loadStatus(); loadCandles();
  } else {
    toast(r.json.error || 'error', false);
  }
}

document.getElementById('form-strategy').addEventListener('submit', (e) => {
  e.preventDefault();
  saveConfig('form-strategy', ['STRATEGY','SYMBOL','TIMEFRAME','SMA_FAST','SMA_SLOW','BB_PERIOD','BB_STD','RSI_PERIOD','RSI_OVERSOLD','RSI_OVERBOUGHT']);
});
document.getElementById('form-risk').addEventListener('submit', (e) => {
  e.preventDefault();
  saveConfig('form-risk', ['RISK_PCT','STOP_LOSS_PCT','TAKE_PROFIT_PCT','PAPER_BALANCE']);
});
document.getElementById('form-mode').addEventListener('submit', (e) => {
  e.preventDefault();
  saveConfig('form-mode', ['MODE','CONFIRM_LIVE','TELEGRAM_BOT_TOKEN','TELEGRAM_CHAT_ID']);
});

async function loadSymbols() {
  try {
    const r = await fetch('/api/symbols');
    const data = await r.json();
    const symbols = Array.isArray(data) ? data : (data.fallback || []);
    // populate both selects: the strategy form one and the chart picker
    ['form-symbol', 'chart-symbol-pick'].forEach(id => {
      const sel = document.getElementById(id);
      if (!sel) return;
      sel.innerHTML = '';
      symbols.forEach(sym => {
        const o = document.createElement('option');
        o.value = sym; o.textContent = sym;
        sel.appendChild(o);
      });
    });
    const count = document.getElementById('symbol-count');
    if (count) count.textContent = `(${symbols.length} on Bitget)`;
    syncChartSelectors();
  } catch (e) {
    const count = document.getElementById('symbol-count');
    if (count) count.textContent = '(fetch failed)';
  }
}

document.getElementById('chart-symbol-pick').addEventListener('change', (e) => {
  chartSymbol = e.target.value;
  localStorage.setItem('chart_symbol', chartSymbol);
  syncChartSelectors();
  loadCandles();
});
document.getElementById('chart-tf-pick').addEventListener('change', (e) => {
  chartTimeframe = e.target.value;
  localStorage.setItem('chart_timeframe', chartTimeframe);
  syncChartSelectors();
  loadCandles();
});
document.getElementById('chart-reset-to-bot').addEventListener('click', () => {
  chartSymbol = null; chartTimeframe = null;
  localStorage.removeItem('chart_symbol');
  localStorage.removeItem('chart_timeframe');
  syncChartSelectors();
  loadCandles();
});

// ----- boot ---------------------------------------------------------------
loadSymbols();
loadStatus(); loadCandles(); loadTrades(); loadEquity(); loadLogs();
setInterval(loadStatus, 3000);
setInterval(loadCandles, 30000);
setInterval(loadTrades, 8000);
setInterval(loadEquity, 12000);
setInterval(loadLogs, 4000);
</script>
</body>
</html>
"""


def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    cfg = load_config()
    app = create_app()
    log.info("starting web UI on http://%s:%d", cfg.web_host, cfg.web_port)
    app.run(host=cfg.web_host, port=cfg.web_port, debug=False)


if __name__ == "__main__":
    main()
