"""
BaseNotificationProvider — abstract contract for all notification providers.

Rules
~~~~~
* Providers are responsible ONLY for delivery simulation / real delivery.
* Providers MUST NOT access the database.
* Providers MUST NOT write work notes.
* Providers MUST NOT contain agent-specific business logic.

A provider receives a NotificationRequest and returns a NotificationResult
that reflects the delivery outcome only.  Work-note persistence is the
responsibility of NotificationService (the layer above the provider).

To add a new provider (e.g. MicrosoftGraphProvider):
    1. Subclass BaseNotificationProvider.
    2. Implement send().
    3. Register the class in NotificationService._build_provider().
"""
from abc import ABC, abstractmethod

from app.integrations.notifications.schemas import (
    NotificationRequest,
    NotificationResult,
)


class BaseNotificationProvider(ABC):
    """
    Abstract base class for notification delivery providers.

    Each concrete provider must implement send() and expose a
    human-readable provider_name property.
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Unique, human-readable name of this provider (e.g. "simulator")."""
        ...

    @abstractmethod
    async def send(self, request: NotificationRequest) -> NotificationResult:
        """
        Deliver the notification described by *request*.

        Returns a NotificationResult reflecting the delivery outcome.
        Must never raise — all errors must be returned as a failed result.
        Must never write to the database.
        """
        ...
