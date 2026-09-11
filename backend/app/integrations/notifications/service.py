"""
NotificationService — orchestrates provider + work-note persistence.

Responsibilities
~~~~~~~~~~~~~~~~
* Select the correct provider based on configuration.
* Call the provider to simulate / deliver the notification.
* On provider success: record the notification as an incident work note
  using WorkNoteService so that every notification is auditable.
* Return a NotificationResult that reflects BOTH outcomes:
    - success=True  only when delivery AND work-note recording both succeed.
    - success=False when either step fails, with a descriptive error.

What this service does NOT do
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
* It does NOT decide whether to send a notification (that is the agent's job).
* It does NOT decide who the recipient is (the caller supplies recipients).
* It does NOT contain any agent-specific business logic.
* It does NOT directly access the database — that is WorkNoteService's job.

Work-note format
~~~~~~~~~~~~~~~~
The work note message preserves the full communication so that the exact
content sent to the recipient is always recoverable from the incident
history.  Format (human-readable, no proprietary encoding):

    [<CHANNEL>] Notification sent via <provider>
    Message-ID : <message_id>
    Recipient(s): <recipients>
    Subject    : <subject>          ← omitted for TEAMS
    ---
    <message body>
"""
from __future__ import annotations

import logging
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.integrations.notifications.base import BaseNotificationProvider
from app.integrations.notifications.schemas import (
    NotificationChannel,
    NotificationRequest,
    NotificationResult,
)
from app.integrations.notifications.simulator import SimulatorNotificationProvider
from app.modules.work_notes.service import WorkNoteService
from app.modules.work_notes.enums import WorkNoteSourceType, WorkNoteActionType

logger = logging.getLogger(__name__)


class NotificationService:
    """
    Orchestrates notification delivery and work-note persistence.

    Usage (inside an agent service)::

        notif_svc = NotificationService(db)
        result = await notif_svc.send(NotificationRequest(
            incident_id=incident.id,
            channel=NotificationChannel.EMAIL,
            recipients=[incident.caller_email],
            subject="Reminder: please confirm your ticket is resolved",
            message="Hi ...",
            source_name="PendingReminderAgent",
            source_type=WorkNoteSourceType.PENDING_AGENT.value,
            action_type=WorkNoteActionType.SEND_REMINDER.value,
        ))
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._work_note_svc = WorkNoteService(db)
        self._provider: BaseNotificationProvider = self._build_provider()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def send(self, request: NotificationRequest) -> NotificationResult:
        """
        Send a notification and record it as a work note.

        Steps
        -----
        1. Delegate delivery to the configured provider.
        2. If delivery fails → return failed result immediately (no work note).
        3. If delivery succeeds → write a work note via WorkNoteService.
        4. If work-note recording fails → return failed result so the caller
           knows the audit trail is incomplete.
        5. Return the final result with work_note_id attached.
        """
        # Step 1 — Deliver (or simulate)
        try:
            delivery_result = await self._provider.send(request)
        except Exception as exc:  # providers must not raise, but be safe
            logger.error(
                "[NotificationService] Provider raised unexpectedly: %s", exc
            )
            return NotificationResult.failure(
                channel=request.channel,
                error=f"Provider error: {exc}",
                recipient=request.recipients[0] if request.recipients else "",
                message=request.message,
            )

        # Step 2 — Bail early on delivery failure
        if not delivery_result.success:
            logger.warning(
                "[NotificationService] Delivery failed for incident %s: %s",
                request.incident_id,
                delivery_result.error,
            )
            return delivery_result

        # Step 3 — Persist work note
        try:
            note_message = self._build_work_note_message(request, delivery_result)
            work_note = await self._work_note_svc.add_note(
                incident_id=request.incident_id,
                message=note_message,
                source_type=WorkNoteSourceType(request.source_type),
                source_name=request.source_name,
                source_id=request.source_id,
                action_type=(
                    WorkNoteActionType(request.action_type)
                    if request.action_type
                    else None
                ),
                auto_activate=False,  # notification work notes are audit trail only
            )
            logger.info(
                "[NotificationService] Work note %s created for incident %s",
                work_note.id,
                request.incident_id,
            )
            delivery_result.work_note_id = work_note.id
            return delivery_result

        except Exception as exc:
            # Step 4 — Work-note failure → report as overall failure
            logger.error(
                "[NotificationService] Work note failed for incident %s: %s",
                request.incident_id,
                exc,
            )
            return NotificationResult(
                success=False,
                channel=delivery_result.channel,
                delivery_status=delivery_result.delivery_status,
                message_id=delivery_result.message_id,
                recipient=delivery_result.recipient,
                subject=delivery_result.subject,
                message=delivery_result.message,
                work_note_id=None,
                error=f"Work note recording failed: {exc}",
            )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_provider() -> BaseNotificationProvider:
        """
        Instantiate the configured notification provider.

        Currently only 'simulator' is supported.  When real providers are
        added, extend this method with additional elif branches — no other
        code needs to change.
        """
        provider_name = settings.NOTIFICATION_PROVIDER.lower()
        if provider_name == "simulator":
            return SimulatorNotificationProvider()
        # Future: elif provider_name == "microsoft_graph": return MicrosoftGraphProvider()
        logger.warning(
            "[NotificationService] Unknown provider '%s', falling back to simulator.",
            provider_name,
        )
        return SimulatorNotificationProvider()

    @staticmethod
    def _build_work_note_message(
        request: NotificationRequest,
        result: NotificationResult,
    ) -> str:
        """
        Build a human-readable work note that preserves the full communication.

        The note is structured so that the exact content sent to the recipient
        is always recoverable from the incident work-note history.
        """
        channel_label = request.channel.upper() if isinstance(request.channel, str) \
            else request.channel.value.upper()

        recipients_str = ", ".join(request.recipients)

        lines = [
            f"[{channel_label}] Notification sent via {result.message_id}",
            f"Source     : {request.source_name}",
            f"Recipient(s): {recipients_str}",
        ]

        if request.subject:
            lines.append(f"Subject    : {request.subject}")

        lines.append("---")
        lines.append(request.message)

        return "\n".join(lines)
