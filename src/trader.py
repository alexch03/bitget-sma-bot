from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

from .config import Config
from .exchange import BitgetExchange
from .strategies import Strategy
from .strategy import position_size
from .telegram_notifier import TelegramNotifier


log = logging.getLogger(__name__)


STATE_FILE = Path(__file__).resolve().parent.parent / "state.json"


@dataclass
class Position:
    side: str        # "long" or "short"
    amount: float
    entry_price: float
    opened_at: float  # epoch seconds

    def pnl(self, current_price: float) -> float:
        direction = 1 if self.side == "long" else -1
        return direction * (current_price - self.entry_price) * self.amount


@dataclass
class PaperBook:
    balance: float
    position: Optional[Position] = None

    def open(self, side: str, amount: float, price: float, ts: float) -> None:
        self.position = Position(side=side, amount=amount, entry_price=price, opened_at=ts)

    def close(self, exit_price: float) -> float:
        assert self.position is not None
        pnl = self.position.pnl(exit_price)
        self.balance += pnl
        self.position = None
        return pnl


class Trader:
    def __init__(
        self,
        cfg: Config,
        exchange: BitgetExchange,
        notifier: TelegramNotifier,
        strategy: Strategy | None = None,
    ):
        self.cfg = cfg
        self.exchange = exchange
        self.notifier = notifier
        self.strategy = strategy if strategy is not None else cfg.build_strategy()
        self.book = self._load_or_init_book()

    def _load_or_init_book(self) -> PaperBook:
        if STATE_FILE.exists() and self.cfg.mode == "paper":
            try:
                data = json.loads(STATE_FILE.read_text())
                pos = None
                if data.get("position"):
                    pos = Position(**data["position"])
                return PaperBook(balance=data["balance"], position=pos)
            except Exception as exc:  # noqa: BLE001
                log.warning("could not restore state: %s — starting fresh", exc)
        return PaperBook(balance=self.cfg.paper_balance)

    def _save_state(self) -> None:
        if self.cfg.mode != "paper":
            return
        payload = {
            "balance": self.book.balance,
            "position": asdict(self.book.position) if self.book.position else None,
        }
        STATE_FILE.write_text(json.dumps(payload, indent=2))

    def _current_balance(self) -> float:
        if self.cfg.mode == "paper":
            return self.book.balance
        if self.cfg.mode == "dry":
            return self.cfg.paper_balance
        # demo and live both query the real (or demo) account
        return self.exchange.fetch_balance_usdt()

    def step(self) -> None:
        limit = max(self.strategy.warmup() + 50, 100)
        df = self.exchange.fetch_ohlcv(self.cfg.symbol, self.cfg.timeframe, limit=limit)
        price = float(df["close"].iloc[-1])

        # SL/TP first: if a position is open and the current price hits the
        # configured stop or target, exit before considering the strategy.
        if self.book.position is not None:
            hit = self._sl_tp_hit(price)
            if hit is not None:
                log.info("[%s] %s hit at price=%.4f, closing position", self.cfg.mode, hit, price)
                self._close(price, reason=hit)
                return

        decision = self.strategy.signal(df)

        log.info("[%s] price=%.4f strategy=%s signal=%s reason=%s position=%s",
                 self.cfg.mode, price, self.strategy.name, decision.signal, decision.reason,
                 self.book.position.side if self.book.position else "none")

        if decision.signal == "flat":
            return

        if self.book.position is None:
            self._open(decision.signal, price)
            return

        # We have a position; if the signal flips, close + reopen the other way.
        if (self.book.position.side == "long" and decision.signal == "short") or \
           (self.book.position.side == "short" and decision.signal == "long"):
            self._close(price)
            self._open(decision.signal, price)

    def _sl_tp_hit(self, price: float) -> str | None:
        """Return 'SL' / 'TP' if the current price hits the configured stop or
        target relative to the open position, else None.

        SL/TP are checked locally on each tick. They are NOT placed as exchange
        orders. If the bot is down when price moves, no exit happens. Document
        this trade-off in docs/strategy.md.
        """
        pos = self.book.position
        if pos is None:
            return None

        sl_pct = self.cfg.stop_loss_pct
        tp_pct = self.cfg.take_profit_pct

        if sl_pct > 0:
            if pos.side == "long" and price <= pos.entry_price * (1 - sl_pct / 100):
                return "SL"
            if pos.side == "short" and price >= pos.entry_price * (1 + sl_pct / 100):
                return "SL"

        if tp_pct > 0:
            if pos.side == "long" and price >= pos.entry_price * (1 + tp_pct / 100):
                return "TP"
            if pos.side == "short" and price <= pos.entry_price * (1 - tp_pct / 100):
                return "TP"

        return None

    def _open(self, side: str, price: float) -> None:
        balance = self._current_balance()
        amount = position_size(balance, price, self.cfg.risk_pct)
        if amount <= 0:
            log.warning("computed amount <= 0, skipping")
            return

        side_for_exchange = "buy" if side == "long" else "sell"

        if self.cfg.mode == "dry":
            log.info("[dry] would %s %.6f @ %.4f", side_for_exchange, amount, price)
        else:
            if self.cfg.mode in ("demo", "live"):
                self.exchange.market_order(self.cfg.symbol, side_for_exchange, amount)
            # track the position locally so the next tick knows we are in a
            # trade. In demo/live we assume the market order fills near the
            # requested price — slippage is not modelled.
            self.book.open(side, amount, price, time.time())

        msg = f"OPEN {side.upper()} {self.cfg.symbol} amount={amount:.6f} @ {price:.4f} [{self.cfg.mode}]"
        log.info(msg)
        self.notifier.send(msg)
        self._save_state()

    def _close(self, price: float, reason: str = "signal") -> None:
        assert self.book.position is not None
        pos = self.book.position
        side_for_exchange = "sell" if pos.side == "long" else "buy"

        if self.cfg.mode == "dry":
            msg = f"[dry] would close {pos.side} {pos.amount:.6f} @ {price:.4f} ({reason})"
        else:
            if self.cfg.mode in ("demo", "live"):
                self.exchange.market_order(self.cfg.symbol, side_for_exchange, pos.amount)
            pnl = self.book.close(price)
            msg = f"CLOSE {pos.side.upper()} {self.cfg.symbol} @ {price:.4f} pnl={pnl:+.2f} balance={self.book.balance:.2f} reason={reason} [{self.cfg.mode}]"

        log.info(msg)
        self.notifier.send(msg)
        self._save_state()


def poll_seconds(timeframe: str) -> int:
    """How often to wake up to check the strategy. Roughly 1/4 of the candle period."""
    table = {"1m": 15, "5m": 60, "15m": 180, "1h": 600, "4h": 1800, "1d": 3600}
    return table.get(timeframe, 60)
