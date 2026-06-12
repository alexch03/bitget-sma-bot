from __future__ import annotations

import logging
import time

import ccxt
import pandas as pd

from .config import Config


log = logging.getLogger(__name__)


class BitgetExchange:
    """Thin wrapper over ccxt's Bitget client.

    Public methods (fetch_ohlcv, fetch_ticker) work without credentials.
    Trading methods (market_order, close_position) require keys.
    """

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.client = ccxt.bitget({
            "apiKey": cfg.api_key,
            "secret": cfg.api_secret,
            "password": cfg.api_password,
            "enableRateLimit": True,
            "options": {
                "defaultType": "swap",
                "defaultSubType": "linear",
            },
        })
        if cfg.mode == "demo":
            # Bitget demo trading requires header `paptrading: 1` (per official docs).
            # ccxt's set_sandbox_mode adds it for Bitget; we also set it explicitly
            # as a belt-and-suspenders guarantee.
            try:
                self.client.set_sandbox_mode(True)
            except Exception:
                self.client.options["sandboxMode"] = True
            self.client.headers["paptrading"] = "1"
            log.info("Bitget exchange set to DEMO (header paptrading=1)")

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 200) -> pd.DataFrame:
        raw = self.client.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        df = df.set_index("timestamp")
        return df

    def fetch_ohlcv_range(
        self, symbol: str, timeframe: str, since_ms: int, until_ms: int
    ) -> pd.DataFrame:
        """Paginated fetch — used by the backtest script."""
        out: list[list] = []
        cursor = since_ms
        tf_ms = self.client.parse_timeframe(timeframe) * 1000

        while cursor < until_ms:
            batch = self.client.fetch_ohlcv(symbol, timeframe=timeframe, since=cursor, limit=1000)
            if not batch:
                break
            out.extend(batch)
            cursor = batch[-1][0] + tf_ms
            time.sleep(self.client.rateLimit / 1000)

        df = pd.DataFrame(out, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df = df.drop_duplicates(subset="timestamp").reset_index(drop=True)
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        df = df.set_index("timestamp")
        return df

    def fetch_balance_usdt(self) -> float:
        try:
            bal = self.client.fetch_balance({"type": "swap"})
        except ccxt.ExchangeError as exc:
            if "40099" in str(exc) or "environment is incorrect" in str(exc).lower():
                raise RuntimeError(
                    "Bitget returned 'exchange environment is incorrect'. "
                    "This means the API key you provided was generated on the LIVE "
                    "dashboard, not the DEMO dashboard. Generate a demo key at "
                    "https://www.bitget.com/asset/demo-trading (Personal Center -> "
                    "API Key Management -> Create Demo API Key) and update your .env."
                ) from exc
            raise
        return float(bal.get("USDT", {}).get("free", 0.0) or 0.0)

    def fetch_ticker_price(self, symbol: str) -> float:
        t = self.client.fetch_ticker(symbol)
        return float(t["last"])

    def market_order(self, symbol: str, side: str, amount: float) -> dict:
        assert side in ("buy", "sell"), side
        log.info("placing %s market order on %s amount=%.6f", side, symbol, amount)
        return self.client.create_order(symbol, "market", side, amount)


def build_exchange(cfg: Config) -> BitgetExchange:
    return BitgetExchange(cfg)
