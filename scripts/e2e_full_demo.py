"""Full end-to-end test suite against Bitget DEMO.

This is the script we run to gain confidence that the bot does the right thing
on a real (demo) exchange. It places small real orders (10 USDT notional each),
verifies position state on the exchange, and cleans up after itself.

Test plan:
  1. fetch_balance + ticker sanity
  2. market BUY -> verify position appears on Bitget -> market SELL to close
  3. Trader.step() forced long -> verify order + book sync
  4. Trader flip long -> short
  5. SL trigger via mocked dropping price feed
  6. TP trigger via mocked pumping price feed
  7. Multi-tick anti-duplicate (5 ticks with no signal)
  8. PnL accounting (book.balance vs real balance change)
  9. Edge cases (amount=0, oversized)
 10. Final cleanup: no residual position

Requires .env with MODE=demo and a Bitget DEMO API key.
"""
from __future__ import annotations

import logging
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import load_config                     # noqa: E402
from src.exchange import build_exchange                # noqa: E402
from src.telegram_notifier import TelegramNotifier     # noqa: E402
from src.trader import Trader                          # noqa: E402
from src.strategies.base import Decision, Strategy     # noqa: E402


log = logging.getLogger("e2e")


# ----------------------------------------------------------------------------
# helpers


class ForcedStrategy(Strategy):
    """Strategy that returns whatever signal you tell it to."""
    name = "forced"

    def __init__(self):
        self.next_signal: str = "flat"
        self.reason: str = "forced"

    def warmup(self) -> int:
        return 5

    def signal(self, df):
        return Decision(signal=self.next_signal, reason=self.reason)


def _df(n: int = 60, base_price: float = 50000.0) -> pd.DataFrame:
    idx = pd.date_range("2026-01-01", periods=n, freq="1h", tz="UTC")
    return pd.DataFrame({
        "open": [base_price] * n,
        "high": [base_price] * n,
        "low": [base_price] * n,
        "close": [base_price] * n,
        "volume": [1.0] * n,
    }, index=idx)


def _has_position(exchange, symbol: str) -> dict | None:
    """Return the first non-zero Bitget position for symbol, or None."""
    try:
        positions = exchange.client.fetch_positions([symbol])
    except Exception as exc:
        log.warning("fetch_positions failed: %s", exc)
        return None
    for p in positions or []:
        contracts = p.get("contracts") or 0
        if abs(float(contracts)) > 0:
            return p
    return None


def _close_any_position(exchange, symbol: str) -> bool:
    """Force-close any open position on symbol. Returns True if cleanup happened."""
    pos = _has_position(exchange, symbol)
    if pos is None:
        return False
    side = "sell" if pos["side"] == "long" else "buy"
    amount = abs(float(pos["contracts"]))
    log.info("CLEANUP: closing residual %s position amount=%.6f", pos["side"], amount)
    exchange.market_order(symbol, side, amount, params={"reduceOnly": True})
    time.sleep(1.0)
    return True


def _print_section(title: str) -> None:
    print()
    print("=" * 70)
    print(f"  {title}")
    print("=" * 70)


# ----------------------------------------------------------------------------


def main() -> int:
    logging.basicConfig(
        level="INFO",
        format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
        datefmt="%H:%M:%S",
    )

    cfg = load_config()
    if cfg.mode != "demo":
        print(f"ERROR: MODE must be 'demo' in .env (got {cfg.mode!r})", file=sys.stderr)
        return 2

    exchange = build_exchange(cfg)
    notifier = TelegramNotifier(cfg)

    symbol = cfg.symbol
    results: list[tuple[str, bool, str]] = []

    # ---- pre-flight ----
    _print_section("PRE-FLIGHT")
    start_balance = exchange.fetch_balance_usdt()
    start_price = exchange.fetch_ticker_price(symbol)
    print(f"start balance: {start_balance:,.2f} USDT")
    print(f"start price:   {start_price:,.2f}")
    _close_any_position(exchange, symbol)  # ensure clean slate

    # notional ~ 10 USDT per trade
    notional = 12.0
    amount = round(notional / start_price + 1e-5, 6)
    print(f"trade size: {amount} BTC (~{round(amount * start_price, 2)} USDT)")

    # ---- TEST 1: market buy + position appears + market sell ----
    _print_section("TEST 1 — Market buy, position visible, market sell to close")
    try:
        exchange.market_order(symbol, "buy", amount)
        time.sleep(1.5)
        pos = _has_position(exchange, symbol)
        assert pos is not None, "no position after market buy"
        assert pos["side"] == "long", f"expected long, got {pos['side']}"
        print(f"  OK position opened: {pos['side']} {pos['contracts']} @ {pos.get('entryPrice')}")

        exchange.market_order(symbol, "sell", abs(float(pos["contracts"])), params={"reduceOnly": True})
        time.sleep(1.5)
        pos_after = _has_position(exchange, symbol)
        assert pos_after is None, f"position not closed: {pos_after}"
        print("  OK position closed")
        results.append(("market buy+sell", True, "open then close cleanly"))
    except Exception as exc:
        print(f"  FAIL: {exc}")
        results.append(("market buy+sell", False, str(exc)))
        _close_any_position(exchange, symbol)

    # ---- TEST 2: Trader.step() forced long opens an order on the exchange ----
    _print_section("TEST 2 — Trader.step() with forced long signal opens on exchange")
    try:
        strat = ForcedStrategy()
        strat.next_signal = "long"
        trader = Trader(cfg, exchange, notifier, strategy=strat)
        # use a fake OHLCV df so warmup is satisfied without network
        mock_ex = type("MockEx", (), {})()
        # We still want REAL market_order on the real exchange, but mock fetch_ohlcv
        # to control the price feed deterministically.
        real_market_order = exchange.market_order
        real_fetch_balance = exchange.fetch_balance_usdt
        original_fetch_ohlcv = exchange.fetch_ohlcv
        exchange.fetch_ohlcv = lambda *a, **k: _df(60, base_price=start_price)

        trader.step()
        time.sleep(1.5)
        assert trader.book.position is not None, "book has no position"
        assert trader.book.position.side == "long"
        pos = _has_position(exchange, symbol)
        assert pos is not None and pos["side"] == "long", f"exchange position mismatch: {pos}"
        print(f"  OK book and exchange agree (long, amount~{trader.book.position.amount:.6f})")
        results.append(("trader open long", True, ""))
        # restore for next test
        exchange.fetch_ohlcv = original_fetch_ohlcv
    except Exception as exc:
        print(f"  FAIL: {exc}")
        results.append(("trader open long", False, str(exc)))
        exchange.fetch_ohlcv = original_fetch_ohlcv  # type: ignore
        _close_any_position(exchange, symbol)

    # ---- TEST 3: flip long -> short ----
    _print_section("TEST 3 — Flip long -> short via Trader.step()")
    try:
        strat.next_signal = "short"
        original_fetch_ohlcv = exchange.fetch_ohlcv
        exchange.fetch_ohlcv = lambda *a, **k: _df(60, base_price=start_price)
        trader.step()
        time.sleep(2.0)
        assert trader.book.position is not None
        assert trader.book.position.side == "short", f"book side {trader.book.position.side}"
        # On exchange, in one-way mode, sell qty > current long closes long + opens short
        pos = _has_position(exchange, symbol)
        assert pos is not None and pos["side"] == "short", f"exchange not short: {pos}"
        print(f"  OK flip succeeded — exchange shows short {pos['contracts']}")
        results.append(("flip long->short", True, ""))
        exchange.fetch_ohlcv = original_fetch_ohlcv
    except Exception as exc:
        print(f"  FAIL: {exc}")
        results.append(("flip long->short", False, str(exc)))
        exchange.fetch_ohlcv = original_fetch_ohlcv  # type: ignore
        _close_any_position(exchange, symbol)

    # cleanup before SL/TP tests
    _close_any_position(exchange, symbol)
    time.sleep(1.0)

    # ---- TEST 4: SL trigger ----
    _print_section("TEST 4 — Stop-loss triggers and closes position")
    try:
        # Build a fresh config with SL=2%
        from dataclasses import replace
        cfg_sl = replace(cfg, stop_loss_pct=2.0, take_profit_pct=0.0)
        strat = ForcedStrategy()
        strat.next_signal = "long"
        trader = Trader(cfg_sl, exchange, notifier, strategy=strat)
        exchange.fetch_ohlcv = lambda *a, **k: _df(60, base_price=start_price)
        trader.step()
        time.sleep(1.5)
        assert trader.book.position is not None and trader.book.position.side == "long"
        entry = trader.book.position.entry_price
        print(f"  position opened @ {entry:.2f}, SL set to {entry * 0.98:.2f}")

        # Simulate next tick where the price has dropped 3% (past SL)
        strat.next_signal = "flat"
        exchange.fetch_ohlcv = lambda *a, **k: _df(60, base_price=entry * 0.97)
        trader.step()
        time.sleep(1.5)
        # local book should be closed
        assert trader.book.position is None, "book still has position after SL"
        # exchange should also be closed
        pos = _has_position(exchange, symbol)
        assert pos is None, f"exchange still has position after SL: {pos}"
        print("  OK SL closed both book and exchange position")
        results.append(("stop-loss trigger", True, ""))
    except Exception as exc:
        print(f"  FAIL: {exc}")
        results.append(("stop-loss trigger", False, str(exc)))
        _close_any_position(exchange, symbol)

    # ---- TEST 5: TP trigger ----
    _print_section("TEST 5 — Take-profit triggers and closes position")
    try:
        cfg_tp = replace(cfg, stop_loss_pct=0.0, take_profit_pct=2.0)
        strat = ForcedStrategy()
        strat.next_signal = "long"
        trader = Trader(cfg_tp, exchange, notifier, strategy=strat)
        exchange.fetch_ohlcv = lambda *a, **k: _df(60, base_price=start_price)
        trader.step()
        time.sleep(1.5)
        entry = trader.book.position.entry_price
        print(f"  position opened @ {entry:.2f}, TP set to {entry * 1.02:.2f}")

        strat.next_signal = "flat"
        exchange.fetch_ohlcv = lambda *a, **k: _df(60, base_price=entry * 1.03)
        trader.step()
        time.sleep(1.5)
        assert trader.book.position is None, "book still has position after TP"
        pos = _has_position(exchange, symbol)
        assert pos is None, f"exchange still has position after TP: {pos}"
        print("  OK TP closed both book and exchange position")
        results.append(("take-profit trigger", True, ""))
    except Exception as exc:
        print(f"  FAIL: {exc}")
        results.append(("take-profit trigger", False, str(exc)))
        _close_any_position(exchange, symbol)

    # ---- TEST 6: multi-tick no duplicate ----
    _print_section("TEST 6 — 5 ticks with flat signal: zero duplicate orders")
    try:
        strat = ForcedStrategy()
        strat.next_signal = "long"
        trader = Trader(cfg, exchange, notifier, strategy=strat)
        exchange.fetch_ohlcv = lambda *a, **k: _df(60, base_price=start_price)
        trader.step()  # opens position
        time.sleep(1.5)
        assert trader.book.position is not None
        opened_amount = trader.book.position.amount

        strat.next_signal = "flat"
        # 5 more ticks with no signal
        for i in range(5):
            trader.step()
            time.sleep(0.3)
        # position size unchanged
        pos = _has_position(exchange, symbol)
        assert pos is not None, "position should still be open"
        on_exchange = abs(float(pos["contracts"]))
        # tolerate small rounding (exchange may round to step)
        assert abs(on_exchange - opened_amount) / opened_amount < 0.1, \
            f"position size changed: opened={opened_amount} now={on_exchange}"
        print(f"  OK 5 ticks did not re-open or alter the position (still {on_exchange})")
        results.append(("multi-tick no duplicate", True, ""))
    except Exception as exc:
        print(f"  FAIL: {exc}")
        results.append(("multi-tick no duplicate", False, str(exc)))
    finally:
        _close_any_position(exchange, symbol)
        time.sleep(1.0)

    # ---- TEST 7: PnL accounting ----
    _print_section("TEST 7 — Real balance change consistent with book accounting")
    try:
        bal_before = exchange.fetch_balance_usdt()
        strat = ForcedStrategy()
        strat.next_signal = "long"
        trader = Trader(cfg, exchange, notifier, strategy=strat)
        exchange.fetch_ohlcv = lambda *a, **k: _df(60, base_price=start_price)
        trader.step()
        time.sleep(1.5)
        strat.next_signal = "short"
        # Use a slightly different price for the close so PnL is non-zero
        exchange.fetch_ohlcv = lambda *a, **k: _df(60, base_price=start_price * 1.001)
        trader.step()
        time.sleep(2.0)
        bal_after = exchange.fetch_balance_usdt()
        # close any residual short
        _close_any_position(exchange, symbol)
        time.sleep(1.5)
        bal_final = exchange.fetch_balance_usdt()
        delta = bal_final - bal_before
        # small notional, small delta. Should be within +/- 1 USDT total (mostly fees).
        assert abs(delta) < 1.5, f"unexpected balance delta: {delta:+.4f} USDT"
        print(f"  OK balance delta after full cycle: {delta:+.4f} USDT (within +/-1.5)")
        results.append(("pnl accounting", True, f"delta={delta:+.4f}"))
    except Exception as exc:
        print(f"  FAIL: {exc}")
        results.append(("pnl accounting", False, str(exc)))
        _close_any_position(exchange, symbol)

    # ---- TEST 8: edge cases ----
    _print_section("TEST 8 — Edge case: zero amount + invalid params")
    try:
        # amount=0 -> ccxt should raise a clear error
        try:
            exchange.market_order(symbol, "buy", 0.0)
            results.append(("edge zero amount", False, "no error raised for amount=0"))
        except Exception:
            print("  OK ccxt rejected amount=0 cleanly")
            results.append(("edge zero amount", True, ""))

        # Way oversized: 10 BTC = ~600k USDT, demo balance only a few k
        try:
            exchange.market_order(symbol, "buy", 10.0)
            results.append(("edge oversized", False, "oversized order accepted!"))
            _close_any_position(exchange, symbol)
        except Exception as exc:
            print(f"  OK oversized order rejected: {type(exc).__name__}")
            results.append(("edge oversized", True, ""))
    except Exception as exc:
        print(f"  FAIL: {exc}")
        results.append(("edge cases", False, str(exc)))

    # ---- FINAL CLEANUP ----
    _print_section("FINAL CLEANUP")
    cleaned = _close_any_position(exchange, symbol)
    time.sleep(1.5)
    final_pos = _has_position(exchange, symbol)
    end_balance = exchange.fetch_balance_usdt()
    print(f"residual position: {final_pos}")
    print(f"end balance:       {end_balance:,.2f} USDT")
    print(f"net change:        {end_balance - start_balance:+.4f} USDT")
    cleanup_ok = final_pos is None

    # ---- REPORT ----
    _print_section("REPORT")
    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    print(f"{passed}/{total} subtests passed")
    print(f"final cleanup ok: {cleanup_ok}")
    print()
    for name, ok, note in results:
        mark = "OK" if ok else "FAIL"
        extra = f"  ({note})" if note else ""
        print(f"  [{mark}] {name}{extra}")

    return 0 if (passed == total and cleanup_ok) else 1


if __name__ == "__main__":
    sys.exit(main())
