"""
Enums for the Incident module.

Values are kept as strings to match ServiceNow field values —
this makes it easy to swap the repository layer to ServiceNow
without changing any business logic or API contracts.
"""
from enum import Enum


class IncidentPriority(str, Enum):
    """
    Incident priority based on impact + urgency matrix.
    Values align with ServiceNow priority field (1=Critical, 4=Low).
    """
    CRITICAL = "1"
    HIGH = "2"
    MEDIUM = "3"
    LOW = "4"


class IncidentState(str, Enum):
    """
    Lifecycle states of an incident.
    Transitions: new -> in_progress -> resolved -> closed
    on_hold and cancelled can occur at any point.
    """
    NEW = "new"
    IN_PROGRESS = "in_progress"
    ON_HOLD = "on_hold"
    RESOLVED = "resolved"
    CLOSED = "closed"
    CANCELLED = "cancelled"


class IncidentCategory(str, Enum):
    """Top-level category for classifying the type of incident."""
    NETWORK = "network"
    HARDWARE = "hardware"
    SOFTWARE = "software"
    DATABASE = "database"
    SECURITY = "security"
    ACCESS = "access"
    EMAIL = "email"
    VPN = "vpn"
    APPLICATION = "application"
    OTHER = "other"


class IncidentImpact(str, Enum):
    """
    Business impact of the incident.
    1=High (many users/critical systems), 3=Low (single user/non-critical).
    """
    HIGH = "1"
    MEDIUM = "2"
    LOW = "3"


class IncidentUrgency(str, Enum):
    """
    How quickly the incident needs to be resolved.
    1=High (immediate), 3=Low (can wait).
    """
    HIGH = "1"
    MEDIUM = "2"
    LOW = "3"


class IncidentEnvironment(str, Enum):
    """Target environment where the incident occurred."""
    PRODUCTION = "production"
    STAGING = "staging"
    DEVELOPMENT = "development"
    DR = "dr"  # Disaster Recovery environment


class IncidentSource(str, Enum):
    """How the incident was reported/detected."""
    MANUAL = "manual"         # Created manually by an agent
    MONITORING = "monitoring" # Triggered by monitoring/alerting tool
    EMAIL = "email"           # Raised via email
    PHONE = "phone"           # Raised via phone call
    SELF_SERVICE = "self_service"  # User submitted via portal
    API = "api"               # Created via API (e.g. integration)
