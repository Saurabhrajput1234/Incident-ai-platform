"""
Enums for the IncidentWorkNote module.
"""
from enum import Enum


class WorkNoteSourceType(str, Enum):
    """Who/what created this work note."""
    ENGINEER = "ENGINEER"
    USER = "USER"
    TRIAGE_AGENT = "TRIAGE_AGENT"
    ACKNOWLEDGEMENT_AGENT = "ACKNOWLEDGEMENT_AGENT"
    PENDING_AGENT = "PENDING_AGENT"
    RESOLUTION_AGENT = "RESOLUTION_AGENT"
    SYSTEM = "SYSTEM"


class WorkNoteActionType(str, Enum):
    """What operation this work note records."""
    INCIDENT_CREATE = "INCIDENT_CREATE"
    INCIDENT_UPDATE = "INCIDENT_UPDATE"
    ASSIGN_ENGINEER = "ASSIGN_ENGINEER"
    STATE_CHANGE = "STATE_CHANGE"
    GROUP_RESOLVED = "GROUP_RESOLVED"
    SEND_ACKNOWLEDGEMENT = "SEND_ACKNOWLEDGEMENT"
    SEND_REMINDER = "SEND_REMINDER"
    MANUAL_NOTE = "MANUAL_NOTE"
    SYSTEM_NOTE = "SYSTEM_NOTE"
