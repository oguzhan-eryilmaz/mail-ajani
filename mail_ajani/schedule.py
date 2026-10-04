from datetime import datetime, timedelta

SLOT_HOURS = (0, 6, 12, 18)
FIRST_RUN_LOOKBACK = timedelta(hours=24)
FETCH_OVERLAP = timedelta(hours=1)
QUIET_UNTIL_HOUR = 8


def latest_slot(now: datetime) -> datetime:
    hour = max(h for h in SLOT_HOURS if h <= now.hour)
    return now.replace(hour=hour, minute=0, second=0, microsecond=0)


def should_run(now: datetime, last_run: datetime | None) -> bool:
    return last_run is None or last_run < latest_slot(now)


def fetch_since(now: datetime, last_fetch: datetime | None) -> datetime:
    if last_fetch is None:
        return now - FIRST_RUN_LOOKBACK
    return last_fetch - FETCH_OVERLAP


def is_quiet(now: datetime) -> bool:
    return now.hour < QUIET_UNTIL_HOUR
