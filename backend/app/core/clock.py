"""Business time is India time: document dates, financial years and lot receipt order."""

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


def start_of_day(d: date) -> datetime:
    """Midnight IST on a business date. Lots received on a date sort FIFO by this."""
    return datetime.combine(d, time(0, 0), tzinfo=IST)


def now_ist() -> datetime:
    return datetime.now(IST)
