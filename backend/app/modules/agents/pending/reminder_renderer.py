"""
Reminder Renderer for Pending Agent.
Renders Jinja2 HTML reminder emails and generates formatted plain-text email bodies for work notes.
"""
import logging
from pathlib import Path
from jinja2 import Environment, FileSystemLoader

logger = logging.getLogger(__name__)
TEMPLATES_DIR = Path(__file__).parent / "templates"


class PendingReminderRenderer:
    def __init__(self):
        self.env = Environment(
            loader=FileSystemLoader(str(TEMPLATES_DIR)),
            autoescape=True,
        )

    def render_html(self, context: dict) -> str:
        """Renders standard_pending_reminder.html with context data."""
        try:
            template = self.env.get_template("standard_pending_reminder.html")
            return template.render(**context)
        except Exception as e:
            logger.error(f"Error rendering reminder HTML template: {e}")
            return f"<html><body><p>Reminder for incident {context.get('ticket_number')}</p></body></html>"

    def render_plain_text_email(self, context: dict) -> str:
        """
        Renders a clean, structured plain-text version of the reminder email
        to be stored inside the incident work note.
        """
        ticket_num = context.get("ticket_number", "INC0000000")
        caller = context.get("caller_name", "Valued Employee")
        short_desc = context.get("short_description", "")
        group = context.get("assignment_group", "Support Team")
        engineer = context.get("assigned_engineer_name", "Assigned Support Engineer")
        reminder_count = context.get("reminder_count", 1)
        max_reminders = context.get("max_reminders", 3)
        is_final = reminder_count >= max_reminders

        if is_final:
            subject = f"FINAL REMINDER (3/3) - Action Required on Ticket {ticket_num}"
            notice = (
                "[FINAL WARNING: Action Required to Prevent Ticket Closure]\n"
                "This is the third and final reminder. Our support team has not received a response. "
                "Please provide the requested information or this incident may be closed due to inactivity."
            )
        elif reminder_count == 2:
            subject = f"Follow-up Reminder (2/3) - Awaiting Response on Ticket {ticket_num}"
            notice = (
                "[SECOND REMINDER: Information Needed]\n"
                "Our support engineer is still waiting for your clarification or details to continue troubleshooting."
            )
        else:
            subject = f"Follow-up Reminder (1/3) - Ticket {ticket_num}"
            notice = (
                "[ACTION REQUIRED: Additional Information Needed]\n"
                "Our support team has updated your ticket to Pending status while awaiting additional details from you."
            )

        awaiting = context.get("awaiting_detail")
        awaiting_line = f"• Details Needed from You: {awaiting}\n" if awaiting else ""

        return (
            f"Subject: {subject}\n\n"
            f"Hello {caller},\n\n"
            f"This is a follow-up reminder regarding your incident {ticket_num} (\"{short_desc}\").\n\n"
            f"{notice}\n\n"
            f"Ticket Details:\n"
            f"• Incident Number: {ticket_num}\n"
            f"• Short Description: {short_desc}\n"
            f"• Assigned Group: {group}\n"
            f"• Assigned Engineer: {engineer}\n"
            f"{awaiting_line}"
            f"• Follow-up Count: Reminder {reminder_count} of {max_reminders}\n"
            f"• Current Status: Pending User Response\n\n"
            f"Please update your ticket in the portal or reply to this notice so we can assist you:\n"
            f"Portal Link: https://servicenow.corp.internal/nav_to.do?uri=incident.do?sys_id={ticket_num}\n\n"
            f"Regards,\n"
            f"{engineer}\n"
            f"{group}"
        )
