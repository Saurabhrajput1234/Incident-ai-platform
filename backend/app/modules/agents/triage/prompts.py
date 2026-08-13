"""
Triage Agent prompts.

COMMON_QUEUE_GROUPS  — generic helpdesk groups that need LLM to determine the real group
SPECIFIC_GROUPS      — actual technical teams with real engineers
ASSIGNMENT_GROUPS    — all specific groups, used as LLM target list

When an incident arrives from a common queue group (or has no group),
the LLM analyzes the incident text and picks from ASSIGNMENT_GROUPS.
"""

# Common queue / generic groups — these need LLM resolution to a specific team
COMMON_QUEUE_GROUPS = {
    "IT Service Desk",
    "IT Helpdesk",
    "General IT Support",
    "L1 Support",
    "Enterprise Support",
    "General Support",
    "Technical Support",
    "Service Operations",
}

# Specific technical assignment groups — LLM picks from this list
# Update this list to match the assignment groups in your shift roster Excel
ASSIGNMENT_GROUPS = [
    "Windows Support",
    "Network Support",
    "Database Support",
    "Linux Support",
    "Cloud Infrastructure",
    "Storage Support",
    "SAP Support",
    "Oracle Support",
    "Security Operations",
    "Middleware Support",
    "Active Directory Support",
    "Backup Support",
    "Citrix Support",
    "Application Support",
    "DevOps Support",
    "Hardware Support",
    "Virtualization Support",
    "Email Support",
    "Telecom Support",
    "Endpoint Support",
]


def is_common_queue(assignment_group: str | None) -> bool:
    """
    Returns True if the assignment group is a common/generic queue
    that requires LLM resolution to a specific team.
    Also returns True if assignment_group is None or empty.
    """
    if not assignment_group:
        return True
    return assignment_group.strip() in COMMON_QUEUE_GROUPS


# System prompt — LLM must pick from ASSIGNMENT_GROUPS only
ASSIGNMENT_GROUP_SYSTEM_PROMPT = """You are an IT incident management expert.
Your task is to determine the correct specific assignment group for an IT incident.

Rules:
- You MUST respond with ONLY one assignment group name from the list below
- Do NOT add any explanation, punctuation, or extra text
- If none of the groups clearly match, respond with exactly: UNKNOWN

Specific Assignment Groups:
{assignment_groups}
"""

# User prompt — incident details for LLM to analyze
ASSIGNMENT_GROUP_USER_PROMPT = """Determine the specific assignment group for this IT incident:

Short Description: {short_description}

Description: {description}

Work Notes: {work_notes}

Respond with only the assignment group name:"""


def build_assignment_group_messages(
    short_description: str,
    description: str | None,
    work_notes: str | None,
    available_groups: list[str] | None = None,
) -> list[dict]:
    """
    Build messages for the assignment group detection LLM call.
    Uses ASSIGNMENT_GROUPS if available_groups not provided.
    """
    groups = available_groups or ASSIGNMENT_GROUPS

    system = ASSIGNMENT_GROUP_SYSTEM_PROMPT.format(
        assignment_groups="\n".join(f"- {g}" for g in groups)
    )
    user = ASSIGNMENT_GROUP_USER_PROMPT.format(
        short_description=short_description,
        description=description or "Not provided",
        work_notes=work_notes or "Not provided",
    )

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
