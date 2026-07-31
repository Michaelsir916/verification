from datetime import datetime, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30), name="IST")


def now_utc_iso():
    """Raw UTC timestamp for storage (always store in this format)."""
    return datetime.now(timezone.utc).isoformat()


def now_utc_iso_plus_days(days):
    """UTC ISO timestamp `days` days from now (used for 7/30/90-day expiry options)."""
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


def parse_ist_to_utc_iso(text):
    """
    Parses a user-typed date/time (assumed IST) into a UTC ISO string for
    storage. Accepts "DD-MM-YYYY HH:MM" or just "DD-MM-YYYY" (defaults to
    23:59 that day). Returns None if the text can't be parsed.
    """
    text = text.strip()
    formats = ["%d-%m-%Y %H:%M", "%d-%m-%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d-%m-%Y"]
    for fmt in formats:
        try:
            dt = datetime.strptime(text, fmt)
            if fmt in ("%d-%m-%Y",):
                dt = dt.replace(hour=23, minute=59, second=59)
            dt = dt.replace(tzinfo=IST)
            return dt.astimezone(timezone.utc).isoformat()
        except ValueError:
            continue
    return None


def to_ist_dual(value):
    """
    Converts a stored UTC ISO string (or datetime) into a display string
    showing BOTH 24-hour and 12-hour time, in IST.
    Example: "02-07-2026 21:15:03 (24h) / 02-07-2026 09:15:03 PM (12h) IST"
    """
    if not value:
        return "Unknown"

    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value)
        except ValueError:
            return value  # not a parseable timestamp, show as-is
    else:
        dt = value

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    ist_dt = dt.astimezone(IST)
    fmt_24h = ist_dt.strftime("%d-%m-%Y %H:%M:%S")
    fmt_12h = ist_dt.strftime("%d-%m-%Y %I:%M:%S %p")
    return f"{fmt_24h} (24h) / {fmt_12h} (12h) IST"
