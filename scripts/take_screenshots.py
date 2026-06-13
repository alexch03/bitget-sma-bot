"""Take a screenshot of the local Flask UI for the README.

Usage:
    # 1. start the Flask UI in another terminal:
    #    python -m src.web
    # 2. then run:
    python scripts/take_screenshots.py
"""
from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright


OUTPUTS = [
    {
        "url": "http://127.0.0.1:5000/",
        "path": "docs/images/web-ui.png",
        "viewport": {"width": 1320, "height": 900},
    },
]


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for cfg in OUTPUTS:
            page = browser.new_page(viewport=cfg["viewport"])
            try:
                page.goto(cfg["url"], wait_until="networkidle", timeout=10000)
                # clear localStorage so the chart picker doesn't show a stale symbol
                page.evaluate("localStorage.clear()")
                page.reload(wait_until="networkidle", timeout=10000)
                # wait for the chart to actually have data
                page.wait_for_timeout(3000)
            except Exception as exc:
                print(f"FAIL {cfg['url']}: {exc}", file=sys.stderr)
                continue
            out = repo_root / cfg["path"]
            out.parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(out), full_page=True)
            print(f"saved {out.relative_to(repo_root)}")
            page.close()
        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
