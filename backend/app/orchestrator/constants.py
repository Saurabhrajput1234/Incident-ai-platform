"""
Canonical agent source name constants for orchestration layer.

Use these everywhere a changed_by or triggering_work_note_source string
is compared.  Eliminates "PendingAgent" vs "PENDING AGENT" vs "Pending Agent"
inconsistencies.

These values map 1-to-1 to WorkNoteSourceType enum values where applicable.
"""


class AgentSource:
    """Canonical string values for changed_by and triggering_work_note_source."""
    TRIAGE_AGENT = "TRIAGE_AGENT"
    ACKNOWLEDGEMENT_AGENT = "ACKNOWLEDGEMENT_AGENT"
    PENDING_AGENT = "PENDING_AGENT"
    RESOLUTION_AGENT = "RESOLUTION_AGENT"
    ENGINEER = "ENGINEER"
    USER = "USER"
    SYSTEM = "SYSTEM"


# Set of all non-user sources — used by ResolutionHandler to skip agent-triggered activations
NON_USER_SOURCES: frozenset[str] = frozenset({
    AgentSource.PENDING_AGENT,
    AgentSource.ACKNOWLEDGEMENT_AGENT,
    AgentSource.TRIAGE_AGENT,
    AgentSource.RESOLUTION_AGENT,
    AgentSource.ENGINEER,
    AgentSource.SYSTEM,
})
