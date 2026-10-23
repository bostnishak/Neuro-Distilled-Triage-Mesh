import asyncio
import json
import time
from typing import List
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from core.logging_otel import logger

router = APIRouter(prefix="/telemetry", tags=["Real-time Telemetry WebSockets"])


class ConnectionManager:
    """Maintains active WebSocket subscriber connections for operational cockpit."""

    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info("websocket_client_connected", total_clients=len(self.active_connections))

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info("websocket_client_disconnected", total_clients=len(self.active_connections))

    async def broadcast(self, message: dict) -> None:
        raw_msg = json.dumps(message)
        dead_connections = []
        for connection in self.active_connections:
            try:
                await connection.send_text(raw_msg)
            except Exception:
                dead_connections.append(connection)

        for dead in dead_connections:
            self.disconnect(dead)


manager = ConnectionManager()


@router.websocket("/ws")
async def websocket_telemetry_endpoint(websocket: WebSocket) -> None:
    """Live streaming telemetry channel for incident dispatch and kernel vitals."""
    await manager.connect(websocket)

    try:
        # Periodic heartbeat and synthetic telemetry tick generator
        while True:
            # Check for incoming client pings
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=2.0)
                # Client message handled if needed
            except asyncio.TimeoutError:
                pass

            # Stream kernel telemetry heartbeat
            tick = {
                "type": "TELEMETRY_HEARTBEAT",
                "timestamp": time.time(),
                "metrics": {
                    "shm_active_slots": 4,
                    "hawkes_clusters_active": 3,
                    "circuit_breaker_state": "CLOSED",
                    "smt_solver_latency_ms": 48.2,
                    "gcra_allowed_rate": 45.0,
                },
            }
            await websocket.send_text(json.dumps(tick))

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.warning("websocket_session_ended", error=str(e))
        manager.disconnect(websocket)
