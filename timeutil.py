"""Andar sab kuch UTC. India ke daily/weekly reset ke liye IST (Asia/Kolkata = UTC+5:30, DST nahi)."""
from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30), "IST")


def now_utc():
    return datetime.now(timezone.utc)


def today_ist(now=None):
    return (now or now_utc()).astimezone(IST).date()


def week_start_utc(now=None):
    """Is hafte (Monday 00:00 IST) ka start, UTC mein."""
    n = (now or now_utc()).astimezone(IST)
    monday = (n - timedelta(days=n.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    return monday.astimezone(timezone.utc)


def fmt_dt(dt):
    if dt is None:
        return "-"
    return dt.astimezone(IST).strftime("%d %b %Y, %I:%M %p IST")


def parse_expiry(text, now=None):
    """'0' -> None (kabhi expire nahi). 'YYYY-MM-DD' -> us din ke end (IST) tak valid."""
    t = (text or "").strip()
    if t == "0":
        return None
    try:
        d = datetime.strptime(t, "%Y-%m-%d")
    except ValueError:
        raise ValueError("Date format YYYY-MM-DD hona chahiye (jaise 2026-12-31) ya 0.")
    expiry = datetime(d.year, d.month, d.day, tzinfo=IST) + timedelta(days=1)
    if expiry <= (now or now_utc()):
        raise ValueError("Ye date nikal chuki hai.")
    return expiry
