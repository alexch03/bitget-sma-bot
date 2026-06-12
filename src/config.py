import os
import sys
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(REPO_ROOT / ".env")


VALID_MODES = ("paper", "dry", "demo", "live")
MODES_THAT_PLACE_ORDERS = ("demo", "live")


VALID_STRATEGIES = ("sma_crossover", "bollinger", "rsi_mean_revert")


@dataclass
class Config:
    api_key: str
    api_secret: str
    api_password: str

    mode: str
    confirm_live: bool

    symbol: str
    timeframe: str

    strategy: str

    # SMA crossover
    sma_fast: int
    sma_slow: int

    # Bollinger
    bb_period: int
    bb_std: float

    # RSI mean revert
    rsi_period: int
    rsi_oversold: float
    rsi_overbought: float

    # Risk management
    risk_pct: float
    stop_loss_pct: float        # 0 = disabled
    take_profit_pct: float      # 0 = disabled

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
            strategy=os.getenv("STRATEGY", "sma_crossover").strip().lower(),
            sma_fast=int(os.getenv("SMA_FAST", "20")),
            sma_slow=int(os.getenv("SMA_SLOW", "50")),
            bb_period=int(os.getenv("BB_PERIOD", "20")),
            bb_std=float(os.getenv("BB_STD", "2.0")),
            rsi_period=int(os.getenv("RSI_PERIOD", "14")),
            rsi_oversold=float(os.getenv("RSI_OVERSOLD", "30")),
            rsi_overbought=float(os.getenv("RSI_OVERBOUGHT", "70")),
            risk_pct=float(os.getenv("RISK_PCT", "2.0")),
            stop_loss_pct=float(os.getenv("STOP_LOSS_PCT", "0")),
            take_profit_pct=float(os.getenv("TAKE_PROFIT_PCT", "0")),
            paper_balance=float(os.getenv("PAPER_BALANCE", "1000")),
            telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
            telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", "").strip(),
            web_host=os.getenv("WEB_HOST", "127.0.0.1").strip(),
            web_port=int(os.getenv("WEB_PORT", "5000")),
            log_level=os.getenv("LOG_LEVEL", "INFO").strip().upper(),
        )
        cfg.validate()
        return cfg

    def build_strategy(self):
        """Instantiate the configured strategy. Imported lazily to avoid cycles."""
        from .strategies import make_strategy
        params = self.strategy_params()
        return make_strategy(self.strategy, **params)

    def strategy_params(self) -> dict:
        if self.strategy == "sma_crossover":
            return {"fast": self.sma_fast, "slow": self.sma_slow}
        if self.strategy == "bollinger":
            return {"period": self.bb_period, "std": self.bb_std}
        if self.strategy == "rsi_mean_revert":
            return {
                "period": self.rsi_period,
                "oversold": self.rsi_oversold,
                "overbought": self.rsi_overbought,
            }
        raise ValueError(f"unknown strategy: {self.strategy!r}")

    def validate(self) -> None:
        if self.mode not in VALID_MODES:
            raise ValueError(f"MODE must be one of {VALID_MODES}, got {self.mode!r}")

        if self.strategy not in VALID_STRATEGIES:
            raise ValueError(f"STRATEGY must be one of {VALID_STRATEGIES}, got {self.strategy!r}")

        if self.sma_fast >= self.sma_slow:
            raise ValueError("SMA_FAST must be smaller than SMA_SLOW")

        if self.bb_period < 2:
            raise ValueError("BB_PERIOD must be >= 2")
        if self.bb_std <= 0:
            raise ValueError("BB_STD must be > 0")

        if self.rsi_period < 2:
            raise ValueError("RSI_PERIOD must be >= 2")
        if not (0 < self.rsi_oversold < self.rsi_overbought < 100):
            raise ValueError("RSI_OVERSOLD < RSI_OVERBOUGHT required, both in (0, 100)")

        if not (0 < self.risk_pct <= 100):
            raise ValueError("RISK_PCT must be in (0, 100]")

        if self.stop_loss_pct < 0 or self.stop_loss_pct >= 100:
            raise ValueError("STOP_LOSS_PCT must be in [0, 100)")
        if self.take_profit_pct < 0:
            raise ValueError("TAKE_PROFIT_PCT must be >= 0")

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
