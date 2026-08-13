"""Triage Agent result schemas."""
from datetime import datetime
from pydantic import BaseModel


class EngineerRecommendation(BaseModel):
    """A single engineer recommendation."""
    engineer_id: str
    name: str
    email: str
    assignment_group: str
    level: str | None
    current_shift: str | None
    confidence_score: float
    reason: str


class TriageResult(BaseModel):
    """Full output of the Triage Agent."""
    incident_id: str
    incident_number: str
    assignment_group: str
    recommended_engineer: EngineerRecommendation | None
    all_candidates: list[EngineerRecommendation]
    recommendation_reason: str
    llm_resolved_group: bool = False  # True if assignment group was determined by LLM
    timestamp: datetime
