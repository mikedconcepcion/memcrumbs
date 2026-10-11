"""Plain dataclasses for the booking domain. All datetimes are timezone-aware UTC."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


@dataclass
class Customer:
    """A person who books classes."""

    id: int
    email: str
    name: str


@dataclass
class ClassSession:
    """One scheduled class with a seat count and a price in cents."""

    id: int
    title: str
    starts_utc: datetime
    seats: int
    price_cents: int


@dataclass
class Booking:
    """A seat held or paid for by a customer."""

    id: int
    customer_id: int
    session_id: int
    status: str = "held"
    hold_expires_utc: datetime | None = None

    def hold_for(self, minutes: int) -> None:
        """Hold the seat for ``minutes`` while the customer pays."""
        self.hold_expires_utc = datetime.now(timezone.utc) + timedelta(minutes=minutes)

    def is_expired(self, now: datetime | None = None) -> bool:
        """True when a held booking has passed its hold expiry."""
        now = now or datetime.now(timezone.utc)
        return self.status == "held" and self.hold_expires_utc is not None and now >= self.hold_expires_utc
