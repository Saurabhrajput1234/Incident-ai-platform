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
