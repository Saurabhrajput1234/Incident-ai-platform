"""Integration tests for incidents REST API."""
import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.anyio


async def _create_incident(client: AsyncClient, short_description: str = "Test email issue") -> dict:
    resp = await client.post("/v1/incidents", json={"short_description": short_description})
    assert resp.status_code == 201
    return resp.json()


@pytest.mark.anyio
async def test_create_incident(client):
    data = await _create_incident(client, "VPN connection dropping")
    assert data["incident_number"].startswith("INC")
    assert data["state"] == "new"
    assert data["short_description"] == "VPN connection dropping"


@pytest.mark.anyio
async def test_create_incident_validation_error(client):
    resp = await client.post("/v1/incidents", json={"short_description": "abc"})
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_create_incident_missing_required(client):
    resp = await client.post("/v1/incidents", json={})
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_get_incident(client):
    created = await _create_incident(client, "Database timeout")
    resp = await client.get(f"/v1/incidents/{created['id']}")
    assert resp.status_code == 200
    assert resp.json()["id"] == created["id"]


@pytest.mark.anyio
async def test_get_incident_not_found(client):
    resp = await client.get("/v1/incidents/nonexistent-id")
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_list_incidents(client):
    await _create_incident(client, "App server crash")
    resp = await client.get("/v1/incidents")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data
    assert data["total"] >= 1


@pytest.mark.anyio
async def test_list_incidents_pagination(client):
    for i in range(5):
        await _create_incident(client, f"Pagination test incident {i}")
    resp = await client.get("/v1/incidents?page=1&page_size=2")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) <= 2
    assert data["page"] == 1
    assert data["page_size"] == 2


@pytest.mark.anyio
async def test_list_incidents_filter_by_state(client):
    resp = await client.post("/v1/incidents", json={
        "short_description": "Filter by state test",
        "state": "resolved"
    })
    assert resp.status_code == 201
    resp = await client.get("/v1/incidents?state=resolved")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert all(i["state"] == "resolved" for i in items)


@pytest.mark.anyio
async def test_update_incident(client):
    created = await _create_incident(client, "Network latency issue")
    resp = await client.put(f"/v1/incidents/{created['id']}", json={"state": "in_progress"})
    assert resp.status_code == 200
    assert resp.json()["state"] == "in_progress"


@pytest.mark.anyio
async def test_update_incident_not_found(client):
    resp = await client.put("/v1/incidents/nonexistent-id", json={"state": "resolved"})
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_delete_incident(client):
    created = await _create_incident(client, "Password reset broken")
    resp = await client.delete(f"/v1/incidents/{created['id']}")
    assert resp.status_code == 204
    resp = await client.get(f"/v1/incidents/{created['id']}")
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_delete_incident_not_found(client):
    resp = await client.delete("/v1/incidents/nonexistent-id")
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_search_incidents(client):
    await _create_incident(client, "SSL certificate expired on prod")
    resp = await client.get("/v1/incidents/search?q=SSL")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1


@pytest.mark.anyio
async def test_search_incidents_short_query(client):
    resp = await client.get("/v1/incidents/search?q=a")
    assert resp.status_code == 422
