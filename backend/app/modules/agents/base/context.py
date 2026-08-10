"""
Agent context utilities.

Helpers for extracting and validating data from AIContext
before passing to agent reasoning logic.
"""
from app.modules.context.schemas import AIContext, EngineerContext
from app.modules.shift_roster.enums import WORKING_SHIFTS


def get_available_engineers(context: AIContext) -> list[EngineerContext]:
    """Return only engineers currently on a working shift."""
    return [e for e in context.engineers if e.is_available]


def get_engineers_on_leave(context: AIContext) -> list[EngineerContext]:
    """Return engineers on WO, PL, CH, or RH."""
    return [e for e in context.engineers if not e.is_available]


def has_available_engineers(context: AIContext) -> bool:
    return any(e.is_available for e in context.engineers)


def get_engineers_by_level(context: AIContext, level: str) -> list[EngineerContext]:
    """Filter engineers by skill level e.g. L1, L2, L3."""
    return [e for e in context.engineers if e.level == level]
