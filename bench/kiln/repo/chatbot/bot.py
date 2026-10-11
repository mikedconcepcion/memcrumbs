"""Answering logic for the student chat bot (port 8091, health at /ping)."""
import re

from .knowledge import faq_entries
from .prices import PriceCache

FALLBACK = "I am not sure. Please ask the studio at the front desk."
_prices = PriceCache()


def score(question: str, keywords: list[str]) -> int:
    """Count how many FAQ keywords occur in the question."""
    words = set(re.findall(r"[a-z0-9]+", question.lower()))
    return sum(1 for k in keywords if k in words)


def answer(question: str) -> str:
    """Return the best FAQ answer, filling {price:<class>} placeholders from the price cache."""
    best, best_score = None, 0
    for entry in faq_entries():
        s = score(question, entry["keywords"])
        if s > best_score:
            best, best_score = entry, s
    if best is None:
        return FALLBACK
    text = best["answer"]
    for name in re.findall(r"\{price:([a-z_]+)\}", text):
        text = text.replace("{price:%s}" % name, _prices.get(name))
    return text
