"""
Enums for the PendingCycle module.
"""
from enum import Enum


class PendingCycleStatus(str, Enum):
    """
    Lifecycle status of a pending reminder cycle.

    ACTIVE    — Currently running cycle awaiting caller action or reminders
    COMPLETED — Resolved/closed or caller responded, cycle ended normally
    CANCELLED — Ticket moved out of pending state or manually aborted
    """
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
