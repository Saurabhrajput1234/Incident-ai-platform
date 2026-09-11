"""
Notification integration package.

Public surface:
    NotificationChannel   — EMAIL / TEAMS enum
    NotificationRequest   — typed send request
    NotificationResult    — typed send result
    BaseNotificationProvider — abstract provider contract
    SimulatorNotificationProvider — simulated delivery (no real I/O)
    NotificationService   — orchestrates provider + work-note persistence
"""
from app.integrations.notifications.schemas import (
    NotificationChannel,
    NotificationRequest,
    NotificationResult,
)
from app.integrations.notifications.base import BaseNotificationProvider
from app.integrations.notifications.simulator import SimulatorNotificationProvider
from app.integrations.notifications.service import NotificationService

__all__ = [
    "NotificationChannel",
    "NotificationRequest",
    "NotificationResult",
    "BaseNotificationProvider",
    "SimulatorNotificationProvider",
    "NotificationService",
]
