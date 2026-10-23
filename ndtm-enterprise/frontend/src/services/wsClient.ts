type EventCallback = (data: any) => void;

class WebSocketClient {
  private socket: WebSocket | null = null;
  private listeners: Map<string, Set<EventCallback>> = new Map();
  private reconnectInterval = 3000;
  private isExplicitClose = false;

  connect() {
    this.isExplicitClose = false;
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const host = window.location.host;
    const wsUrl = `${protocol}//${host}/ws/telemetry`;

    try {
      this.socket = new WebSocket(wsUrl);

      this.socket.onopen = () => {
        console.log("[NDTM WS] Telemetry stream connected.");
      };

      this.socket.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
          const eventType = payload.event;
          const data = payload.data;

          const callbacks = this.listeners.get(eventType);
          if (callbacks) {
            callbacks.forEach((cb) => cb(data));
          }

          // Wildcard listeners
          const allCallbacks = this.listeners.get("*");
          if (allCallbacks) {
            allCallbacks.forEach((cb) => cb({ event: eventType, data }));
          }
        } catch {
          // Non-JSON ping/pong
        }
      };

      this.socket.onclose = () => {
        if (!this.isExplicitClose) {
          console.warn("[NDTM WS] Connection dropped. Reconnecting in 3s...");
          setTimeout(() => this.connect(), this.reconnectInterval);
        }
      };

      this.socket.onerror = (err) => {
        console.error("[NDTM WS] WebSocket error:", err);
        this.socket?.close();
      };
    } catch (e) {
      setTimeout(() => this.connect(), this.reconnectInterval);
    }
  }

  subscribe(eventType: string, callback: EventCallback) {
    if (!this.listeners.has(eventType)) {
      this.listeners.set(eventType, new Set());
    }
    this.listeners.get(eventType)!.add(callback);

    return () => {
      this.listeners.get(eventType)?.delete(callback);
    };
  }

  disconnect() {
    this.isExplicitClose = true;
    this.socket?.close();
  }
}

export const wsClient = new WebSocketClient();
