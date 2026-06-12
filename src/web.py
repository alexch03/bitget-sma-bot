from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, render_template_string, request

from .config import load_config


log = logging.getLogger(__name__)


PAGE = """
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>bitget-sma-bot</title>
<style>
  body { font-family: system-ui, sans-serif; max-width: 720px; margin: 2rem auto; padding: 0 1rem; }
  h1 { margin-bottom: 0.25rem; }
  .muted { color: #888; font-size: 0.9rem; }
  label { display: block; margin-top: 1rem; font-weight: 600; }
  input, select { width: 100%; padding: 0.4rem; font-size: 1rem; }
  button { margin-top: 1.5rem; padding: 0.6rem 1.2rem; font-size: 1rem; cursor: pointer; }
  .ok { color: #0a7d2c; }
  .warn { color: #b8860b; }
  pre { background: #f4f4f4; padding: 0.8rem; overflow-x: auto; }
</style>
</head>
<body>
<h1>bitget-sma-bot</h1>
<p class="muted">Runtime configuration. Changes are written to <code>runtime.json</code> and picked up on the next loop tick.</p>

<form method="POST">
  <label>Symbol
    <input name="symbol" value="{{ cfg.symbol }}">
  </label>
  <label>Timeframe
    <select name="timeframe">
      {% for tf in ["1m","5m","15m","1h","4h","1d"] %}
      <option value="{{ tf }}" {% if tf == cfg.timeframe %}selected{% endif %}>{{ tf }}</option>
      {% endfor %}
    </select>
  </label>
  <label>SMA fast
    <input name="sma_fast" type="number" min="2" max="200" value="{{ cfg.sma_fast }}">
  </label>
  <label>SMA slow
    <input name="sma_slow" type="number" min="3" max="500" value="{{ cfg.sma_slow }}">
  </label>
  <label>Risk per trade (%)
    <input name="risk_pct" type="number" step="0.1" min="0.1" max="100" value="{{ cfg.risk_pct }}">
  </label>
  <button type="submit">Save</button>
</form>

<p class="muted">Mode: <strong>{{ cfg.mode }}</strong> — to change the mode, edit <code>.env</code> and restart.</p>

{% if message %}
<p class="ok">{{ message }}</p>
{% endif %}

<h2>Current overrides</h2>
<pre>{{ overrides_json }}</pre>
</body>
</html>
"""


RUNTIME_FILE = Path(__file__).resolve().parent.parent / "runtime.json"


def _read_overrides() -> dict[str, Any]:
    if RUNTIME_FILE.exists():
        try:
            return json.loads(RUNTIME_FILE.read_text())
        except Exception:
            return {}
    return {}


def _write_overrides(data: dict[str, Any]) -> None:
    RUNTIME_FILE.write_text(json.dumps(data, indent=2))


def create_app():
    cfg = load_config()
    app = Flask(__name__)

    @app.route("/", methods=["GET", "POST"])
    def index():
        message = ""
        if request.method == "POST":
            overrides = {
                "symbol": request.form.get("symbol", cfg.symbol).strip(),
                "timeframe": request.form.get("timeframe", cfg.timeframe).strip(),
                "sma_fast": int(request.form.get("sma_fast", cfg.sma_fast)),
                "sma_slow": int(request.form.get("sma_slow", cfg.sma_slow)),
                "risk_pct": float(request.form.get("risk_pct", cfg.risk_pct)),
            }
            if overrides["sma_fast"] >= overrides["sma_slow"]:
                message = "ERROR: SMA fast must be smaller than SMA slow. Not saved."
            else:
                _write_overrides(overrides)
                message = "Saved."

        overrides = _read_overrides()
        return render_template_string(
            PAGE,
            cfg=cfg,
            overrides_json=json.dumps(overrides, indent=2) if overrides else "(none)",
            message=message,
        )

    @app.route("/api/config", methods=["GET"])
    def api_config():
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
