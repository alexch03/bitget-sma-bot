from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, render_template_string, request

from .config import load_config


log = logging.getLogger(__name__)


REPO_ROOT = Path(__file__).resolve().parent.parent
RUNTIME_FILE = REPO_ROOT / "runtime.json"
STATE_FILE = REPO_ROOT / "state.json"
TRADES_FILE = REPO_ROOT / "trades.jsonl"


# ---------------------------------------------------------------------------
# state helpers


def _read_overrides() -> dict[str, Any]:
    if RUNTIME_FILE.exists():
        try:
            return json.loads(RUNTIME_FILE.read_text())
        except Exception:
            return {}
    return {}


def _write_overrides(data: dict[str, Any]) -> None:
    RUNTIME_FILE.write_text(json.dumps(data, indent=2))


def _read_state() -> dict[str, Any]:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            return {}
    return {}


def _read_trades(limit: int = 20) -> list[dict]:
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


# ---------------------------------------------------------------------------
# template


DASHBOARD_HTML = r"""<!doctype html>
<html lang="en" class="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>bitget-sma-bot</title>
<script src="https://cdn.tailwindcss.com"></script>
<script src="https://unpkg.com/lightweight-charts@4.2.2/dist/lightweight-charts.standalone.production.js"></script>
<style>
  :root { --bg:#0b0e14; --panel:#11151f; --border:#1f2937; --text:#e5e7eb; --muted:#94a3b8; }
  html, body { background: var(--bg); color: var(--text); }
  .panel { background: var(--panel); border: 1px solid var(--border); border-radius: 12px; }
  .badge { display:inline-flex; align-items:center; gap:.35rem; padding:.2rem .6rem; border-radius:9999px; font-size:.75rem; font-weight:600; }
  .badge-mode-paper { background:#1e293b; color:#cbd5e1; }
  .badge-mode-dry   { background:#3f3f46; color:#fbbf24; }
  .badge-mode-demo  { background:#0f3a2f; color:#34d399; }
  .badge-mode-live  { background:#3f1d1d; color:#fca5a5; }
  .badge-long  { background:#0a3a2a; color:#34d399; }
  .badge-short { background:#3a0a1f; color:#fb7185; }
  .badge-flat  { background:#1e293b; color:#94a3b8; }
  .pulse { width:.5rem; height:.5rem; border-radius:9999px; background:#34d399; box-shadow: 0 0 8px #34d399; animation: pulse 2s infinite; }
  @keyframes pulse { 0%{opacity:1} 50%{opacity:.4} 100%{opacity:1} }
  input, select { background:#0b0e14; border:1px solid var(--border); color:var(--text); border-radius:8px; padding:.5rem .75rem; width:100%; }
  input:focus, select:focus { outline: none; border-color:#3b82f6; }
  button.primary { background:#2563eb; color:#fff; padding:.55rem 1rem; border-radius:8px; font-weight:600; transition: all .15s; }
  button.primary:hover { background:#1d4ed8; }
  .stat-label { color: var(--muted); font-size:.75rem; text-transform: uppercase; letter-spacing:.05em; }
  .stat-value { font-size:1.5rem; font-weight:700; font-variant-numeric: tabular-nums; }
  .stat-value.green { color:#34d399; }
  .stat-value.red { color:#fb7185; }
  .stat-value.muted { color:#94a3b8; }
  .trade-row { display:grid; grid-template-columns: 50px 1fr 1fr 1fr 80px; gap:.5rem; padding:.5rem .75rem; border-bottom:1px solid #1f2937; font-size:.85rem; align-items:center; }
  .trade-row:last-child { border-bottom: none; }
  table.cfg { width:100%; font-size:.85rem; }
  table.cfg td { padding: .35rem .25rem; }
  table.cfg td:first-child { color: var(--muted); }
  table.cfg td:last-child { text-align: right; font-variant-numeric: tabular-nums; }
</style>
</head>
<body class="min-h-screen">

<header class="border-b border-slate-800 sticky top-0 z-10 backdrop-blur bg-slate-950/70">
  <div class="max-w-7xl mx-auto px-6 py-3 flex items-center justify-between">
    <div class="flex items-center gap-3">
      <svg width="28" height="28" viewBox="0 0 32 32" fill="none">
        <rect x="2" y="6" width="28" height="20" rx="4" fill="#2563eb"/>
        <path d="M6 19 L11 14 L15 17 L20 11 L26 14" stroke="#fff" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
        <circle cx="20" cy="11" r="1.6" fill="#fbbf24"/>
      </svg>
      <div>
        <div class="font-bold text-lg">bitget-sma-bot</div>
        <div class="text-xs text-slate-400" id="header-sub">loading...</div>
      </div>
    </div>
    <div class="flex items-center gap-2">
      <span class="pulse" id="pulse"></span>
      <span class="text-xs text-slate-400" id="last-update">—</span>
    </div>
  </div>
</header>

<main class="max-w-7xl mx-auto px-6 py-6 space-y-6">

  <!-- STATUS CARDS -->
  <section class="grid grid-cols-2 md:grid-cols-4 gap-4">
    <div class="panel p-4">
      <div class="stat-label">Balance</div>
      <div class="stat-value" id="stat-balance">—</div>
      <div class="text-xs text-slate-400 mt-1" id="stat-balance-source">—</div>
    </div>
    <div class="panel p-4">
      <div class="stat-label">Position</div>
      <div class="stat-value" id="stat-position">FLAT</div>
      <div class="text-xs text-slate-400 mt-1" id="stat-position-detail">no open position</div>
    </div>
    <div class="panel p-4">
      <div class="stat-label">Unrealized PnL</div>
      <div class="stat-value" id="stat-pnl">—</div>
      <div class="text-xs text-slate-400 mt-1" id="stat-pnl-pct">—</div>
    </div>
    <div class="panel p-4">
      <div class="stat-label">Last price</div>
      <div class="stat-value" id="stat-price">—</div>
      <div class="text-xs text-slate-400 mt-1" id="stat-symbol">—</div>
    </div>
  </section>

  <!-- CHART + SIDE PANEL -->
  <section class="grid grid-cols-1 lg:grid-cols-3 gap-6">
    <div class="panel p-4 lg:col-span-2">
      <div class="flex items-center justify-between mb-3">
        <div>
          <div class="text-sm font-semibold" id="chart-title">price chart</div>
          <div class="text-xs text-slate-400" id="chart-sub">—</div>
        </div>
        <div class="flex items-center gap-2 text-xs">
          <span class="text-slate-400">timeframe:</span>
          <span class="badge" id="chart-tf">—</span>
        </div>
      </div>
      <div id="chart" style="width:100%;height:380px;"></div>
    </div>

    <div class="panel p-4">
      <div class="text-sm font-semibold mb-3">configuration</div>
      <table class="cfg">
        <tr><td>strategy</td><td id="cfg-strategy">—</td></tr>
        <tr><td>symbol</td><td id="cfg-symbol">—</td></tr>
        <tr><td>timeframe</td><td id="cfg-timeframe">—</td></tr>
        <tr><td>risk per trade</td><td id="cfg-risk">—</td></tr>
        <tr><td>stop loss</td><td id="cfg-sl">—</td></tr>
        <tr><td>take profit</td><td id="cfg-tp">—</td></tr>
        <tr><td>telegram</td><td id="cfg-telegram">—</td></tr>
      </table>

      <div class="border-t border-slate-800 mt-4 pt-4">
        <div class="text-sm font-semibold mb-2">override</div>
        <p class="text-xs text-slate-400 mb-3">written to <code>runtime.json</code> and picked up on the next loop tick.</p>
        <form id="cfg-form" class="space-y-2">
          <div>
            <label class="text-xs text-slate-400">symbol</label>
            <input name="symbol" id="form-symbol" />
          </div>
          <div class="grid grid-cols-2 gap-2">
            <div>
              <label class="text-xs text-slate-400">timeframe</label>
              <select name="timeframe" id="form-timeframe">
                <option>1m</option><option>5m</option><option>15m</option>
                <option>1h</option><option>4h</option><option>1d</option>
              </select>
            </div>
            <div>
              <label class="text-xs text-slate-400">risk %</label>
              <input name="risk_pct" id="form-risk" type="number" step="0.1" min="0.1" max="100"/>
            </div>
          </div>
          <div class="grid grid-cols-2 gap-2">
            <div>
              <label class="text-xs text-slate-400">SMA fast</label>
              <input name="sma_fast" id="form-fast" type="number" min="2"/>
            </div>
            <div>
              <label class="text-xs text-slate-400">SMA slow</label>
              <input name="sma_slow" id="form-slow" type="number" min="3"/>
            </div>
          </div>
          <button type="submit" class="primary w-full mt-2">save override</button>
          <div id="form-msg" class="text-xs mt-2"></div>
        </form>
      </div>
    </div>
  </section>

  <!-- TRADES + ACTIVITY -->
  <section class="grid grid-cols-1 lg:grid-cols-2 gap-6">
    <div class="panel p-4">
      <div class="text-sm font-semibold mb-3">recent trades</div>
      <div id="trades-header" class="trade-row text-xs text-slate-400 border-b border-slate-800">
        <span>side</span><span>entry</span><span>exit</span><span>pnl</span><span class="text-right">reason</span>
      </div>
      <div id="trades-body">
        <div class="text-center text-slate-500 text-sm py-8" id="trades-empty">no trades recorded yet</div>
      </div>
    </div>

    <div class="panel p-4">
      <div class="text-sm font-semibold mb-3">demo connection</div>
      <div class="space-y-3 text-sm">
        <div class="flex items-center justify-between">
          <span class="text-slate-400">mode</span>
          <span id="conn-mode" class="badge">—</span>
        </div>
        <div class="flex items-center justify-between">
          <span class="text-slate-400">paptrading header</span>
          <span id="conn-paptrading" class="text-slate-300">—</span>
        </div>
        <div class="flex items-center justify-between">
          <span class="text-slate-400">api auth</span>
          <span id="conn-auth" class="text-slate-300">—</span>
        </div>
        <div class="flex items-center justify-between">
          <span class="text-slate-400">last fetch</span>
          <span id="conn-fetch" class="text-slate-300">—</span>
        </div>
      </div>
      <div class="border-t border-slate-800 mt-4 pt-4 text-xs text-slate-400 leading-relaxed">
        in <code class="bg-slate-800 px-1 rounded">paper</code> mode the bot simulates trades locally.<br>
        in <code class="bg-slate-800 px-1 rounded">demo</code> mode it places real orders on bitget's demo account using virtual money — the <code class="bg-slate-800 px-1 rounded">paptrading: 1</code> header is set.<br>
        in <code class="bg-slate-800 px-1 rounded">live</code> mode it places real orders on a real account.
      </div>
    </div>
  </section>

  <footer class="text-center text-xs text-slate-500 pt-4 pb-8">
    bitget-sma-bot · <a href="https://github.com/alexch03/bitget-sma-bot" class="underline hover:text-slate-300">github</a> · educational use only
  </footer>
</main>

<script>
const fmt = {
  usdt: (n) => (n == null) ? '—' : n.toLocaleString(undefined, {minimumFractionDigits:2, maximumFractionDigits:2}) + ' USDT',
  pct: (n) => (n == null) ? '—' : (n>=0?'+':'') + n.toFixed(2) + '%',
  num: (n, d=2) => (n == null) ? '—' : n.toLocaleString(undefined, {minimumFractionDigits:d, maximumFractionDigits:d}),
  time: (ts) => ts ? new Date(ts*1000).toLocaleTimeString() : '—',
};

const chart = LightweightCharts.createChart(document.getElementById('chart'), {
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
window.addEventListener('resize', () => chart.applyOptions({ width: document.getElementById('chart').clientWidth }));
chart.applyOptions({ width: document.getElementById('chart').clientWidth });

async function loadCandles() {
  try {
    const r = await fetch('/api/candles?limit=200');
    if (!r.ok) return;
    const data = await r.json();
    candleSeries.setData(data);
  } catch (e) { /* ignore */ }
}

async function loadStatus() {
  try {
    const r = await fetch('/api/status');
    const s = await r.json();

    // header
    document.getElementById('header-sub').textContent =
      `${s.symbol} · ${s.timeframe} · strategy: ${s.strategy}`;

    // status cards
    document.getElementById('stat-balance').textContent = fmt.usdt(s.balance);
    document.getElementById('stat-balance-source').textContent =
      s.balance_source === 'exchange' ? `live from ${s.mode} account` : 'paper book';
    document.getElementById('stat-price').textContent = fmt.num(s.current_price, 2);
    document.getElementById('stat-symbol').textContent = s.symbol;

    const pos = s.position;
    if (pos) {
      const sideBadge = pos.side === 'long' ? 'badge-long' : 'badge-short';
      document.getElementById('stat-position').innerHTML =
        `<span class="badge ${sideBadge}">${pos.side.toUpperCase()}</span>`;
      document.getElementById('stat-position-detail').textContent =
        `${pos.amount.toFixed(6)} @ ${fmt.num(pos.entry_price, 2)}`;

      const pnl = s.unrealized_pnl ?? 0;
      const pnlEl = document.getElementById('stat-pnl');
      pnlEl.textContent = (pnl >= 0 ? '+' : '') + fmt.num(pnl, 2) + ' USDT';
      pnlEl.className = 'stat-value ' + (pnl >= 0 ? 'green' : 'red');
      document.getElementById('stat-pnl-pct').textContent = fmt.pct(s.unrealized_pnl_pct);
    } else {
      document.getElementById('stat-position').innerHTML = '<span class="badge badge-flat">FLAT</span>';
      document.getElementById('stat-position-detail').textContent = 'no open position';
      document.getElementById('stat-pnl').textContent = '—';
      document.getElementById('stat-pnl').className = 'stat-value muted';
      document.getElementById('stat-pnl-pct').textContent = '—';
    }

    // config panel
    document.getElementById('cfg-strategy').textContent = s.strategy;
    document.getElementById('cfg-symbol').textContent = s.symbol;
    document.getElementById('cfg-timeframe').textContent = s.timeframe;
    document.getElementById('cfg-risk').textContent = s.risk_pct + '%';
    document.getElementById('cfg-sl').textContent = s.stop_loss_pct > 0 ? s.stop_loss_pct + '%' : 'disabled';
    document.getElementById('cfg-tp').textContent = s.take_profit_pct > 0 ? s.take_profit_pct + '%' : 'disabled';
    document.getElementById('cfg-telegram').textContent = s.telegram_enabled ? 'connected' : 'disabled';

    // chart title
    document.getElementById('chart-title').textContent = s.symbol;
    document.getElementById('chart-sub').textContent = `${s.strategy} ${JSON.stringify(s.strategy_params)}`;
    const tfBadge = document.getElementById('chart-tf');
    tfBadge.textContent = s.timeframe;
    tfBadge.className = 'badge badge-flat';

    // connection card
    const modeBadge = document.getElementById('conn-mode');
    modeBadge.textContent = s.mode;
    modeBadge.className = 'badge badge-mode-' + s.mode;
    document.getElementById('conn-paptrading').textContent = s.mode === 'demo' ? 'set (= 1)' : 'n/a';
    document.getElementById('conn-auth').textContent = s.api_auth_ok ? 'ok' : (s.mode === 'paper' ? 'not needed' : 'unchecked');
    document.getElementById('conn-fetch').textContent = fmt.time(s.fetched_at);

    document.getElementById('last-update').textContent = 'updated ' + new Date().toLocaleTimeString();

    // populate form on first load
    if (!window._formInitialised) {
      document.getElementById('form-symbol').value = s.symbol;
      document.getElementById('form-timeframe').value = s.timeframe;
      document.getElementById('form-risk').value = s.risk_pct;
      document.getElementById('form-fast').value = s.strategy_params.fast ?? 20;
      document.getElementById('form-slow').value = s.strategy_params.slow ?? 50;
      window._formInitialised = true;
    }
  } catch (e) {
    document.getElementById('last-update').textContent = 'error: ' + e.message;
  }
}

async function loadTrades() {
  try {
    const r = await fetch('/api/trades');
    const trades = await r.json();
    const body = document.getElementById('trades-body');
    const empty = document.getElementById('trades-empty');
    if (!trades.length) {
      body.innerHTML = '<div class="text-center text-slate-500 text-sm py-8">no trades recorded yet</div>';
      return;
    }
    body.innerHTML = trades.map(t => {
      const sideBadge = t.side === 'long' ? 'badge-long' : 'badge-short';
      const pnlClass = t.pnl >= 0 ? 'text-green-400' : 'text-rose-400';
      return `
        <div class="trade-row">
          <span class="badge ${sideBadge}">${t.side.slice(0,1).toUpperCase()}</span>
          <span>${fmt.num(t.entry_price, 2)}</span>
          <span>${fmt.num(t.exit_price, 2)}</span>
          <span class="${pnlClass}">${(t.pnl>=0?'+':'') + fmt.num(t.pnl, 2)}</span>
          <span class="text-right text-slate-400 text-xs">${t.reason || '—'}</span>
        </div>`;
    }).join('');
  } catch (e) { /* ignore */ }
}

document.getElementById('cfg-form').addEventListener('submit', async (ev) => {
  ev.preventDefault();
  const form = ev.target;
  const data = new FormData(form);
  const body = new URLSearchParams();
  for (const [k, v] of data.entries()) body.append(k, v);
  const r = await fetch('/', { method: 'POST', body });
  const msg = document.getElementById('form-msg');
  if (r.ok) {
    msg.textContent = 'saved.';
    msg.className = 'text-xs mt-2 text-green-400';
    setTimeout(() => { msg.textContent = ''; }, 2000);
  } else {
    msg.textContent = 'error saving';
    msg.className = 'text-xs mt-2 text-rose-400';
  }
});

loadStatus();
loadCandles();
loadTrades();
setInterval(loadStatus, 5000);
setInterval(loadCandles, 30000);
setInterval(loadTrades, 10000);
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# app


def create_app():
    cfg = load_config()
    app = Flask(__name__)

    # Cached exchange/ticker to avoid hammering Bitget on each poll.
    cache: dict[str, Any] = {"ts": 0, "balance": None, "price": None, "candles": None, "auth_ok": None}

    def _ensure_exchange():
        from .exchange import build_exchange
        if "exchange" not in cache:
            cache["exchange"] = build_exchange(cfg)
        return cache["exchange"]

    def _fresh_ticker_and_balance(force: bool = False) -> tuple[float | None, float | None, bool | None]:
        now = time.time()
        if not force and now - cache["ts"] < 5 and cache["price"] is not None:
            return cache["price"], cache["balance"], cache["auth_ok"]
        try:
            ex = _ensure_exchange()
            cache["price"] = ex.fetch_ticker_price(cfg.symbol)
        except Exception as exc:
            log.debug("ticker fetch failed: %s", exc)
            cache["price"] = None
        if cfg.mode == "paper":
            cache["balance"] = None
            cache["auth_ok"] = None
        else:
            try:
                ex = _ensure_exchange()
                cache["balance"] = ex.fetch_balance_usdt()
                cache["auth_ok"] = True
            except Exception as exc:
                log.debug("balance fetch failed: %s", exc)
                cache["balance"] = None
                cache["auth_ok"] = False
        cache["ts"] = now
        return cache["price"], cache["balance"], cache["auth_ok"]

    def _fresh_candles(limit: int = 200) -> list[dict]:
        now = time.time()
        if cache.get("candles_ts") and now - cache["candles_ts"] < 25 and cache.get("candles"):
            return cache["candles"]
        try:
            ex = _ensure_exchange()
            df = ex.fetch_ohlcv(cfg.symbol, cfg.timeframe, limit=limit)
            arr = []
            for ts, row in df.iterrows():
                arr.append({
                    "time": int(ts.timestamp()),
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                })
            cache["candles"] = arr
            cache["candles_ts"] = now
            return arr
        except Exception as exc:
            log.warning("candles fetch failed: %s", exc)
            return cache.get("candles") or []

    @app.route("/", methods=["GET", "POST"])
    def index():
        if request.method == "POST":
            try:
                overrides = {
                    "symbol": request.form.get("symbol", cfg.symbol).strip(),
                    "timeframe": request.form.get("timeframe", cfg.timeframe).strip(),
                    "sma_fast": int(request.form.get("sma_fast", cfg.sma_fast)),
                    "sma_slow": int(request.form.get("sma_slow", cfg.sma_slow)),
                    "risk_pct": float(request.form.get("risk_pct", cfg.risk_pct)),
                }
                if overrides["sma_fast"] >= overrides["sma_slow"]:
                    return jsonify({"error": "SMA fast must be smaller than SMA slow"}), 400
                _write_overrides(overrides)
            except (TypeError, ValueError) as exc:
                return jsonify({"error": str(exc)}), 400
        return render_template_string(DASHBOARD_HTML)

    @app.route("/api/status", methods=["GET"])
    def api_status():
        overrides = _read_overrides()
        state = _read_state()

        price, balance, auth_ok = _fresh_ticker_and_balance()

        pos = state.get("position")
        position_obj = None
        unrealized_pnl = None
        unrealized_pnl_pct = None
        if pos and price is not None:
            direction = 1 if pos["side"] == "long" else -1
            unrealized_pnl = direction * (price - pos["entry_price"]) * pos["amount"]
            unrealized_pnl_pct = direction * (price - pos["entry_price"]) / pos["entry_price"] * 100
            position_obj = {
                "side": pos["side"],
                "amount": pos["amount"],
                "entry_price": pos["entry_price"],
                "opened_at": pos.get("opened_at"),
            }
        elif pos:
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

        return jsonify({
            "mode": cfg.mode,
            "symbol": overrides.get("symbol", cfg.symbol),
            "timeframe": overrides.get("timeframe", cfg.timeframe),
            "strategy": cfg.strategy,
            "strategy_params": cfg.strategy_params(),
            "risk_pct": overrides.get("risk_pct", cfg.risk_pct),
            "stop_loss_pct": cfg.stop_loss_pct,
            "take_profit_pct": cfg.take_profit_pct,
            "current_price": price,
            "balance": balance_val,
            "balance_source": balance_source,
            "position": position_obj,
            "unrealized_pnl": unrealized_pnl,
            "unrealized_pnl_pct": unrealized_pnl_pct,
            "telegram_enabled": cfg.telegram_enabled,
            "api_auth_ok": auth_ok,
            "fetched_at": int(cache["ts"]),
            "overrides": overrides,
        })

    @app.route("/api/candles", methods=["GET"])
    def api_candles():
        limit = int(request.args.get("limit", 200))
        return jsonify(_fresh_candles(limit))

    @app.route("/api/trades", methods=["GET"])
    def api_trades():
        return jsonify(_read_trades(limit=30))

    @app.route("/api/config", methods=["GET"])
    def api_config():
        # back-compat with the previous JSON shape
        return jsonify({
            "symbol": cfg.symbol,
            "timeframe": cfg.timeframe,
            "sma_fast": cfg.sma_fast,
            "sma_slow": cfg.sma_slow,
            "risk_pct": cfg.risk_pct,
            "mode": cfg.mode,
            "overrides": _read_overrides(),
        })

    return app


def main():
    cfg = load_config()
    app = create_app()
    log.info("starting web UI on http://%s:%d", cfg.web_host, cfg.web_port)
    app.run(host=cfg.web_host, port=cfg.web_port, debug=False)


if __name__ == "__main__":
    main()
