"""
Unit tests for Acknowledgement Agent template renderer and service.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from app.modules.agents.acknowledgement.template_renderer import TemplateRenderer
from app.modules.agents.acknowledgement.schemas import IntentResult, IntentType


def test_template_renderer_salesforce_incorrect_request():
    renderer = TemplateRenderer()
    context = {
        "ticket_number": "INC0000043",
        "caller_name": "Tina",
        "short_description": "Need access to Salesforce GTS EANZ",
        "assignment_group": "HCL Apps Run-SFDC",
        "assigned_engineer_name": "Swapna Maji",
    }

    text_content = renderer.render_plain_text_email("salesforce_incorrect_request.html", context)
    assert "Salesforce Access & Update Request Notice - INC0000043" in text_content
    assert "Hi Tina," in text_content
    assert "Application Access Request" in text_content


def test_template_renderer_standard_ack():
    renderer = TemplateRenderer()
    context = {
        "ticket_number": "INC0000044",
        "caller_name": "John",
        "short_description": "Laptop crash",
        "assignment_group": "Windows Support",
        "assigned_engineer_name": "Swapna Maji",
    }

    text_content = renderer.render_plain_text_email("standard_ack.html", context)
    assert "Incident Assignment Notification - INC0000044" in text_content
    assert "Hello John," in text_content
    assert "Assigned Engineer: Swapna Maji" in text_content


def test_template_renderer_other_templates_route_to_standard():
    renderer = TemplateRenderer()
    context = {
        "ticket_number": "INC0000045",
        "caller_name": "Alice",
        "short_description": "Wrong environment or hardware order",
        "assignment_group": "Apps Run-SFDC",
        "assigned_engineer_name": "Swapna Maji",
    }

    # Pass an old/other template name — should route to standard ack
    text_content = renderer.render_plain_text_email("wrong_ticket_access.html", context)
    assert "Incident Assignment Notification - INC0000045" in text_content
    assert "Assigned Engineer: Swapna Maji" in text_content

    html_content = renderer.render_html("wrong_ticket_service_catalog.html", context)
    assert "Incident Assignment Notification" in html_content


@pytest.mark.anyio
async def test_acknowledgement_agent_salesforce_incorrect_routing():
    from datetime import datetime, timezone, date
    from app.modules.agents.acknowledgement.agent import AcknowledgementAgent
    from app.modules.context.schemas import AIContext, IncidentContext

    agent = AcknowledgementAgent()
    agent.intent_classifier.classify_intent = AsyncMock(
        return_value=IntentResult(
            intent=IntentType.SALESFORCE_INCORRECT_REQUEST,
            confidence=0.95,
            reasoning="Access requested via incident",
        )
    )

    incident = IncidentContext(
        incident_id="inc-1",
        incident_number="INC0000001",
        short_description="Need access to Salesforce",
        description="Please give me access to Salesforce",
        priority="3 - Moderate",
        state="in_progress",
        category="Software",
        subcategory="Salesforce",
        assignment_group="Apps Run-SFDC",
        caller="Alice",
        created_at=datetime.now(timezone.utc),
    )
    context = AIContext(
        incident=incident,
        engineers=[],
        context_date=date.today(),
        created_at=datetime.now(timezone.utc),
    )

    response = await agent.reason(context)
    assert response.success is True
    assert response.result["template_used"] == "salesforce_incorrect_request.html"
    assert response.result["intent_info"]["intent"] == "SALESFORCE_INCORRECT_REQUEST"


@pytest.mark.anyio
async def test_acknowledgement_agent_salesforce_other_routes_to_standard():
    from datetime import datetime, timezone, date
    from app.modules.agents.acknowledgement.agent import AcknowledgementAgent
    from app.modules.context.schemas import AIContext, IncidentContext

    agent = AcknowledgementAgent()
    agent.intent_classifier.classify_intent = AsyncMock(
        return_value=IntentResult(
            intent=IntentType.STANDARD_INCIDENT,
            confidence=0.90,
            reasoning="Standard break fix or other inquiry",
        )
    )

    incident = IncidentContext(
        incident_id="inc-2",
        incident_number="INC0000002",
        short_description="Apex CPU timeout error",
        description="CPU limit exceeded during save",
        priority="2 - High",
        state="in_progress",
        category="Software",
        subcategory="Salesforce",
        assignment_group="Apps Run-SFDC",
        caller="Bob",
        created_at=datetime.now(timezone.utc),
    )
    context = AIContext(
        incident=incident,
        engineers=[],
        context_date=date.today(),
        created_at=datetime.now(timezone.utc),
    )

    response = await agent.reason(context)
    assert response.success is True
    assert response.result["template_used"] == "standard_ack.html"
    assert response.result["intent_info"]["intent"] == "STANDARD_INCIDENT"


@pytest.mark.anyio
async def test_acknowledgement_agent_non_salesforce_routes_to_standard():
    from datetime import datetime, timezone, date
    from app.modules.agents.acknowledgement.agent import AcknowledgementAgent
    from app.modules.context.schemas import AIContext, IncidentContext

    agent = AcknowledgementAgent()
    incident = IncidentContext(
        incident_id="inc-3",
        incident_number="INC0000003",
        short_description="Network port down",
        description="Port 4 is not responding",
        priority="3 - Moderate",
        state="in_progress",
        category="Hardware",
        subcategory="Network",
        assignment_group="Network Support",
        caller="Charlie",
        created_at=datetime.now(timezone.utc),
    )
    context = AIContext(
        incident=incident,
        engineers=[],
        context_date=date.today(),
        created_at=datetime.now(timezone.utc),
    )

    response = await agent.reason(context)
    assert response.success is True
    assert response.result["template_used"] == "standard_ack.html"
    assert response.result["intent_info"]["intent"] == "STANDARD_INCIDENT"


