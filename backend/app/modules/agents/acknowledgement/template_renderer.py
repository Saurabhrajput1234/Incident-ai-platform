"""
Template Renderer for Acknowledgement Agent.
Renders Jinja2 HTML email templates and generates formatted plain-text email content.
"""
import logging
from pathlib import Path
from jinja2 import Environment, FileSystemLoader

logger = logging.getLogger(__name__)
TEMPLATES_DIR = Path(__file__).parent / "templates"


class TemplateRenderer:
    def __init__(self):
        self.env = Environment(
            loader=FileSystemLoader(str(TEMPLATES_DIR)),
            autoescape=True,
        )

    def render_html(self, template_name: str, context: dict) -> str:
        """
        Renders the Jinja2 HTML email template.
        Only salesforce_incorrect_request.html and standard_ack.html are active.
        All other templates route to standard_ack.html.
        """
        target_template = (
            "salesforce_incorrect_request.html"
            if template_name == "salesforce_incorrect_request.html"
            else "standard_ack.html"
        )
        try:
            template = self.env.get_template(target_template)
            return template.render(**context)
        except Exception as e:
            logger.error(f"Error rendering HTML template '{target_template}': {e}")
            return f"<html><body><p>Notification for incident {context.get('ticket_number')}</p></body></html>"

    def render_plain_text_email(self, template_name: str, context: dict) -> str:
        """
        Renders a clean, structured plain-text version of the email for work notes & notifications.
        Only salesforce_incorrect_request.html and standard_ack.html are active.
        All other requests route to standard_ack.html.
        """
        ticket_num = context.get("ticket_number", "INC0000000")
        caller = context.get("caller_name", "Valued Employee")
        short_desc = context.get("short_description", "")
        group = context.get("assignment_group", "Support Team")
        engineer = context.get("assigned_engineer_name", "Assigned Support Engineer")

        if template_name == "salesforce_incorrect_request.html":
            return (
                f"Subject: Salesforce Access & Update Request Notice - {ticket_num}\n\n"
                f"Hi {caller},\n\n"
                f"Good day to you.\n"
                f"Thank you for reaching out to the SBD IT Support Team.\n\n"
                f"[NOTICE: Incorrect Form Submitted]\n"
                f"This is not the correct form for Salesforce access or Profile Update requests.\n\n"
                f"For access or updates in Salesforce.com GTS (EANZ) & GEM, you need to raise a Request Item (RITM). "
                f"Please follow the steps below to submit your request:\n\n"
                f"1. Go to IT Central: https://sbdkproduction.service-now.com/esc\n"
                f"2. Search for \"Application Access Request\".\n"
                f"3. Select the \"Salesforce.com GTS (EANZ) & GEM\" option in the Application name field in the Application Access Request form.\n"
                f"4. Fill out the form according to your specific access requirements.\n"
                f"5. Do mention any mirror ID whose access can be replicated for you in the Additional Comment section.\n\n"
                f"IT Central Portal Link: https://sbdkproduction.service-now.com/esc\n\n"
                f"If you encounter any issues, please feel free to reach out to us at aman.mourya@sbdinc.com and we'll be happy to assist you further.\n\n"
                f"As this is not the correct form for access requests, this incident ticket will be updated accordingly.\n\n"
                f"Regards,\n"
                f"Aman Mourya\n"
                f"HCL Apps Run-SFDC Support Team"
            )
        else:  # standard_ack.html (all other requests routed here)
            return (
                f"Subject: Incident Assignment Notification - {ticket_num}\n\n"
                f"Hello {caller},\n\n"
                f"Your support ticket has been triaged and assigned to our technical operations team for investigation.\n\n"
                f"Ticket Details:\n"
                f"• Incident Number: {ticket_num}\n"
                f"• Short Description: {short_desc}\n"
                f"• Assigned Group: {group}\n"
                f"• Assigned Engineer: {engineer}\n"
                f"• Current Status: In Progress\n\n"
                f"Our engineer, {engineer}, is actively reviewing your issue and will update you via work notes as progress is made.\n\n"
                f"View Ticket Link: https://servicenow.corp.internal/nav_to.do?uri=incident.do?sys_id={ticket_num}\n\n"
                f"Regards,\n"
                f"Enterprise Incident AI Platform Team"
            )
