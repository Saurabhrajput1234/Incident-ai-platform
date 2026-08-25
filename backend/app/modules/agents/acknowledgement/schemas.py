"""
Pydantic schemas for the Acknowledgement Agent domain.
"""
from datetime import datetime, timezone
from enum import Enum
from pydantic import BaseModel, Field


class IntentType(str, Enum):
    STANDARD_INCIDENT = "STANDARD_INCIDENT"
    ACCESS_REQUEST = "ACCESS_REQUEST"
    SERVICE_REQUEST = "SERVICE_REQUEST"
    WRONG_REQUEST = "WRONG_REQUEST"
    SALESFORCE_INCORRECT_REQUEST = "SALESFORCE_INCORRECT_REQUEST"


class IntentResult(BaseModel):
    intent: IntentType
    confidence: float
    reasoning: str


class EmailDeliveryLog(BaseModel):
    log_id: str
    incident_number: str
    caller_name: str
    user_email: str
    intent: str
    template_name: str
    delivery_status: str
    sent_timestamp: str


class AcknowledgementResult(BaseModel):
    incident_id: str
    incident_number: str
    caller: str | None = None
    assigned_to: str | None = None
    assignment_group: str | None = None
    intent_info: IntentResult
    template_used: str
    email_sent: bool
    delivery_status: str
    work_notes_added: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
