"""Load the FAQ knowledge file used by the chat bot."""
import json
from pathlib import Path

FAQ_PATH = Path(__file__).resolve().parent / "knowledge" / "faq.json"
_cache: list[dict] | None = None


def faq_entries() -> list[dict]:
    """Return FAQ entries, loading the file on first use."""
    global _cache
    if _cache is None:
        reload()
    return _cache


def reload() -> int:
    """Re-read faq.json (called by ChatKnowledgeRefresh at 04:00 and by /reload).

    Returns the number of entries loaded.
    """
    global _cache
    _cache = json.loads(FAQ_PATH.read_text(encoding="utf-8")) if FAQ_PATH.exists() else []
    return len(_cache)
