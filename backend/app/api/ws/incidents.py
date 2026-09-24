"""
WebSocket endpoint for real-time incident updates.
Clients connect to /ws/incidents/{incident_id} to receive live events.
"""
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.api.ws.manager import connect, disconnect

logger = logging.getLogger(__name__)
router = APIRouter()


@router.websocket("/ws/incidents/{incident_id}")
async def websocket_endpoint(websocket: WebSocket, incident_id: str):
    """
    WebSocket endpoint for real-time incident updates.
    
    Usage:
    - Connect: ws://localhost:8000/ws/incidents/INC0000001
    - Receives JSON events as they occur
    - Auto-reconnects on disconnect
    """
    await connect(incident_id, websocket)
    
    try:
        while True:
            # Keep connection open, receive heartbeat pings
            data = await websocket.receive_text()
            # Echo back to keep connection alive
            await websocket.send_text("pong")
    except WebSocketDisconnect:
        disconnect(incident_id, websocket)
    except Exception as e:
        logger.error(f"[WebSocket] Error in {incident_id}: {e}")
        try:
            disconnect(incident_id, websocket)
        except Exception:
            pass
