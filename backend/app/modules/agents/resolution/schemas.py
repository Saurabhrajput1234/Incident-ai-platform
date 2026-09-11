"""
Resolution Agent schemas.

Data contracts for the ON_HOLD → ACTIVE resolution workflow.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Trigger
# ---------------------------------------------------------------------------

class ResolutionTrigger(BaseModel):
    """
    State-transition metadata passed to the Resolution Agent.

    The agent processes ONLY transitions where:
        previous_state == "on_hold"  AND  current_state == "active"

    triggering_work_note_id
        ID of the specific work note that caused the ON_HOLD → ACTIVE
        transition.  ResolutionService uses it to load that exact note
        rather than calling get_latest() (which would return the SYSTEM
        STATE_CHANGE audit note written immediately after activation).
        None for manual engineer state changes.

    triggering_work_note_source
        WorkNoteSourceType value of the triggering note (e.g. "USER",
        "PENDING_AGENT", "SYSTEM").  Populated when the trigger comes from
        a work-note-driven activation; None for manual state changes.
        ResolutionService uses this to gate eligibility BEFORE loading the
        note — only "USER" source triggers Resolution analysis.
    """
    incident_id: str = Field(..., min_length=1)
    previous_state: str = Field(..., min_length=1)
    current_state: str = Field(..., min_length=1)
    triggering_work_note_id: str | None = Field(default=None)
    triggering_work_note_source: str | None = Field(default=None)


# ---------------------------------------------------------------------------
# Structured resolution intent
# ---------------------------------------------------------------------------

class ResolutionIntent(str, Enum):
    """
    Structured classification of the user's response intent.

    Only ISSUE_RESOLVED, REQUEST_COMPLETED, and REQUIRED_ACTION_COMPLETED
    are considered resolution-positive and may allow automatic closure.
    All other intents result in NO_ACTION.
    """
    ISSUE_RESOLVED          = "ISSUE_RESOLVED"           # "it's working now"
    REQUEST_COMPLETED       = "REQUEST_COMPLETED"         # "I submitted the RITM"
    REQUIRED_ACTION_COMPLETED = "REQUIRED_ACTION_COMPLETED"  # "I completed the steps"
    ACKNOWLEDGED_ONLY       = "ACKNOWLEDGED_ONLY"         # "Thanks, I'll check"
    ACTION_PENDING          = "ACTION_PENDING"            # "I'll do it tomorrow"
    MORE_INFORMATION_PROVIDED = "MORE_INFORMATION_PROVIDED"  # "Here are the logs"
    UNCLEAR                 = "UNCLEAR"                   # ambiguous response


# Intents that allow automatic resolution
RESOLUTION_POSITIVE_INTENTS = frozenset({
    ResolutionIntent.ISSUE_RESOLVED,
    ResolutionIntent.REQUEST_COMPLETED,
    ResolutionIntent.REQUIRED_ACTION_COMPLETED,
})


# ---------------------------------------------------------------------------
# LLM analysis
# ---------------------------------------------------------------------------

class LLMAnalysis(BaseModel):
    """
    Structured output returned by the LLM user-response analyser.

    Fields
    ------
    intent              : Structured classification of the user's response.
                          Only ISSUE_RESOLVED / REQUEST_COMPLETED /
                          REQUIRED_ACTION_COMPLETED allow auto-resolution.
    positive_resolution : Convenience bool — True when intent is in
                          RESOLUTION_POSITIVE_INTENTS.  Derived from intent
                          at construction time; kept for backward compat.
    confidence          : 0.0–1.0 confidence score.
    summary             : Short plain-text summary of the user's response.
    next_best_action    : Recommended next action for the engineer/team.
    """
    intent: ResolutionIntent = ResolutionIntent.UNCLEAR
    positive_resolution: bool = False
    confidence: float = Field(ge=0.0, le=1.0)
    summary: str
    next_best_action: str


# ---------------------------------------------------------------------------
# Notification outcome summary
# ---------------------------------------------------------------------------

class NotificationOutcome(BaseModel):
    """Summary of a single notification channel attempt."""
    channel: str
    success: bool
    recipient: str
    message_id: str | None = None
    work_note_id: str | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# Resolution action taken
# ---------------------------------------------------------------------------

class ResolutionAction(str, Enum):
    """Final action performed by the Resolution Agent."""
    AUTO_RESOLVED  = "auto_resolved"      # incident moved to resolved/closed
    NOTIFIED       = "notified"           # engineer/group notified, no state change
    IGNORED        = "ignored"            # trigger or work-note criteria not met
    NO_ACTION      = "no_action"          # safe fallback when missing data
    FAILED         = "failed"             # unexpected error


# ---------------------------------------------------------------------------
# Agent result
# ---------------------------------------------------------------------------

class ResolutionResult(BaseModel):
    """
    Complete structured result returned by ResolutionService.

    This is stored in AgentResponse.result and doubles as the audit record.
    """
    # ---- Input context ----
    incident_id: str
    incident_number: str
    previous_state: str
    current_state: str

    # ---- Trigger decision ----
    trigger_eligible: bool
    trigger_reason: str

    # ---- Work note check ----
    latest_work_note_source: str | None = None
    work_note_eligible: bool = False

    # ---- Pending cycle ----
    pending_cycle_cancelled: bool = False
    pending_cycle_id: str | None = None

    # ---- LLM analysis ----
    llm_analysis: LLMAnalysis | None = None
    llm_failed: bool = False
    llm_error: str | None = None

    # ---- Provenance ----
    provenance_eligible: bool = False
    provenance_reason: str = ""

    # ---- Notifications ----
    notifications: list[NotificationOutcome] = Field(default_factory=list)

    # ---- Final action ----
    action: ResolutionAction = ResolutionAction.NO_ACTION
    action_reason: str = ""

    # ---- Timestamps ----
    processed_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
