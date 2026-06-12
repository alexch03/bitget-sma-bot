import os
import sys
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(REPO_ROOT / ".env")


VALID_MODES = ("paper", "dry", "demo", "live")
MODES_THAT_PLACE_ORDERS = ("demo", "live")


@dataclass
class Config:
    api_key: str
    api_secret: str
    api_password: str

    mode: str
    confirm_live: bool

    symbol: str
    timeframe: str

    sma_fast: int
    sma_slow: int
    risk_pct: float
    paper_balance: float

    telegram_bot_token: str
    telegram_chat_id: str

    web_host: str
    web_port: int

    log_level: str

    @classmethod
    def from_env(cls) -> "Config":
        cfg = cls(
            api_key=os.getenv("BITGET_API_KEY", "").strip(),
            api_secret=os.getenv("BITGET_API_SECRET", "").strip(),
            api_password=os.getenv("BITGET_API_PASSWORD", "").strip(),
            mode=os.getenv("MODE", "paper").strip().lower(),
            confirm_live=os.getenv("CONFIRM_LIVE", "no").strip().lower() == "yes",
            symbol=os.getenv("SYMBOL", "BTC/USDT:USDT").strip(),
            timeframe=os.getenv("TIMEFRAME", "1h").strip(),
            sma_fast=int(os.getenv("SMA_FAST", "20")),
            sma_slow=int(os.getenv("SMA_SLOW", "50")),
            risk_pct=float(os.getenv("RISK_PCT", "2.0")),
            paper_balance=float(os.getenv("PAPER_BALANCE", "1000")),
            telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
            telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", "").strip(),
            web_host=os.getenv("WEB_HOST", "127.0.0.1").strip(),
            web_port=int(os.getenv("WEB_PORT", "5000")),
            log_level=os.getenv("LOG_LEVEL", "INFO").strip().upper(),
        )
        cfg.validate()
        return cfg

    def validate(self) -> None:
        if self.mode not in VALID_MODES:
            raise ValueError(f"MODE must be one of {VALID_MODES}, got {self.mode!r}")

        if self.sma_fast >= self.sma_slow:
            raise ValueError("SMA_FAST must be smaller than SMA_SLOW")

        if not (0 < self.risk_pct <= 100):
            raise ValueError("RISK_PCT must be in (0, 100]")

        if self.mode == "live":
            if not self.confirm_live:
                raise RuntimeError(
                    "MODE=live requires CONFIRM_LIVE=yes in .env. "
                    "Read DISCLAIMER.md before enabling."
                )
            if not (self.api_key and self.api_secret and self.api_password):
                raise RuntimeError("MODE=live requires Bitget API credentials")

        if self.mode == "demo":
            if not (self.api_key and self.api_secret and self.api_password):
                raise RuntimeError(
                    "MODE=demo requires Bitget DEMO API credentials "
                    "(generate them on https://www.bitget.com/asset/demo-trading)"
                )

    @property
    def telegram_enabled(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_chat_id)


def load_config() -> Config:
    try:
        return Config.from_env()
    except (ValueError, RuntimeError) as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        raise
