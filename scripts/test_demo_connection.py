"""End-to-end smoke test for the Bitget demo connection.

Reads credentials from .env (must be set to MODE=demo), then:
  1. Fetches USDT futures balance
  2. Fetches BTC/USDT:USDT ticker
  3. Places a small limit BUY 50% below market (cannot fill at this price)
  4. Fetches open orders to confirm the order is visible
  5. Cancels the order
  6. Re-fetches open orders to confirm it is gone

The order notional is just above Bitget's 5 USDT minimum (~10 USDT here).
No risk of accidental fill: the limit price is half of spot.

Usage:
    python scripts/test_demo_connection.py
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import load_config        # noqa: E402
from src.exchange import build_exchange   # noqa: E402


def main() -> int:
    logging.basicConfig(
        level="INFO",
        format="%(asctime)s %(levelname)s :: %(message)s",
        datefmt="%H:%M:%S",
    )
    log = logging.getLogger("demo-e2e")

    cfg = load_config()
    if cfg.mode != "demo":
        print(f"ERROR: MODE must be 'demo' in .env (got {cfg.mode!r})", file=sys.stderr)
        return 2

    exchange = build_exchange(cfg)

    log.info("1/6 fetching demo balance...")
    bal = exchange.fetch_balance_usdt()
    print(f"   demo balance: {bal:,.2f} USDT")

    log.info("2/6 fetching ticker...")
    price = exchange.fetch_ticker_price(cfg.symbol)
    print(f"   {cfg.symbol} last: {price:,.2f}")

    log.info("3/6 placing limit BUY 50%% below market (cannot fill)...")
    limit_price = round(price * 0.5, 1)
    # min notional on Bitget USDT-M is 5 USDT; we use ~10 for safety
    amount = round(10.0 / limit_price + 1e-5, 6)
    notional = round(amount * limit_price, 2)
    order = exchange.client.create_order(cfg.symbol, "limit", "buy", amount, limit_price)
    order_id = order.get("id")
    print(f"   placed id={order_id}  amount={amount}  price={limit_price}  notional={notional} USDT")

    log.info("4/6 fetching open orders...")
    open_orders = exchange.client.fetch_open_orders(cfg.symbol)
    matching = [o for o in open_orders if o["id"] == order_id]
    print(f"   our order found: {len(matching) == 1}")
    if not matching:
        print(f"   ERROR: order id {order_id} not in open orders", file=sys.stderr)
        return 1

    log.info("5/6 cancelling the order...")
    exchange.client.cancel_order(order_id, cfg.symbol)

    log.info("6/6 verifying it is gone...")
    open_after = exchange.client.fetch_open_orders(cfg.symbol)
    remaining = [o for o in open_after if o["id"] == order_id]
    print(f"   remaining with that id: {len(remaining)} (expected 0)")

    if remaining:
        print("FAIL: order still open after cancel", file=sys.stderr)
        return 1

    print()
    print("=== Bitget demo E2E PASSED ===")
    print("Your demo keys, the paptrading header, and order placement all work.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
