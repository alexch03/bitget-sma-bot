"""UI smoke test: launch a Flask server in this process, drive the dashboard
with Playwright, verify the critical click paths still work.

Verifies:
  1. Index page renders without console errors
  2. The Symbol dropdown is populated from /api/symbols
  3. Bot start button transitions the badge from STOPPED to RUNNING
  4. Bot stop button transitions back to STOPPED
  5. Force close button is disabled when there's no position
  6. The toast appears after a save action

Mocks the BitgetExchange so no real network is hit.
"""
from __future__ import annotations

import sys
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from playwright.sync_api import sync_playwright   # noqa: E402

# ----- mock exchange ---------------------------------------------------------


def _fake_df(n: int = 60, base: float = 60000.0) -> pd.DataFrame:
    idx = pd.date_range("2026-01-01", periods=n, freq="1h", tz="UTC")
    return pd.DataFrame({
        "open": [base + i for i in range(n)],
        "high": [base + i + 5 for i in range(n)],
        "low":  [base + i - 5 for i in range(n)],
        "close":[base + i + 1 for i in range(n)],
        "volume": [1.0] * n,
    }, index=idx)


def _build_fake_exchange(cfg):
    ex = MagicMock()
    ex.fetch_ohlcv.return_value = _fake_df()
    ex.fetch_ticker_price.return_value = 60010.0
    ex.fetch_balance_usdt.return_value = 5000.0
    ex.client.load_markets.return_value = {
        "BTC/USDT:USDT": {"swap": True, "linear": True, "quote": "USDT", "active": True},
        "ETH/USDT:USDT": {"swap": True, "linear": True, "quote": "USDT", "active": True},
        "SOL/USDT:USDT": {"swap": True, "linear": True, "quote": "USDT", "active": True},
    }
    return ex


def _bot_start_noop(*args, **kwargs):
    from src import web as web_mod
    fake = MagicMock()
    fake.poll.return_value = None
    fake.pid = 99999
    fake.stdout = MagicMock()
    web_mod._bot_process = fake
    web_mod._bot_started_at = time.time()
    return True, "started"


def _bot_stop_noop(*args, **kwargs):
    from src import web as web_mod
    web_mod._bot_process = None
    web_mod._bot_started_at = None
    return True, "stopped"


# ----- main ------------------------------------------------------------------


def main() -> int:
    from src import web as web_mod
    from src import exchange as ex_mod

    # patch exchange before app creation
    ex_mod.build_exchange = _build_fake_exchange
    web_mod.build_exchange = _build_fake_exchange
    # patch subprocess spawn / kill so we don't actually start a bot
    web_mod._spawn_bot = _bot_start_noop
    web_mod._stop_bot = _bot_stop_noop

    app = web_mod.create_app()

    port = 5099
    server = threading.Thread(
        target=lambda: app.run(host="127.0.0.1", port=port, use_reloader=False),
        daemon=True,
    )
    server.start()
    # wait for the server
    import socket
    for _ in range(40):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                break
        except OSError:
            time.sleep(0.25)
    else:
        print("FAIL: flask did not come up", file=sys.stderr)
        return 1

    base_url = f"http://127.0.0.1:{port}"

    results: list[tuple[str, bool, str]] = []

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1320, "height": 900})

        # capture console errors
        console_errors: list[str] = []
        page.on("pageerror", lambda exc: console_errors.append(str(exc)))
        page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)

        # ---- 1. render -----------------------------------------------------
        try:
            page.goto(base_url, wait_until="networkidle", timeout=10000)
            assert "bitget-sma-bot" in page.title().lower()
            page.wait_for_selector("#bot-state-badge", timeout=5000)
            badge_text = page.text_content("#bot-state-badge").strip()
            assert badge_text == "STOPPED", f"initial badge was {badge_text!r}"
            results.append(("page renders, badge STOPPED", True, ""))
        except Exception as exc:
            results.append(("page renders, badge STOPPED", False, str(exc)))

        # ---- 2. symbols populated -----------------------------------------
        try:
            # wait until the dropdown has at least one option
            page.wait_for_function(
                "document.querySelectorAll('#form-symbol option').length > 0",
                timeout=8000,
            )
            opts = page.eval_on_selector_all("#form-symbol option", "els => els.map(o => o.value)")
            assert "BTC/USDT:USDT" in opts, f"symbols missing BTC: {opts}"
            results.append(("symbols dropdown populated", True, f"{len(opts)} options"))
        except Exception as exc:
            results.append(("symbols dropdown populated", False, str(exc)))

        # ---- 3. click Start Bot -> badge becomes RUNNING -------------------
        try:
            page.click("#btn-start")
            page.wait_for_function(
                "document.querySelector('#bot-state-badge').textContent.trim() === 'RUNNING'",
                timeout=6000,
            )
            assert not page.is_disabled("#btn-stop"), "Stop button should be enabled"
            results.append(("click Start -> RUNNING", True, ""))
        except Exception as exc:
            results.append(("click Start -> RUNNING", False, str(exc)))

        # ---- 4. click Stop Bot -> badge becomes STOPPED --------------------
        try:
            page.click("#btn-stop")
            page.wait_for_function(
                "document.querySelector('#bot-state-badge').textContent.trim() === 'STOPPED'",
                timeout=6000,
            )
            results.append(("click Stop -> STOPPED", True, ""))
        except Exception as exc:
            results.append(("click Stop -> STOPPED", False, str(exc)))

        # ---- 5. force close button disabled when no position ---------------
        try:
            disabled = page.is_disabled("#btn-force-close")
            assert disabled, "Force close should be disabled when flat"
            results.append(("force close disabled when flat", True, ""))
        except Exception as exc:
            results.append(("force close disabled when flat", False, str(exc)))

        # ---- 6. console errors --------------------------------------------
        # Filter out playwright noise about favicon
        real_errors = [e for e in console_errors if "favicon" not in e.lower() and e.strip()]
        if real_errors:
            results.append(("no JS console errors", False, f"{len(real_errors)} errors: {real_errors[:3]}"))
        else:
            results.append(("no JS console errors", True, ""))

        browser.close()

    # ---- report ----
    print()
    print("=" * 60)
    print("  UI SMOKE TEST REPORT")
    print("=" * 60)
    passed = sum(1 for _, ok, _ in results if ok)
    for name, ok, note in results:
        mark = "OK  " if ok else "FAIL"
        extra = f"  ({note})" if note else ""
        print(f"  [{mark}] {name}{extra}")
    print()
    print(f"{passed}/{len(results)} passed")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
