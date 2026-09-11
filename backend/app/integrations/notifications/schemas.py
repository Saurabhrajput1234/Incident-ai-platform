"""
Notification request and result schemas.

These are the shared data contracts between:
  - Agents / callers  →  NotificationService  →  Provider

Design rules
~~~~~~~~~~~~
* Completely generic — no agent-specific logic lives here.
* The caller (agent/service) supplies source_type and action_type so that
  the work note written by NotificationService carries the right context.
* subject is optional: it applies to EMAIL, not to TEAMS.
* recipients is a list so that a single request can address multiple
  addresses/channels (e.g. all engineers in a group).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Channel enum
# ---------------------------------------------------------------------------

class NotificationChannel(str, Enum):
    """Supported notification channels."""
    EMAIL = "email"
    TEAMS = "teams"


# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------

class NotificationRequest(BaseModel):
    """
    A single notification to be delivered through one channel.

    Fields
    ------
    incident_id   : UUID of the incident this notification concerns.
    channel       : EMAIL or TEAMS.
    recipients    : One or more addresses / aliases / channel names.
    subject       : Email subject line (ignored for TEAMS).
    message       : The exact body / message text to deliver.
    source_name   : Human-readable name of the calling agent or service,
                    e.g. "PendingReminderAgent".  Stored in the work note
                    source_name column.
    source_type   : WorkNoteSourceType value — supplied by the caller so
                    that work notes are attributed correctly.
    action_type   : WorkNoteActionType value — optional, supplied by the
                    caller (e.g. SEND_REMINDER, SEND_ACKNOWLEDGEMENT).
    source_id     : Optional opaque identifier for the originating entity
                    (e.g. agent run-id, engineer UUID).  Stored in the
                    work note source_id column.
    """
    incident_id: str = Field(..., min_length=1)
    channel: NotificationChannel
    recipients: list[str] = Field(..., min_length=1)
    subject: str | None = Field(default=None)
    message: str = Field(..., min_length=1)
    source_name: str = Field(..., min_length=1, max_length=200)
    source_type: str = Field(..., min_length=1)   # WorkNoteSourceType value
    action_type: str | None = Field(default=None)  # WorkNoteActionType value
    source_id: str | None = Field(default=None)

    model_config = {"use_enum_values": True}


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------

class NotificationResult(BaseModel):
    """
    Structured outcome of a single notification attempt.

    Fields
    ------
    success         : True only when BOTH delivery and work-note recording
                      succeeded.
    channel         : Channel that was used.
    delivery_status : Provider-specific status string, e.g.
                      "simulated_success" or "failed".
    message_id      : Unique identifier for this notification event.  For
                      the simulator this is a generated SIM-* ID.  For a
                      real provider it would be the provider's message ID.
    recipient       : The primary/first recipient used.
    subject         : Echoed back from the request (None for TEAMS).
    message         : The exact body/message that was sent.
    work_note_id    : UUID of the work note row created in the DB.  None if
                      work-note recording failed or was not attempted.
    error           : Human-readable failure description (None on success).
    timestamp       : UTC timestamp of the result.
    """
    success: bool
    channel: str
    delivery_status: str
    message_id: str
    recipient: str
    subject: str | None = None
    message: str
    work_note_id: str | None = None
    error: str | None = None
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    @classmethod
    def failure(
        cls,
        *,
        channel: NotificationChannel | str,
        error: str,
        message_id: str | None = None,
        recipient: str = "",
        message: str = "",
    ) -> "NotificationResult":
        """Convenience constructor for a failed result."""
        return cls(
            success=False,
            channel=str(channel) if isinstance(channel, NotificationChannel) else channel,
            delivery_status="failed",
            message_id=message_id or f"SIM-FAIL-{uuid.uuid4()}",
            recipient=recipient,
            message=message,
            error=error,
        )
