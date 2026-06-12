from __future__ import annotations

import asyncio
import logging
from typing import Optional

from .config import Config


log = logging.getLogger(__name__)


class TelegramNotifier:
    """Wraps python-telegram-bot for fire-and-forget notifications.

    If TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is missing, the notifier
    silently no-ops so the bot still runs without Telegram set up.
    """

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._bot = None
        if cfg.telegram_enabled:
            try:
                from telegram import Bot
                self._bot = Bot(token=cfg.telegram_bot_token)
            except Exception as exc:  # noqa: BLE001
                log.warning("Telegram disabled (init failed): %s", exc)
                self._bot = None

    def is_enabled(self) -> bool:
        return self._bot is not None

    def send(self, text: str) -> None:
        if not self._bot:
            log.debug("telegram: %s", text)
            return
        try:
            asyncio.run(self._send_async(text))
        except RuntimeError:
            # Already in an event loop (rare here, but defend anyway)
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(self._send_async(text))
            finally:
                loop.close()
        except Exception as exc:  # noqa: BLE001
            log.warning("Telegram send failed: %s", exc)

    async def _send_async(self, text: str) -> None:
        await self._bot.send_message(chat_id=self.cfg.telegram_chat_id, text=text)
