"""
Enums for the Shift Roster module.
Values match the Excel file's shift codes exactly.
"""
from enum import Enum


class ShiftCode(str, Enum):
    """Daily shift values as they appear in the Excel roster."""
    SHIFT1 = "Shift1"
    SHIFT2 = "Shift2"
    SHIFT3 = "Shift3"
    WEEK_OFF = "WO"           # Week Off
    PLANNED_LEAVE = "PL"      # Planned Leave
    RESTRICTED_HOLIDAY = "RH" # Restricted Holiday


class EngineerLevel(str, Enum):
    L1 = "L1"
    L2 = "L2"
    L3 = "L3"


class EngineerStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"  # removed engineer — keeps historical data


class UploadStatus(str, Enum):
    SUCCESS = "success"
    PARTIAL = "partial"   # some rows failed
    FAILED = "failed"


# ---------------------------------------------------------------------------
# Shift/leave code reference data — stored as a constant, not a DB table.
# Use SHIFT_DEFINITIONS anywhere you need labels, descriptions or working flag.
# ---------------------------------------------------------------------------
SHIFT_DEFINITIONS: dict[str, dict] = {
    "Shift1": {"label": "Shift 1",            "description": "12:30 PM IST - 09:30 PM IST", "is_working": True},
    "Shift2": {"label": "Shift 2",            "description": "10:00 AM IST - 07:30 PM IST", "is_working": True},
    "Shift3": {"label": "Shift 3",            "description": "08:00 AM EST - 05:00 PM EST", "is_working": True},
    "WO":     {"label": "Week Off",           "description": None,                           "is_working": False},
    "PL":     {"label": "Planned Leave",      "description": None,                           "is_working": False},
    "CH":     {"label": "Company Holiday",    "description": None,                           "is_working": False},
    "RH":     {"label": "Restricted Holiday", "description": None,                           "is_working": False},
}

WORKING_SHIFTS = {code for code, meta in SHIFT_DEFINITIONS.items() if meta["is_working"]}
NON_WORKING_CODES = {code for code, meta in SHIFT_DEFINITIONS.items() if not meta["is_working"]}
