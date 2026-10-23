"""WebSocket connection manager for real-time telemetry streaming to the React cockpit."""
from __future__ import annotations

import json
import logging
from typing import Any

from starlette.websockets import WebSocket, WebSocketState

logger = logging.getLogger("services.websocket")


class WebSocketTelemetryManager:
    """Manages active browser connections and broadcasts real-time system events."""

    def __init__(self) -> None:
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info("WebSocket client connected. Total clients: %d", len(self.active_connections))

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info("WebSocket client disconnected. Total clients: %d", len(self.active_connections))

    async def broadcast_event(self, event_type: str, data: dict[str, Any]) -> None:
        """Broadcasts structured JSON event to all connected dashboard clients."""
        if not self.active_connections:
            return

        payload = json.dumps({"event": event_type, "data": data}, ensure_ascii=False)
        stale_sockets: list[WebSocket] = []

        for socket in self.active_connections:
            try:
                if socket.client_state == WebSocketState.CONNECTED:
                    await socket.send_text(payload)
                else:
                    stale_sockets.append(socket)
            except Exception:
                stale_sockets.append(socket)

        for stale in stale_sockets:
            self.disconnect(stale)


# Global singleton instance
ws_manager = WebSocketTelemetryManager()
