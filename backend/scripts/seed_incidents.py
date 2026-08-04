"""
Seed script: inserts ~100 realistic incidents into the database.
Run from backend/ with venv activated:
    python scripts/seed_incidents.py
"""
import asyncio
import sys
import os
import uuid
from datetime import datetime, timezone, timedelta
import random

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.core.config import settings
from app.modules.incidents.model import Incident
from app.modules.incidents.enums import (
    IncidentPriority, IncidentState, IncidentCategory,
    IncidentImpact, IncidentUrgency, IncidentEnvironment, IncidentSource
)

INCIDENTS = [
    ("Email service not working", "Users unable to send/receive emails", IncidentCategory.EMAIL, "Email Team"),
    ("VPN connection dropping", "VPN disconnects every 10 minutes for remote users", IncidentCategory.VPN, "Network Team"),
    ("Database timeout errors", "Production DB queries timing out after 30s", IncidentCategory.DATABASE, "DBA Team"),
    ("Application server crash", "App server restarting repeatedly", IncidentCategory.APPLICATION, "App Team"),
    ("Server unavailable", "Web server returning 503", IncidentCategory.HARDWARE, "Infrastructure"),
    ("Password reset not working", "Self-service portal not sending reset emails", IncidentCategory.ACCESS, "IAM Team"),
    ("Network latency spike", "High latency across datacenter switches", IncidentCategory.NETWORK, "Network Team"),
    ("Login page slow", "Authentication page taking over 15 seconds to load", IncidentCategory.SOFTWARE, "Web Team"),
    ("Printer not responding", "Floor 3 printer offline", IncidentCategory.HARDWARE, "Hardware Team"),
    ("File share access denied", "Users cannot access shared drive", IncidentCategory.ACCESS, "IAM Team"),
    ("SSL certificate expired", "HTTPS certificate expired on api.internal", IncidentCategory.SECURITY, "Security Team"),
    ("Backup job failed", "Nightly backup did not complete", IncidentCategory.DATABASE, "DBA Team"),
    ("High CPU on server", "CPU at 99% on production node", IncidentCategory.HARDWARE, "Infrastructure"),
    ("Memory leak in service", "Java heap growing unbounded", IncidentCategory.SOFTWARE, "App Team"),
    ("DNS resolution failure", "Internal DNS not resolving hostnames", IncidentCategory.NETWORK, "Network Team"),
    ("Storage disk full", "/var partition at 100%", IncidentCategory.HARDWARE, "Infrastructure"),
    ("API rate limit exceeded", "Third party API returning 429 errors", IncidentCategory.APPLICATION, "Integration Team"),
    ("Two-factor auth broken", "OTP not being delivered", IncidentCategory.SECURITY, "Security Team"),
    ("Firewall blocking traffic", "New firewall rule blocking internal traffic", IncidentCategory.NETWORK, "Network Team"),
    ("CI/CD pipeline failing", "Jenkins build failing at test stage", IncidentCategory.SOFTWARE, "DevOps Team"),
    ("Kubernetes pod crashing", "Pod stuck in CrashLoopBackOff", IncidentCategory.APPLICATION, "DevOps Team"),
    ("Load balancer misconfigured", "Traffic not distributing evenly", IncidentCategory.NETWORK, "Infrastructure"),
    ("Database replication lag", "Replica 30 minutes behind primary", IncidentCategory.DATABASE, "DBA Team"),
    ("Cache invalidation issue", "Redis cache returning stale data", IncidentCategory.DATABASE, "App Team"),
    ("Webhook delivery failure", "Outbound webhooks not reaching endpoints", IncidentCategory.APPLICATION, "Integration Team"),
    ("LDAP sync broken", "AD groups not syncing to application", IncidentCategory.ACCESS, "IAM Team"),
    ("Scheduled job not running", "Cron job missed last 3 executions", IncidentCategory.SOFTWARE, "App Team"),
    ("Report generation timeout", "PDF reports timing out for large datasets", IncidentCategory.APPLICATION, "App Team"),
    ("Mobile app crash on login", "iOS app crashes after entering credentials", IncidentCategory.APPLICATION, "Mobile Team"),
    ("Monitoring alert flood", "PagerDuty receiving thousands of false alerts", IncidentCategory.SOFTWARE, "DevOps Team"),
    ("S3 bucket access denied", "Application cannot read from S3", IncidentCategory.ACCESS, "Cloud Team"),
    ("NTP sync failure", "Server clocks drifting out of sync", IncidentCategory.NETWORK, "Network Team"),
    ("Kernel panic on node", "Linux kernel panic on node worker-04", IncidentCategory.HARDWARE, "Infrastructure"),
    ("Log aggregation down", "Kibana not receiving logs from services", IncidentCategory.SOFTWARE, "DevOps Team"),
    ("Service mesh timeout", "Istio sidecar proxy rejecting connections", IncidentCategory.NETWORK, "DevOps Team"),
    ("Email spam filter issue", "Legitimate emails being quarantined", IncidentCategory.EMAIL, "Email Team"),
    ("VPN license exhausted", "No available VPN sessions", IncidentCategory.VPN, "Network Team"),
    ("Database connection pool full", "App cannot acquire DB connections", IncidentCategory.DATABASE, "DBA Team"),
    ("Config management drift", "Ansible failing on 12 nodes", IncidentCategory.SOFTWARE, "DevOps Team"),
    ("Antivirus blocking app", "AV quarantined required DLL", IncidentCategory.SECURITY, "Security Team"),
    ("IP address conflict", "Duplicate IP detected on subnet", IncidentCategory.NETWORK, "Network Team"),
    ("SSH key expired", "Automated deployment failing due to expired key", IncidentCategory.ACCESS, "IAM Team"),
    ("Slow query degrading DB", "Single query consuming 80% DB CPU", IncidentCategory.DATABASE, "DBA Team"),
    ("Application deployment failed", "Rollout stuck at 50% replicas", IncidentCategory.APPLICATION, "DevOps Team"),
    ("CDN cache poisoning", "Incorrect content being served from CDN", IncidentCategory.SECURITY, "Security Team"),
    ("Message queue backlog", "RabbitMQ queue depth over 1 million", IncidentCategory.APPLICATION, "Integration Team"),
    ("Service account locked", "Batch job service account locked out", IncidentCategory.ACCESS, "IAM Team"),
    ("Network switch down", "Core switch in rack B unresponsive", IncidentCategory.NETWORK, "Network Team"),
    ("Disk I/O bottleneck", "High disk wait on database host", IncidentCategory.HARDWARE, "DBA Team"),
    ("Container image pull failed", "OCI registry unreachable", IncidentCategory.APPLICATION, "DevOps Team"),
]

CALLERS = [
    "john.smith", "jane.doe", "alice.johnson", "bob.williams",
    "carol.brown", "david.jones", "eva.garcia", "frank.miller",
    "grace.wilson", "henry.moore", "iris.taylor", "james.anderson",
]

SUBCATEGORIES = {
    IncidentCategory.EMAIL: ["SMTP", "IMAP", "Spam Filter", "Relay"],
    IncidentCategory.VPN: ["SSL VPN", "IPSec", "Client"],
    IncidentCategory.DATABASE: ["PostgreSQL", "MySQL", "Oracle", "Redis", "MongoDB"],
    IncidentCategory.APPLICATION: ["Web App", "API", "Mobile", "Batch"],
    IncidentCategory.NETWORK: ["LAN", "WAN", "WiFi", "Firewall", "DNS"],
    IncidentCategory.HARDWARE: ["Server", "Storage", "Printer", "Switch"],
    IncidentCategory.ACCESS: ["AD", "LDAP", "SSO", "MFA"],
    IncidentCategory.SECURITY: ["Firewall", "IDS", "Certificate", "Patch"],
    IncidentCategory.SOFTWARE: ["OS", "Middleware", "Driver", "Framework"],
    IncidentCategory.OTHER: ["General"],
}


async def seed():
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        incidents = []
        all_entries = INCIDENTS * 3  # ~150 entries, we'll take 100
        random.shuffle(all_entries)

        for i, (short_desc, desc, category, group) in enumerate(all_entries[:100], start=1):
            days_ago = random.randint(0, 90)
            created = datetime.now(timezone.utc) - timedelta(days=days_ago, hours=random.randint(0, 23))
            priority = random.choice(list(IncidentPriority))
            state = random.choice(list(IncidentState))

            incident = Incident(
                id=str(uuid.uuid4()),
                incident_number=f"INC{str(i).zfill(7)}",
                short_description=short_desc,
                description=desc,
                priority=priority.value,
                state=state.value,
                category=category.value,
                subcategory=random.choice(SUBCATEGORIES.get(category, ["General"])),
                impact=random.choice(list(IncidentImpact)).value,
                urgency=random.choice(list(IncidentUrgency)).value,
                assignment_group=group,
                assigned_to=random.choice(CALLERS),
                caller=random.choice(CALLERS),
                environment=random.choice(list(IncidentEnvironment)).value,
                source=random.choice(list(IncidentSource)).value,
                business_service=random.choice([
                    "IT Services", "HR Portal", "Finance System",
                    "Customer Portal", "Internal Tools", None
                ]),
                configuration_item=random.choice([
                    "server-prod-01", "db-cluster-01", "app-server-02",
                    "network-switch-01", None
                ]),
                created_at=created,
                updated_at=created + timedelta(hours=random.randint(0, 48)),
            )
            incidents.append(incident)

        session.add_all(incidents)
        await session.commit()
        print(f"✅ Seeded {len(incidents)} incidents successfully.")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
