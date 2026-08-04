"""
SQLAlchemy model for the Incident entity.

This model represents the incident table structure in PostgreSQL.
In future phases, this can be swapped with a ServiceNow REST API
adapter without changing the service/API layers.
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Text, DateTime, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column
from app.database.postgres.base import Base
from app.modules.incidents.enums import (
    IncidentPriority, IncidentState, IncidentCategory,
    IncidentImpact, IncidentUrgency, IncidentEnvironment, IncidentSource
)


class Incident(Base):
    """
    Incident database model.
    
    Represents a support incident with its full lifecycle
    from creation through assignment, resolution, and closure.
    """

    __tablename__ = "incidents"

    # Primary identifiers
    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    incident_number: Mapped[str] = mapped_column(
        String(20), unique=True, nullable=False, index=True
    )  # e.g. INC0000123
    
    # Core description fields
    short_description: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Priority and state management
    priority: Mapped[str] = mapped_column(
        SAEnum(IncidentPriority), nullable=False, default=IncidentPriority.MEDIUM
    )
    state: Mapped[str] = mapped_column(
        SAEnum(IncidentState), nullable=False, default=IncidentState.NEW
    )
    
    # Classification
    category: Mapped[str | None] = mapped_column(SAEnum(IncidentCategory), nullable=True)
    subcategory: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Impact and urgency (used to calculate priority)
    impact: Mapped[str] = mapped_column(
        SAEnum(IncidentImpact), nullable=False, default=IncidentImpact.MEDIUM
    )
    urgency: Mapped[str] = mapped_column(
        SAEnum(IncidentUrgency), nullable=False, default=IncidentUrgency.MEDIUM
    )

    # Assignment fields
    assignment_group: Mapped[str | None] = mapped_column(String(100), nullable=True)
    assigned_to: Mapped[str | None] = mapped_column(String(100), nullable=True)
    caller: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # CMDB references
    configuration_item: Mapped[str | None] = mapped_column(String(100), nullable=True)
    business_service: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Environment and source
    environment: Mapped[str | None] = mapped_column(
        SAEnum(IncidentEnvironment), nullable=True
    )
    source: Mapped[str] = mapped_column(
        SAEnum(IncidentSource), nullable=False, default=IncidentSource.MANUAL
    )

    # Notes and comments
    work_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    comments: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )
