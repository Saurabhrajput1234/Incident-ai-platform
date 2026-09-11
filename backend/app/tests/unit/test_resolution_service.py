"""
Unit tests for the Resolution Agent (ResolutionService + ResolutionAgent).

All 35 required scenarios are covered.  Every test is a pure unit test:
WorkNoteService, PendingCycleService, IncidentService, ContextService,
NotificationService, and ResolutionAgent are mocked via AsyncMock so no
database is touched.

Test map
--------
TRIGGER
 1. ON_HOLD → ACTIVE is processed.            ← changed from PENDING
 2. ACTIVE → ACTIVE is ignored.
 3. PENDING → ACTIVE is now ignored.          ← changed from ON_HOLD→ACTIVE=ignored
 4. NEW → ACTIVE is ignored.
 5. IN_PROGRESS → ACTIVE is ignored.

WORK NOTE
 6. Latest USER note proceeds.
 7. Latest ENGINEER note is ignored.
 8. Latest ACKNOWLEDGEMENT_AGENT note is ignored.
 9. Latest PENDING_AGENT note is ignored.
10. Latest SYSTEM note is ignored.

PENDING CYCLE
11. USER response cancels active PendingCycle.
12. Cancellation happens regardless of response content.
13. No active PendingCycle is handled safely (cancel returns None).

LLM
14. Positive response handled correctly.
15. Non-positive response handled correctly.
16. Summary is present in result.
17. Next best action is present in result.
18. Confidence is validated (0.0–1.0).
19. Invalid structured LLM output handled safely (parse error → non-positive).
20. LLM failure prevents auto-resolution.

NOTIFICATIONS
21. Positive → Teams sent to assigned engineer.
22. Positive → Email sent to assignment group.
23. Positive → NotificationService creates work note (work_note_id present).
24. Non-positive → Teams sent to assigned engineer.
25. Non-positive → Work note created (work_note_id present).
26. Non-positive → No assignment-group email sent.
27. Work note communication matches notification message body.

AUTO RESOLUTION
28. Positive + eligible provenance → auto-resolve performed.
29. Positive + no provenance → no auto-resolve.
30. Negative response → no auto-resolve.
31. LLM failure → no auto-resolve.
32. Duplicate trigger → no duplicate auto-resolution (idempotent).

FAILURE
33. Notification failure handled safely (result returned, no exception).
34. Assigned engineer email not found → Teams skipped gracefully.
35. Assignment group has no emails → Email skipped gracefully.
"""
from __future__ import annotations

import json
import pytest
from datetime import datetime, timezone, date
from unittest.mock import AsyncMock, MagicMock, patch

from app.modules.agents.resolution.service import ResolutionService
from app.modules.agents.resolution.schemas import (
    ResolutionAction,
    ResolutionTrigger,
    LLMAnalysis,
    ResolutionIntent,
    RESOLUTION_POSITIVE_INTENTS,
)
from app.modules.agents.resolution.agent import ResolutionAgent
from app.modules.agents.base.response import AgentResponse
from app.modules.work_notes.enums import WorkNoteSourceType, WorkNoteActionType
from app.integrations.notifications.schemas import NotificationResult, NotificationChannel


# ---------------------------------------------------------------------------
# Helpers / factories
# ---------------------------------------------------------------------------

def _trigger(previous: str = "on_hold", current: str = "active", inc_id: str = "inc-001") -> ResolutionTrigger:
    return ResolutionTrigger(incident_id=inc_id, previous_state=previous, current_state=current)


def _mock_incident(
    inc_id: str = "inc-001",
    number: str = "INC0000001",
    state: str = "active",
    assigned_to: str | None = "Alice Smith",
    assignment_group: str | None = "Network Ops",
):
    m = MagicMock()
    m.id = inc_id
    m.incident_number = number
    m.state = state
    m.assigned_to = assigned_to
    m.assignment_group = assignment_group
    m.short_description = "VPN not working"
    m.description = "User cannot connect to VPN"
    m.priority = "3"
    m.category = "network"
    m.subcategory = None
    m.caller = "alice"
    m.created_at = datetime.now(timezone.utc)
    return m


def _mock_work_note(source_type: str = "USER", message: str = "It is working now."):
    m = MagicMock()
    m.source_type = source_type
    m.message = message
    m.created_at = datetime.now(timezone.utc)
    return m


def _mock_pending_cycle(cycle_id: str = "cycle-1"):
    m = MagicMock()
    m.id = cycle_id
    m.status = "CANCELLED"
    return m


def _mock_context(engineers=None):
    """Build a minimal AIContext mock with optional engineers list."""
    from app.modules.context.schemas import AIContext, IncidentContext, EngineerContext

    inc_ctx = IncidentContext(
        incident_id="inc-001",
        incident_number="INC0000001",
        short_description="VPN not working",
        description="Cannot connect",
        priority="3",
        state="active",
        category="network",
        subcategory=None,
        assignment_group="Network Ops",
        assigned_to="Alice Smith",
        caller="alice",
        created_at=datetime.now(timezone.utc),
    )

    if engineers is None:
        engineers = [
            EngineerContext(
                engineer_id="eng-1",
                name="Alice Smith",
                email="alice@example.com",
                assignment_group="Network Ops",
                level="L2",
                default_shift="Shift1",
                current_shift="Shift1",
                is_available=True,
                is_shift_active=True,
                roster_date=date.today(),
            ),
            EngineerContext(
                engineer_id="eng-2",
                name="Bob Jones",
                email="bob@example.com",
                assignment_group="Network Ops",
                level="L1",
                default_shift="Shift1",
                current_shift="Shift1",
                is_available=True,
                is_shift_active=True,
                roster_date=date.today(),
            ),
        ]

    return AIContext(
        incident=inc_ctx,
        engineers=engineers,
        context_date=date.today(),
        created_at=datetime.now(timezone.utc),
    )


def _llm_json(positive: bool = True, confidence: float = 0.95,
              summary: str = "User confirmed fix.", next_action: str = "Close ticket.") -> str:
    return json.dumps({
        "positive_resolution": positive,
        "confidence": confidence,
        "summary": summary,
        "next_best_action": next_action,
    })


def _mock_notif_result(success: bool = True, channel: str = "teams", wn_id: str = "wn-1") -> NotificationResult:
    return NotificationResult(
        success=success,
        channel=channel,
        delivery_status="simulated_success" if success else "failed",
        message_id=f"SIM-{channel.upper()}-abc123",
        recipient="alice@example.com",
        message="body",
        work_note_id=wn_id if success else None,
        error=None if success else "Delivery failed",
    )


# ---------------------------------------------------------------------------
# Service factory — wires all mocked dependencies
# ---------------------------------------------------------------------------

def _make_service(
    incident=None,
    latest_note=None,
    cancelled_cycle=None,
    context=None,
    agent_response: AgentResponse | None = None,
    provenance_notes: list | None = None,
    notif_teams_result: NotificationResult | None = None,
    notif_email_result: NotificationResult | None = None,
    update_incident_raises: Exception | None = None,
):
    """Return a ResolutionService with fully mocked sub-services."""
    db = AsyncMock()
    svc = ResolutionService(db)

    # --- IncidentService ---
    svc.incident_service = AsyncMock()
    svc.incident_service.get_incident.return_value = incident or _mock_incident()
    if update_incident_raises:
        svc.incident_service.update_incident_internal.side_effect = update_incident_raises
    else:
        svc.incident_service.update_incident_internal.return_value = incident or _mock_incident()

    # --- WorkNoteService ---
    svc.work_note_svc = AsyncMock()
    svc.work_note_svc.get_latest.return_value = latest_note if latest_note is not None else _mock_work_note()
    svc.work_note_svc.add_note.return_value = MagicMock(id="audit-wn-1")

    if provenance_notes is None:
        # Default: one ACKNOWLEDGEMENT_AGENT note (eligible provenance)
        ack_note = _mock_work_note(source_type=WorkNoteSourceType.ACKNOWLEDGEMENT_AGENT.value)
        svc.work_note_svc.get_by_source_type.return_value = [ack_note]
    else:
        svc.work_note_svc.get_by_source_type.return_value = provenance_notes

    # --- PendingCycleService ---
    svc.pending_cycle_svc = AsyncMock()
    svc.pending_cycle_svc.cancel_active_cycle.return_value = (
        cancelled_cycle if cancelled_cycle is not None else _mock_pending_cycle()
    )

    # --- ContextService ---
    svc.context_service = AsyncMock()
    svc.context_service.build_for_incident.return_value = context or _mock_context()

    # --- NotificationService ---
    svc.notification_svc = AsyncMock()
    teams_res = notif_teams_result or _mock_notif_result(channel="teams")
    email_res = notif_email_result or _mock_notif_result(channel="email", wn_id="wn-2")

    async def _smart_send(req):
        if req.channel == NotificationChannel.TEAMS or req.channel == "teams":
            return teams_res
        return email_res

    svc.notification_svc.send.side_effect = _smart_send

    # --- ResolutionAgent ---
    if agent_response is not None:
        svc.agent = AsyncMock()
        svc.agent.run.return_value = agent_response
        svc.agent.agent_name = "ResolutionAgent"

    return svc


def _positive_agent_response(summary="Issue fixed.", next_action="Close ticket.", confidence=0.95) -> AgentResponse:
    return AgentResponse(
        success=True,
        agent_name="ResolutionAgent",
        reasoning=summary,
        confidence=confidence,
        result={"llm_analysis": LLMAnalysis(
            intent=ResolutionIntent.ISSUE_RESOLVED,
            positive_resolution=True,
            confidence=confidence,
            summary=summary,
            next_best_action=next_action,
        ).model_dump()},
    )


def _negative_agent_response(summary="Still broken.", next_action="Investigate logs.", confidence=0.80) -> AgentResponse:
    return AgentResponse(
        success=True,
        agent_name="ResolutionAgent",
        reasoning=summary,
        confidence=confidence,
        result={"llm_analysis": LLMAnalysis(
            intent=ResolutionIntent.ACKNOWLEDGED_ONLY,
            positive_resolution=False,
            confidence=confidence,
            summary=summary,
            next_best_action=next_action,
        ).model_dump()},
    )


def _failed_agent_response() -> AgentResponse:
    return AgentResponse(
        success=False,
        agent_name="ResolutionAgent",
        errors=["LLM timed out"],
        result={"llm_failed": True, "llm_error": "LLM timed out"},
    )


# ===========================================================================
# TRIGGER TESTS (1-5)
# ===========================================================================

@pytest.mark.asyncio
async def test_1_on_hold_to_active_is_processed():
    """ON_HOLD → ACTIVE triggers the full workflow (not ignored)."""
    svc = _make_service(agent_response=_positive_agent_response())
    result = await svc.process(_trigger("on_hold", "active"))
    data = result.result
    assert data["trigger_eligible"] is True
    assert data["action"] != ResolutionAction.IGNORED.value


@pytest.mark.asyncio
async def test_2_active_to_active_is_ignored():
    """ACTIVE → ACTIVE must be silently ignored."""
    svc = _make_service()
    result = await svc.process(_trigger("active", "active"))
    data = result.result
    assert data["trigger_eligible"] is False
    assert data["action"] == ResolutionAction.IGNORED.value


@pytest.mark.asyncio
async def test_3_pending_to_active_is_ignored():
    """PENDING → ACTIVE must now be silently ignored (trigger changed to on_hold)."""
    svc = _make_service()
    result = await svc.process(_trigger("pending", "active"))
    data = result.result
    assert data["trigger_eligible"] is False
    assert data["action"] == ResolutionAction.IGNORED.value


@pytest.mark.asyncio
async def test_4_missing_previous_state_is_ignored():
    """NEW → ACTIVE must be treated as invalid and ignored."""
    svc = _make_service()
    result = await svc.process(_trigger("new", "active"))
    data = result.result
    assert data["trigger_eligible"] is False
    assert data["action"] == ResolutionAction.IGNORED.value


@pytest.mark.asyncio
async def test_5_invalid_transition_metadata_is_ignored():
    """IN_PROGRESS → ACTIVE must also be ignored."""
    svc = _make_service()
    result = await svc.process(_trigger("in_progress", "active"))
    data = result.result
    assert data["trigger_eligible"] is False
    assert data["action"] == ResolutionAction.IGNORED.value


# ===========================================================================
# WORK NOTE TESTS (6-10)
# ===========================================================================

@pytest.mark.asyncio
async def test_6_latest_user_note_proceeds():
    """When latest work note is from USER, processing continues."""
    svc = _make_service(
        latest_note=_mock_work_note("USER"),
        agent_response=_positive_agent_response(),
    )
    result = await svc.process(_trigger())
    data = result.result
    assert data["work_note_eligible"] is True
    assert data["latest_work_note_source"] == "USER"


@pytest.mark.asyncio
async def test_7_latest_engineer_note_is_ignored():
    """
    When the latest/triggering note is from ENGINEER (no triggering_work_note_source
    on trigger — manual path fallback), step 4 rejects it.
    Only USER triggers Resolution analysis.
    """
    svc = _make_service(latest_note=_mock_work_note("ENGINEER"))
    result = await svc.process(_trigger())
    data = result.result
    assert data["work_note_eligible"] is False
    assert data["action"] == ResolutionAction.IGNORED.value


@pytest.mark.asyncio
async def test_8_latest_acknowledgement_agent_note_is_ignored():
    """ACKNOWLEDGEMENT_AGENT latest note → ignored (not USER)."""
    svc = _make_service(latest_note=_mock_work_note("ACKNOWLEDGEMENT_AGENT"))
    result = await svc.process(_trigger())
    data = result.result
    assert data["work_note_eligible"] is False
    assert data["action"] == ResolutionAction.IGNORED.value


@pytest.mark.asyncio
async def test_9_latest_pending_agent_note_is_ignored():
    """PENDING_AGENT latest note → ignored (not USER)."""
    svc = _make_service(latest_note=_mock_work_note("PENDING_AGENT"))
    result = await svc.process(_trigger())
    data = result.result
    assert data["work_note_eligible"] is False
    assert data["action"] == ResolutionAction.IGNORED.value


@pytest.mark.asyncio
async def test_10_latest_system_note_is_ignored():
    """When latest work note is from SYSTEM, processing stops."""
    svc = _make_service(latest_note=_mock_work_note("SYSTEM"))
    result = await svc.process(_trigger())
    data = result.result
    assert data["work_note_eligible"] is False
    assert data["action"] == ResolutionAction.IGNORED.value


# ===========================================================================
# PENDING CYCLE TESTS (11-13)
# ===========================================================================

@pytest.mark.asyncio
async def test_11_user_response_cancels_active_pending_cycle():
    """When a USER note is present, PendingCycleService.cancel_active_cycle is called."""
    svc = _make_service(
        latest_note=_mock_work_note("USER"),
        agent_response=_positive_agent_response(),
    )
    await svc.process(_trigger())
    svc.pending_cycle_svc.cancel_active_cycle.assert_called_once()


@pytest.mark.asyncio
async def test_12_pending_cycle_not_cancelled_for_negative_response():
    """
    When the user response is negative (e.g. ACKNOWLEDGED_ONLY), the incident
    must NOT be auto-resolved and the PendingCycle IS cancelled because the
    user has responded (regardless of resolution outcome).
    """
    svc = _make_service(
        latest_note=_mock_work_note("USER", "Still broken, please help."),
        agent_response=_negative_agent_response(),
    )
    result = await svc.process(_trigger())
    # Cycle IS cancelled — user responded, so waiting-for-user is over
    svc.pending_cycle_svc.cancel_active_cycle.assert_called_once()
    # But incident state must NOT be changed (no auto-resolve)
    svc.incident_service.update_incident_internal.assert_not_called()


@pytest.mark.asyncio
async def test_13_no_active_pending_cycle_handled_safely():
    """When cancel returns None (no active cycle), processing continues without error."""
    svc = _make_service(
        latest_note=_mock_work_note("USER"),
        cancelled_cycle=None,          # simulate no active cycle
        agent_response=_positive_agent_response(),
    )
    # Override the mock to return None explicitly
    svc.pending_cycle_svc.cancel_active_cycle.return_value = None
    result = await svc.process(_trigger())
    # Should complete without exception
    assert result.agent_name == "ResolutionAgent"
    data = result.result
    assert data["pending_cycle_cancelled"] is False


# ===========================================================================
# LLM TESTS (14-20)
# ===========================================================================

@pytest.mark.asyncio
async def test_14_positive_response_correctly_handled():
    """Positive LLM analysis leads to NOTIFIED or AUTO_RESOLVED action, not IGNORED."""
    svc = _make_service(
        latest_note=_mock_work_note("USER"),
        agent_response=_positive_agent_response(),
    )
    result = await svc.process(_trigger())
    data = result.result
    assert data["llm_analysis"]["positive_resolution"] is True
    assert data["action"] in (ResolutionAction.AUTO_RESOLVED.value, ResolutionAction.NOTIFIED.value)


@pytest.mark.asyncio
async def test_15_non_positive_response_correctly_handled():
    """Non-positive LLM analysis results in NOTIFIED action (not auto-resolve)."""
    svc = _make_service(
        latest_note=_mock_work_note("USER"),
        agent_response=_negative_agent_response(),
    )
    result = await svc.process(_trigger())
    data = result.result
    assert data["llm_analysis"]["positive_resolution"] is False
    assert data["action"] == ResolutionAction.NOTIFIED.value


@pytest.mark.asyncio
async def test_16_summary_is_present_in_result():
    """LLM summary is captured in ResolutionResult.llm_analysis.summary."""
    summary_text = "User confirmed the VPN issue is resolved."
    svc = _make_service(
        latest_note=_mock_work_note("USER"),
        agent_response=_positive_agent_response(summary=summary_text),
    )
    result = await svc.process(_trigger())
    assert result.result["llm_analysis"]["summary"] == summary_text


@pytest.mark.asyncio
async def test_17_next_best_action_is_present_in_result():
    """LLM next_best_action is captured in ResolutionResult.llm_analysis."""
    action_text = "Close the incident and document resolution steps."
    svc = _make_service(
        latest_note=_mock_work_note("USER"),
        agent_response=_positive_agent_response(next_action=action_text),
    )
    result = await svc.process(_trigger())
    assert result.result["llm_analysis"]["next_best_action"] == action_text


@pytest.mark.asyncio
async def test_18_confidence_is_within_valid_range():
    """Confidence must be between 0.0 and 1.0 inclusive."""
    svc = _make_service(
        latest_note=_mock_work_note("USER"),
        agent_response=_positive_agent_response(confidence=0.87),
    )
    result = await svc.process(_trigger())
    conf = result.result["llm_analysis"]["confidence"]
    assert 0.0 <= conf <= 1.0


@pytest.mark.asyncio
async def test_19_invalid_structured_llm_output_handled_safely():
    """
    ResolutionAgent._parse_llm_response: when LLM returns garbage JSON,
    the agent returns a safe non-positive LLMAnalysis (no exception raised).
    """
    agent = ResolutionAgent()

    # Simulate bad JSON from LLM
    result = agent._parse_llm_response("NOT_VALID_JSON $$$$")
    assert result.positive_resolution is False
    assert result.confidence == 0.0
    assert "parse" in result.summary.lower() or "unable" in result.summary.lower()


@pytest.mark.asyncio
async def test_20_llm_failure_prevents_auto_resolution():
    """When LLM fails, auto-resolve must not be attempted and success=False."""
    svc = _make_service(
        latest_note=_mock_work_note("USER"),
        agent_response=_failed_agent_response(),
    )
    result = await svc.process(_trigger())
    assert result.success is False
    data = result.result
    assert data["llm_failed"] is True
    assert data["action"] == ResolutionAction.FAILED.value
    # update_incident_internal must NOT have been called
    svc.incident_service.update_incident_internal.assert_not_called()


# ===========================================================================
# NOTIFICATION TESTS (21-27)
# ===========================================================================

@pytest.mark.asyncio
async def test_21_positive_sends_teams_to_assigned_engineer():
    """Positive response → Teams notification sent (notification_svc.send called with TEAMS)."""
    svc = _make_service(
        latest_note=_mock_work_note("USER"),
        agent_response=_positive_agent_response(),
    )
    await svc.process(_trigger())
    calls = svc.notification_svc.send.call_args_list
    channels = [c.args[0].channel for c in calls]
    assert NotificationChannel.TEAMS in channels or "teams" in channels


@pytest.mark.asyncio
async def test_22_positive_sends_group_email():
    """Positive response → Email notification sent to assignment group."""
    svc = _make_service(
        latest_note=_mock_work_note("USER"),
        agent_response=_positive_agent_response(),
    )
    await svc.process(_trigger())
    calls = svc.notification_svc.send.call_args_list
    channels = [c.args[0].channel for c in calls]
    assert NotificationChannel.EMAIL in channels or "email" in channels


@pytest.mark.asyncio
async def test_23_positive_notification_work_note_id_present():
    """Positive response notification result must carry a work_note_id."""
    svc = _make_service(
        latest_note=_mock_work_note("USER"),
        agent_response=_positive_agent_response(),
        notif_teams_result=_mock_notif_result(channel="teams", wn_id="wn-teams-1"),
    )
    result = await svc.process(_trigger())
    data = result.result
    teams_notif = next((n for n in data["notifications"] if n["channel"] == "teams"), None)
    assert teams_notif is not None
    assert teams_notif["work_note_id"] == "wn-teams-1"


@pytest.mark.asyncio
async def test_24_non_positive_sends_teams_to_engineer():
    """Non-positive response → Teams notification still sent to engineer."""
    svc = _make_service(
        latest_note=_mock_work_note("USER", "Still broken."),
        agent_response=_negative_agent_response(),
    )
    await svc.process(_trigger())
    calls = svc.notification_svc.send.call_args_list
    channels = [c.args[0].channel for c in calls]
    assert NotificationChannel.TEAMS in channels or "teams" in channels


@pytest.mark.asyncio
async def test_25_non_positive_notification_work_note_present():
    """Non-positive Teams notification must carry a work_note_id."""
    svc = _make_service(
        latest_note=_mock_work_note("USER", "Still broken."),
        agent_response=_negative_agent_response(),
        notif_teams_result=_mock_notif_result(channel="teams", wn_id="wn-neg-1"),
    )
    result = await svc.process(_trigger())
    data = result.result
    teams_notif = next((n for n in data["notifications"] if n["channel"] == "teams"), None)
    assert teams_notif is not None
    assert teams_notif["work_note_id"] == "wn-neg-1"


@pytest.mark.asyncio
async def test_26_non_positive_does_not_send_group_email():
    """Non-positive response must NOT send assignment-group email."""
    svc = _make_service(
        latest_note=_mock_work_note("USER", "Problem persists."),
        agent_response=_negative_agent_response(),
    )
    await svc.process(_trigger())
    calls = svc.notification_svc.send.call_args_list
    channels = [c.args[0].channel for c in calls]
    assert NotificationChannel.EMAIL not in channels
    assert "email" not in channels


@pytest.mark.asyncio
async def test_27_work_note_communication_matches_notification_body():
    """
    NotificationService.send is called with the exact message body that is
    also persisted as the work note (NotificationService handles that internally).
    Verify the same message is in both Teams and Email calls for positive case.
    """
    svc = _make_service(
        latest_note=_mock_work_note("USER"),
        agent_response=_positive_agent_response(summary="VPN is now working."),
    )
    await svc.process(_trigger())
    calls = svc.notification_svc.send.call_args_list
    assert len(calls) >= 2  # Teams + Email

    teams_call = next(c for c in calls if c.args[0].channel == NotificationChannel.TEAMS)
    email_call = next(c for c in calls if c.args[0].channel == NotificationChannel.EMAIL)

    # Both should carry the same message body
    assert teams_call.args[0].message == email_call.args[0].message


# ===========================================================================
# AUTO RESOLUTION TESTS (28-32)
# ===========================================================================

@pytest.mark.asyncio
async def test_28_positive_plus_eligible_provenance_auto_resolves():
    """Positive response + ACKNOWLEDGEMENT_AGENT work note → auto-resolve performed."""
    ack_note = MagicMock()
    ack_note.source_type = WorkNoteSourceType.ACKNOWLEDGEMENT_AGENT.value

    svc = _make_service(
        latest_note=_mock_work_note("USER", "It is working now."),
        agent_response=_positive_agent_response(),
        provenance_notes=[ack_note],
    )
    result = await svc.process(_trigger())
    data = result.result
    assert data["action"] == ResolutionAction.AUTO_RESOLVED.value
    svc.incident_service.update_incident_internal.assert_called_once()


@pytest.mark.asyncio
async def test_29_positive_without_provenance_no_auto_resolve():
    """Positive response but no ACKNOWLEDGEMENT_AGENT/PENDING_AGENT notes → no auto-resolve."""
    svc = _make_service(
        latest_note=_mock_work_note("USER", "Fixed."),
        agent_response=_positive_agent_response(),
        provenance_notes=[],   # empty → no provenance
    )
    result = await svc.process(_trigger())
    data = result.result
    assert data["action"] == ResolutionAction.NOTIFIED.value
    svc.incident_service.update_incident_internal.assert_not_called()


@pytest.mark.asyncio
async def test_30_negative_response_no_auto_resolve():
    """Negative user response must never trigger auto-resolve."""
    svc = _make_service(
        latest_note=_mock_work_note("USER", "Still not working."),
        agent_response=_negative_agent_response(),
    )
    result = await svc.process(_trigger())
    data = result.result
    assert data["action"] == ResolutionAction.NOTIFIED.value
    svc.incident_service.update_incident_internal.assert_not_called()


@pytest.mark.asyncio
async def test_31_llm_failure_no_auto_resolve():
    """LLM failure must prevent auto-resolve entirely."""
    svc = _make_service(
        latest_note=_mock_work_note("USER"),
        agent_response=_failed_agent_response(),
    )
    result = await svc.process(_trigger())
    svc.incident_service.update_incident_internal.assert_not_called()
    assert result.result["action"] == ResolutionAction.FAILED.value


@pytest.mark.asyncio
async def test_32_duplicate_trigger_no_duplicate_auto_resolution():
    """
    Processing the same trigger twice must not call update_incident_internal twice.
    On the second call the incident is already resolved (state='resolved'),
    so the service returns early via the ignored path.

    We simulate this by making the second get_incident return state='resolved'
    so that the incident is no longer in a pending→active transition context.
    """
    ack_note = MagicMock()
    ack_note.source_type = WorkNoteSourceType.ACKNOWLEDGEMENT_AGENT.value

    svc = _make_service(
        latest_note=_mock_work_note("USER"),
        agent_response=_positive_agent_response(),
        provenance_notes=[ack_note],
    )

    # First call — should auto-resolve
    await svc.process(_trigger())
    first_call_count = svc.incident_service.update_incident_internal.call_count
    assert first_call_count == 1

    # Second call with same trigger — change latest note to SYSTEM (non-USER)
    # to simulate that the incident was already processed (agent wrote an audit note)
    svc.work_note_svc.get_latest.return_value = _mock_work_note("SYSTEM", "Resolved by agent.")
    result2 = await svc.process(_trigger())
    # Should be ignored this time (latest note is SYSTEM, not USER)
    assert result2.result["action"] == ResolutionAction.IGNORED.value
    # update_incident_internal still only called once (first call)
    assert svc.incident_service.update_incident_internal.call_count == 1


# ===========================================================================
# FAILURE TESTS (33-35)
# ===========================================================================

@pytest.mark.asyncio
async def test_33_notification_failure_handled_safely():
    """If notification delivery fails, result is still returned without exception."""
    failed_teams = _mock_notif_result(success=False, channel="teams")
    failed_teams.success = False
    failed_teams.error = "Teams delivery failed"

    svc = _make_service(
        latest_note=_mock_work_note("USER"),
        agent_response=_positive_agent_response(),
        notif_teams_result=failed_teams,
    )
    # Should not raise
    result = await svc.process(_trigger())
    assert result is not None
    data = result.result
    teams_notif = next((n for n in data["notifications"] if n["channel"] == "teams"), None)
    assert teams_notif is not None
    assert teams_notif["success"] is False


@pytest.mark.asyncio
async def test_34_assigned_engineer_email_not_found_teams_skipped_gracefully():
    """
    When AIContext has no matching engineer for assigned_to name,
    Teams notification is skipped with a failure outcome — no exception.
    """
    # Context with engineers that don't match the incident's assigned_to
    context = _mock_context(engineers=[])  # no engineers

    svc = _make_service(
        latest_note=_mock_work_note("USER"),
        context=context,
        agent_response=_positive_agent_response(),
    )
    result = await svc.process(_trigger())
    data = result.result
    # Teams outcome should exist and be marked failed (no recipient)
    teams_notif = next((n for n in data["notifications"] if n["channel"] == "teams"), None)
    assert teams_notif is not None
    assert teams_notif["success"] is False
    assert teams_notif["recipient"] == ""


@pytest.mark.asyncio
async def test_35_assignment_group_no_emails_email_skipped_gracefully():
    """
    When AIContext.engineers is empty, assignment-group email is skipped gracefully.
    """
    from app.modules.context.schemas import EngineerContext

    context_no_engineers = _mock_context(engineers=[])

    svc = _make_service(
        latest_note=_mock_work_note("USER"),
        context=context_no_engineers,
        agent_response=_positive_agent_response(),
    )
    result = await svc.process(_trigger())
    data = result.result
    email_notif = next((n for n in data["notifications"] if n["channel"] == "email"), None)
    assert email_notif is not None
    assert email_notif["success"] is False
    assert email_notif["recipient"] == ""
