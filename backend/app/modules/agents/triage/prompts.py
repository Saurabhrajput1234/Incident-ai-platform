"""
Triage Agent prompts.

COMMON_QUEUE_GROUPS  — generic helpdesk groups that need LLM to determine the real group
SPECIFIC_GROUPS      — actual technical teams with real engineers
ASSIGNMENT_GROUPS    — all specific groups, used as LLM target list

When an incident arrives from a common queue group (or has no group),
the LLM analyzes the incident text and picks from ASSIGNMENT_GROUPS.
"""

# Common queue / generic groups — these need LLM resolution to a specific team
# COMMON_QUEUE_GROUPS = {
#     "IT Service Desk",
#     "IT Helpdesk",
#     "General IT Support",
#     "L1 Support",
#     "Enterprise Support",
#     "General Support",
#     "Technical Support",
#     "Service Operations",
# }

COMMON_QUEUE_GROUPS = {
    "HCL Apps Run-SAP",
  
}

# Specific technical assignment groups — LLM picks from this list
# Update this list to match the assignment groups in your shift roster Excel
# ASSIGNMENT_GROUPS = [
#     "Windows Support",
#     "Network Support",
#     "Database Support",
#     "Linux Support",
#     "Cloud Infrastructure",
#     "Storage Support",
#     "SAP Support",
#     "Oracle Support",
#     "Security Operations",
#     "Middleware Support",
#     "Active Directory Support",
#     "Backup Support",
#     "Citrix Support",
#     "Application Support",
#     "DevOps Support",
#     "Hardware Support",
#     "Virtualization Support",
#     "Email Support",
#     "Telecom Support",
#     "Endpoint Support",
# ]
ASSIGNMENT_GROUPS = [
  "Apps Run - BPM",
  "Apps Run - NON SAP ERP-AS400",
  "Apps Run - NON SAP ERP-INF-INFOR",
  "Apps Run - NON SAP ERP-MS NAV",
  "Apps Run - NON SAP ERP-OAD-LAG",
  "Apps Run - Stat & Tax",
  "Apps Run - User-Admin-JDA/WMS",
  "Apps Run-Ariba",
  "Apps Run-BI-Analytics-SAP BO",
  "Apps Run-BI-Analytics-DataLake",
  "Apps Run-BI-Analytics-PowerBI",
  "Apps Run-BI-Analytics-SAP BW",
  "Apps Run-Christmas",
  "Apps Run-JDE",
  "Apps Run-Kronos",
  "Apps Run-MES",
  "Apps Run-Middleware - EAI",
  "Apps Run-Middleware - EDI/EAI",
  "Apps Run-MyML Operations",
  "Apps Run-OT",
  "Apps Run-SAP - BASIS",
  "Apps Run-SAP - Batch - BASIS",
  "Apps Run-SAP - Development",
  "Apps Run-SAP - FICO",
  "Apps Run-SAP - MM/WM/PP",
  "Apps Run-SAP - PP/QM/PM",
  "Apps Run-SAP - Security/GRC",
  "Apps Run-Supply Chain",
  "Apps Run-PLM",
  "Apps Run-SAP - SD",
  "Apps Run-SFDC",
  "Apps Run-Sun-Corp Apps",
  "Apps Run-MetaStorm",
  "Apps Run-MKT Ecom",
  "Apps Run-SharePoint",
  "Apps Run-Hyperion",
  "Apps Run-NON SAP ERP-XPPS",
  "Apps Run-MTD-SFDC",
  "Apps Run-Digital Ops",
  "Apps Run-Robotic Process Automation",
  "Apps Run-Robotic Process Automation-L",
  "Apps Run-Workday",
  "HCL Apps Run-SAP",
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
Your ONLY job is to pick ONE assignment group from the list below that matches the incident.

CRITICAL RULES:
- Respond with ONLY the exact group name from the list
- Do NOT add any explanation, punctuation, or extra words
- Do NOT include "The answer is" or "I choose" or similar prefixes
- If no group matches, respond with exactly: UNKNOWN

Assignment Groups (pick ONE exactly as shown):
{assignment_groups}"""

# User prompt — incident details for LLM to analyze
ASSIGNMENT_GROUP_USER_PROMPT = """Incident:
Short: {short_description}
Description: {description}

Which group from the list above? Respond with ONLY the group name:"""


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
