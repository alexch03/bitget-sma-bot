from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

from .config import Config
from .exchange import BitgetExchange
from .strategy import latest_signal, position_size
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
    def __init__(self, cfg: Config, exchange: BitgetExchange, notifier: TelegramNotifier):
        self.cfg = cfg
        self.exchange = exchange
        self.notifier = notifier
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
        return self.exchange.fetch_balance_usdt()

    def step(self) -> None:
        df = self.exchange.fetch_ohlcv(self.cfg.symbol, self.cfg.timeframe, limit=self.cfg.sma_slow + 50)
        decision = latest_signal(df, self.cfg.sma_fast, self.cfg.sma_slow)
        price = float(df["close"].iloc[-1])

        log.info("[%s] price=%.4f decision=%s reason=%s position=%s",
                 self.cfg.mode, price, decision.signal, decision.reason,
                 self.book.position.side if self.book.position else "none")

        # Decide what to do based on current position and new signal
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

    def _open(self, side: str, price: float) -> None:
        balance = self._current_balance()
        amount = position_size(balance, price, self.cfg.risk_pct)
        if amount <= 0:
            log.warning("computed amount <= 0, skipping")
            return

        side_for_exchange = "buy" if side == "long" else "sell"

        if self.cfg.mode == "paper":
            self.book.open(side, amount, price, time.time())
        elif self.cfg.mode == "dry":
            log.info("[dry] would %s %.6f @ %.4f", side_for_exchange, amount, price)
        else:  # live
            self.exchange.market_order(self.cfg.symbol, side_for_exchange, amount)

        msg = f"OPEN {side.upper()} {self.cfg.symbol} amount={amount:.6f} @ {price:.4f} [{self.cfg.mode}]"
        log.info(msg)
        self.notifier.send(msg)
        self._save_state()

    def _close(self, price: float) -> None:
        assert self.book.position is not None
        pos = self.book.position
        side_for_exchange = "sell" if pos.side == "long" else "buy"

        if self.cfg.mode == "paper":
            pnl = self.book.close(price)
            msg = f"CLOSE {pos.side.upper()} {self.cfg.symbol} @ {price:.4f} pnl={pnl:+.2f} balance={self.book.balance:.2f}"
        elif self.cfg.mode == "dry":
            msg = f"[dry] would close {pos.side} {pos.amount:.6f} @ {price:.4f}"
        else:
            self.exchange.market_order(self.cfg.symbol, side_for_exchange, pos.amount)
            self.book.position = None
            msg = f"CLOSE {pos.side.upper()} {self.cfg.symbol} @ {price:.4f} [live]"

        log.info(msg)
        self.notifier.send(msg)
        self._save_state()


def poll_seconds(timeframe: str) -> int:
    """How often to wake up to check the strategy. Roughly 1/4 of the candle period."""
    table = {"1m": 15, "5m": 60, "15m": 180, "1h": 600, "4h": 1800, "1d": 3600}
    return table.get(timeframe, 60)
