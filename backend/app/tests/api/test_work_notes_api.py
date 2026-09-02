"""Integration tests for the Work Notes API."""
import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.anyio


async def _create_incident(client: AsyncClient, desc: str = "Test VPN issue") -> dict:
    resp = await client.post("/v1/incidents", json={"short_description": desc})
    assert resp.status_code == 201
    return resp.json()


@pytest.mark.anyio
async def test_add_and_list_work_note(client):
    incident = await _create_incident(client, "Work note test incident")
    incident_id = incident["id"]

    resp = await client.post(
        f"/v1/incidents/{incident_id}/work-notes",
        json={
            "message": "Engineer looked into the issue",
            "source_type": "ENGINEER",
            "source_name": "Alice Smith",
            "source_id": "eng-001",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["incident_id"] == incident_id
    assert data["source_type"] == "ENGINEER"
    assert data["source_name"] == "Alice Smith"
    assert data["source_id"] == "eng-001"
    assert data["action_type"] == "MANUAL_NOTE"
    assert "id" in data
    assert "created_at" in data


@pytest.mark.anyio
async def test_list_work_notes_returns_all(client):
    incident = await _create_incident(client, "List work notes test")
    incident_id = incident["id"]

    for i in range(3):
        await client.post(
            f"/v1/incidents/{incident_id}/work-notes",
            json={"message": f"Note {i}", "source_type": "USER", "source_name": "Bob"},
        )

    resp = await client.get(f"/v1/incidents/{incident_id}/work-notes")
    assert resp.status_code == 200
    notes = resp.json()
    # At least our 3 manual notes (triage may have added more in background)
    assert len(notes) >= 3


@pytest.mark.anyio
async def test_get_latest_work_note(client):
    incident = await _create_incident(client, "Latest note test")
    incident_id = incident["id"]

    await client.post(
        f"/v1/incidents/{incident_id}/work-notes",
        json={"message": "First note", "source_type": "USER", "source_name": "Carol"},
    )
    await client.post(
        f"/v1/incidents/{incident_id}/work-notes",
        json={"message": "Second note — most recent", "source_type": "ENGINEER", "source_name": "Dave"},
    )

    resp = await client.get(f"/v1/incidents/{incident_id}/work-notes/latest")
    assert resp.status_code == 200
    data = resp.json()
    assert data is not None
    # Latest by created_at should be the most recently added
    assert data["source_name"] == "Dave"


@pytest.mark.anyio
async def test_work_notes_isolated_per_incident(client):
    inc1 = await _create_incident(client, "Isolation test incident 1")
    inc2 = await _create_incident(client, "Isolation test incident 2")

    await client.post(
        f"/v1/incidents/{inc1['id']}/work-notes",
        json={"message": "Note for inc1 only", "source_type": "SYSTEM", "source_name": "System"},
    )

    resp = await client.get(f"/v1/incidents/{inc2['id']}/work-notes")
    assert resp.status_code == 200
    notes = resp.json()
    assert all(n["incident_id"] == inc2["id"] for n in notes)


@pytest.mark.anyio
async def test_add_work_note_missing_required_fields(client):
    incident = await _create_incident(client, "Validation test")
    resp = await client.post(
        f"/v1/incidents/{incident['id']}/work-notes",
        json={"message": "Missing source_name"},
    )
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_add_work_note_empty_message(client):
    incident = await _create_incident(client, "Empty message test")
    resp = await client.post(
        f"/v1/incidents/{incident['id']}/work-notes",
        json={"message": "", "source_type": "USER", "source_name": "Eve"},
    )
    assert resp.status_code == 422
