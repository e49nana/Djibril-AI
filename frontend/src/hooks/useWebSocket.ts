// Djibril AI — WebSocket Hook
// Auto-reconnecting WebSocket with typed messages.

import { useCallback, useEffect, useRef, useState } from "react";
import type { WSMessage } from "../types";

interface UseWebSocketOptions {
  url: string;
  onMessage?: (msg: WSMessage) => void;
  reconnectInterval?: number;
  maxRetries?: number;
}

interface UseWebSocketReturn {
  isConnected: boolean;
  lastMessage: WSMessage | null;
  clientCount: number;
  reconnectCount: number;
}

export function useWebSocket({
  url,
  onMessage,
  reconnectInterval = 3000,
  maxRetries = 50,
}: UseWebSocketOptions): UseWebSocketReturn {
  const [isConnected, setIsConnected] = useState(false);
  const [lastMessage, setLastMessage] = useState<WSMessage | null>(null);
  const [clientCount, setClientCount] = useState(0);
  const [reconnectCount, setReconnectCount] = useState(0);

  const wsRef = useRef<WebSocket | null>(null);
  const retriesRef = useRef(0);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    try {
      const ws = new WebSocket(url);

      ws.onopen = () => {
        setIsConnected(true);
        retriesRef.current = 0;
        console.log("[Djibril WS] Connected");
      };

      ws.onmessage = (event: MessageEvent) => {
        try {
          const msg: WSMessage = JSON.parse(event.data as string);
          setLastMessage(msg);

          if (msg.type === "heartbeat") {
            const clients = (msg.payload as Record<string, number>).clients ?? 0;
            setClientCount(clients);
          }

          onMessage?.(msg);
        } catch (err) {
          console.error("[Djibril WS] Parse error:", err);
        }
      };

      ws.onclose = () => {
        setIsConnected(false);
        wsRef.current = null;

        if (retriesRef.current < maxRetries) {
          retriesRef.current += 1;
          setReconnectCount(retriesRef.current);
          reconnectTimerRef.current = setTimeout(connect, reconnectInterval);
        }
      };

      ws.onerror = (err) => {
        console.error("[Djibril WS] Error:", err);
        ws.close();
      };

      wsRef.current = ws;
    } catch (err) {
      console.error("[Djibril WS] Connection failed:", err);
    }
  }, [url, onMessage, reconnectInterval, maxRetries]);

  useEffect(() => {
    connect();
    return () => {
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      wsRef.current?.close();
    };
  }, [connect]);

  return { isConnected, lastMessage, clientCount, reconnectCount };
}
