"""
WebSocket Connection Manager for real-time incident updates.
Manages active connections and broadcasts events to clients.
"""
import logging
from fastapi import WebSocket

logger = logging.getLogger(__name__)

# Store active WebSocket connections per incident
# Format: {incident_id: [websocket1, websocket2, ...]}
active_connections: dict[str, list[WebSocket]] = {}


async def connect(incident_id: str, websocket: WebSocket):
    """Add a new WebSocket connection for an incident"""
    await websocket.accept()
    if incident_id not in active_connections:
        active_connections[incident_id] = []
    active_connections[incident_id].append(websocket)
    logger.info(f"[WebSocket] Client connected to incident {incident_id}. Total: {len(active_connections[incident_id])}")


def disconnect(incident_id: str, websocket: WebSocket):
    """Remove a WebSocket connection"""
    if incident_id in active_connections:
        active_connections[incident_id].remove(websocket)
        if not active_connections[incident_id]:
            del active_connections[incident_id]
        logger.info(f"[WebSocket] Client disconnected from incident {incident_id}")


async def broadcast(incident_id: str, event: dict):
    """Broadcast an event to all connected clients for an incident"""
    if incident_id not in active_connections:
        return

    disconnected = []
    for connection in active_connections[incident_id]:
        try:
            await connection.send_json(event)
        except Exception as e:
            logger.error(f"[WebSocket] Failed to send to {incident_id}: {e}")
            disconnected.append(connection)

    # Clean up dead connections
    for conn in disconnected:
        try:
            disconnect(incident_id, conn)
        except Exception:
            pass
