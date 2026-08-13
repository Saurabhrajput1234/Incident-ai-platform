"""
Shift Time Checker.

Determines whether a given shift code is currently active
based on the current real-world time and timezone.

Shift definitions (from SHIFT_DEFINITIONS):
  Shift1: 12:30 PM IST - 09:30 PM IST
  Shift2: 10:00 AM IST - 07:30 PM IST
  Shift3: 08:00 AM EST - 05:00 PM EST  (Eastern Standard Time)
  WO/PL/CH/RH: never active (non-working)

IST = UTC+5:30
EST = UTC-5:00

Note: Shift1 ends at 09:30 PM IST which is before midnight — no overnight crossing.
"""
import logging
from datetime import datetime, time
import pytz

logger = logging.getLogger(__name__)

IST = pytz.timezone("Asia/Kolkata")   # UTC+5:30
EST = pytz.timezone("US/Eastern")     # UTC-5:00 / UTC-4:00 (DST aware)

# Shift windows: (start_time, end_time, timezone)
# All times are in the shift's local timezone
SHIFT_WINDOWS: dict[str, tuple[time, time, pytz.BaseTzInfo]] = {
    "Shift1": (time(12, 30), time(21, 30), IST),   # 12:30 PM - 09:30 PM IST
    "Shift2": (time(10,  0), time(19, 30), IST),   # 10:00 AM - 07:30 PM IST
    "Shift3": (time( 8,  0), time(17,  0), EST),   # 08:00 AM - 05:00 PM EST
}


def is_shift_active_now(shift_code: str, now_utc: datetime | None = None) -> bool:
    """
    Returns True if the given shift code is currently active.

    Args:
        shift_code: e.g. "Shift1", "Shift2", "Shift3", "WO", "PL"
        now_utc: UTC datetime to check against (defaults to current UTC time)

    Returns:
        True if within the shift window, False otherwise.
    """
    if shift_code not in SHIFT_WINDOWS:
        # WO, PL, CH, RH — never active
        return False

    start, end, tz = SHIFT_WINDOWS[shift_code]

    if now_utc is None:
        now_utc = datetime.now(pytz.utc)

    # Convert current UTC time to the shift's local timezone
    now_local = now_utc.astimezone(tz)
    current_time = now_local.time().replace(second=0, microsecond=0)

    active = start <= current_time <= end

    logger.debug(
        f"Shift check: {shift_code} | "
        f"window={start.strftime('%H:%M')}-{end.strftime('%H:%M')} {tz.zone} | "
        f"now={current_time.strftime('%H:%M')} | active={active}"
    )
    return active


def get_active_shifts_now(now_utc: datetime | None = None) -> list[str]:
    """
    Returns all shift codes that are currently active.
    Typically returns 0 or 1 shift, but handles overlapping windows.
    """
    if now_utc is None:
        now_utc = datetime.now(pytz.utc)
    return [code for code in SHIFT_WINDOWS if is_shift_active_now(code, now_utc)]


def get_shift_status_summary(now_utc: datetime | None = None) -> dict:
    """
    Returns a summary of all shift statuses — useful for the AI health endpoint.
    """
    if now_utc is None:
        now_utc = datetime.now(pytz.utc)

    summary = {}
    for code, (start, end, tz) in SHIFT_WINDOWS.items():
        now_local = now_utc.astimezone(tz)
        summary[code] = {
            "active": is_shift_active_now(code, now_utc),
            "window": f"{start.strftime('%H:%M')} - {end.strftime('%H:%M')} {tz.zone}",
            "current_time_in_tz": now_local.strftime("%H:%M %Z"),
        }
    return summary
