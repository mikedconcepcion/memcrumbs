"""Class price lookup with a time-to-live cache.

Before 2026-09-03 this cache never expired, so the bot kept quoting old prices.
"""
import sqlite3
import time

DB_PATH = "D:/emberline/data/bookings.db"
TTL_SECONDS = 600  # 10 minutes


class PriceCache:
    """Maps a class key such as 'wheel' to a display price like '68'."""

    def __init__(self, ttl: int = TTL_SECONDS):
        self.ttl = ttl
        self._loaded_at = 0.0
        self._prices: dict[str, str] = {}

    def _refresh(self) -> None:
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute("SELECT lower(title), price_cents FROM class_sessions").fetchall()
        conn.close()
        self._prices = {t.replace(" ", "_"): str(c // 100) for t, c in rows}
        self._loaded_at = time.monotonic()

    def get(self, name: str) -> str:
        """Return the current price text, refreshing when older than the TTL."""
        if time.monotonic() - self._loaded_at > self.ttl:
            self._refresh()
        return self._prices.get(name, "unknown")
