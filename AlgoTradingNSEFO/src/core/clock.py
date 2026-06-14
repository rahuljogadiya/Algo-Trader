from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from datetime import timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


try:
    IST = ZoneInfo("Asia/Kolkata")
except ZoneInfoNotFoundError:
    # Fallback for environments without tzdata.
    IST = timezone(timedelta(hours=5, minutes=30))


def parse_hhmm(t: str) -> time:
    # expects "HH:MM"
    hh, mm = t.split(":")
    return time(int(hh), int(mm))


# Backwards/alternate name used by some callers/tests
def parse_time_hhmm(t: str) -> time:
    return parse_hhmm(t)


@dataclass(frozen=True)
class MarketClock:
    tz: ZoneInfo = IST
    market_open: time = time(9, 15)
    market_close: time = time(15, 30)

    def now(self) -> datetime:
        return datetime.now(self.tz)

    def today_open_dt(self, *, ref: datetime | None = None) -> datetime:
        ref = ref or self.now()
        # Preserve tz-awareness of the reference datetime to avoid naive/aware comparison errors.
        if ref.tzinfo is None:
            return datetime.combine(ref.date(), self.market_open)
        return datetime.combine(ref.date(), self.market_open, tzinfo=self.tz)

    def is_within_first_minutes(self, minutes: int, *, ref: datetime | None = None) -> bool:
        ref = ref or self.now()
        open_dt = self.today_open_dt(ref=ref)
        return open_dt <= ref < (open_dt + timedelta(minutes=minutes))

    def is_after_time(self, t: time, *, ref: datetime | None = None) -> bool:
        ref = ref or self.now()
        return ref.time() >= t

    def is_before_time(self, t: time, *, ref: datetime | None = None) -> bool:
        ref = ref or self.now()
        return ref.time() <= t

    def cutoff_time_reached(self, no_new_trades_after: time, *, ref: datetime | None = None) -> bool:
        return self.is_after_time(no_new_trades_after, ref=ref)

    def square_off_reached(self, square_off: time, *, ref: datetime | None = None) -> bool:
        return self.is_after_time(square_off, ref=ref)
