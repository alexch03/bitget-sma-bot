from __future__ import annotations

import logging
import signal
import sys
import time

from .config import load_config
from .exchange import build_exchange
from .telegram_notifier import TelegramNotifier
from .trader import Trader, poll_seconds


def _force_utf8_io() -> None:
    """On Windows the default console codec is cp1252 which mangles unicode.
    Reconfigure stdout/stderr to UTF-8 so logs render correctly anywhere."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def setup_logging(level: str) -> None:
    _force_utf8_io()
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def main() -> int:
    cfg = load_config()
    setup_logging(cfg.log_level)
    log = logging.getLogger("main")

    log.info("bitget-sma-bot starting - mode=%s symbol=%s timeframe=%s",
             cfg.mode, cfg.symbol, cfg.timeframe)

    if cfg.mode == "live":
        log.warning("LIVE MODE ENABLED. Real orders will be placed.")

    exchange = build_exchange(cfg)
    notifier = TelegramNotifier(cfg)
    trader = Trader(cfg, exchange, notifier)

    notifier.send(f"bitget-sma-bot online ({cfg.mode}) {cfg.symbol} {cfg.timeframe}")

    stop = False

    def _stop(_signum, _frame):
        nonlocal stop
        log.info("shutdown signal received")
        stop = True

    signal.signal(signal.SIGINT, _stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _stop)

    interval = poll_seconds(cfg.timeframe)
    log.info("loop interval = %ds", interval)

    while not stop:
        try:
            trader.step()
        except Exception as exc:  # noqa: BLE001
            log.exception("trader.step failed: %s", exc)
            notifier.send(f"bot error: {exc}")
        for _ in range(interval):
            if stop:
                break
            time.sleep(1)

    notifier.send("bitget-sma-bot stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
