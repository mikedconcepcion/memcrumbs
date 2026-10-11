"""Load booking.toml and the environment-held secrets."""
import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "config" / "booking.toml"


@dataclass(frozen=True)
class Settings:
    """Resolved settings for the booking app."""

    db_path: str
    hold_minutes: int
    timezone: str
    provider_url: str
    payment_timeout: int
    api_key: str


def load_settings(path: Path = DEFAULT_PATH) -> Settings:
    """Read the TOML file and fetch the payment API key from the machine environment.

    The key is never stored in the file; ``api_key_env`` names the variable
    (normally PAYPROV_API_KEY, set machine-wide on web-srv).
    """
    with open(path, "rb") as fh:
        raw = tomllib.load(fh)
    key_var = raw["payments"]["api_key_env"]
    api_key = os.environ.get(key_var, "")
    return Settings(
        db_path=raw["database"]["path"],
        hold_minutes=raw["server"]["hold_minutes"],
        timezone=raw["studio"]["timezone"],
        provider_url=raw["payments"]["provider_url"],
        payment_timeout=raw["payments"]["timeout_seconds"],
        api_key=api_key,
    )
