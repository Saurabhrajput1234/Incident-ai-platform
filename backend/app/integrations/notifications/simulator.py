"""
SimulatorNotificationProvider — simulated delivery, no real I/O.

Behaviour
~~~~~~~~~
* Generates a unique SIM-<CHANNEL>-<UUID> message ID for every request.
* Returns delivery_status = "simulated_success" on the happy path.
* Supports EMAIL and TEAMS channels.
* Makes zero network calls.
* Is stateless — safe to instantiate multiple times.

This provider is active when NOTIFICATION_PROVIDER=simulator (the default).
When real credentials become available, swap it for MicrosoftGraphProvider
without touching any agent code.
"""
from __future__ import annotations

import logging
import uuid

from app.integrations.notifications.base import BaseNotificationProvider
from app.integrations.notifications.schemas import (
    NotificationChannel,
    NotificationRequest,
    NotificationResult,
)

logger = logging.getLogger(__name__)


class SimulatorNotificationProvider(BaseNotificationProvider):
    """
    Simulates email and Teams delivery.

    Every call returns a successful NotificationResult with a unique
    SIM-EMAIL-* or SIM-TEAMS-* message ID so that callers can trace
    individual notifications without touching a real provider.
    """

    @property
    def provider_name(self) -> str:
        return "simulator"

    async def send(self, request: NotificationRequest) -> NotificationResult:
        """
        Simulate delivery of *request*.

        The method never raises.  If the channel is not recognised it
        returns a failed result rather than raising an exception.
        """
        try:
            channel = NotificationChannel(request.channel)
        except ValueError:
            return NotificationResult.failure(
                channel=request.channel,
                error=f"Unknown notification channel: '{request.channel}'",
                recipient=request.recipients[0] if request.recipients else "",
                message=request.message,
            )

        # Pick the primary recipient for the result summary
        primary_recipient = request.recipients[0] if request.recipients else ""

        if channel == NotificationChannel.EMAIL:
            return self._simulate_email(request, primary_recipient)
        elif channel == NotificationChannel.TEAMS:
            return self._simulate_teams(request, primary_recipient)

        # Fallback — should not be reachable given the enum guard above
        return NotificationResult.failure(
            channel=channel,
            error=f"Unhandled channel: '{channel}'",
            recipient=primary_recipient,
            message=request.message,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _simulate_email(
        self, request: NotificationRequest, primary_recipient: str
    ) -> NotificationResult:
        message_id = f"SIM-EMAIL-{uuid.uuid4()}"
        logger.info(
            "[SimulatorProvider] EMAIL simulated | id=%s | to=%s | subject=%s",
            message_id,
            ", ".join(request.recipients),
            request.subject or "(no subject)",
        )
        return NotificationResult(
            success=True,
            channel=NotificationChannel.EMAIL.value,
            delivery_status="simulated_success",
            message_id=message_id,
            recipient=primary_recipient,
            subject=request.subject,
            message=request.message,
        )

    def _simulate_teams(
        self, request: NotificationRequest, primary_recipient: str
    ) -> NotificationResult:
        message_id = f"SIM-TEAMS-{uuid.uuid4()}"
        logger.info(
            "[SimulatorProvider] TEAMS simulated | id=%s | to=%s",
            message_id,
            ", ".join(request.recipients),
        )
        return NotificationResult(
            success=True,
            channel=NotificationChannel.TEAMS.value,
            delivery_status="simulated_success",
            message_id=message_id,
            recipient=primary_recipient,
            subject=None,   # Teams has no subject
            message=request.message,
        )
