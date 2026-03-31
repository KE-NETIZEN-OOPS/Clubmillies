'use client';

import { useEffect, useRef, useState, useCallback } from 'react';

interface WSEvent {
  type: string;
  data: Record<string, any>;
  timestamp: string;
}

export function useWebSocket() {
  const [events, setEvents] = useState<WSEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  const connect = useCallback(() => {
    const envWsUrl = process.env.NEXT_PUBLIC_WS_URL;
    const defaultProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const defaultWsUrl = `${defaultProtocol}//${window.location.host}/ws`;
    const wsUrl = envWsUrl?.trim() ? envWsUrl : defaultWsUrl;
    const ws = new WebSocket(wsUrl);

    ws.onopen = () => setConnected(true);
    ws.onclose = () => {
      setConnected(false);
      setTimeout(connect, 3000); // Reconnect
    };
    ws.onmessage = (e) => {
      try {
        const event: WSEvent = JSON.parse(e.data);
        setEvents((prev) => [event, ...prev].slice(0, 100));
      } catch {}
    };

    wsRef.current = ws;
  }, []);

  useEffect(() => {
    connect();
    return () => wsRef.current?.close();
  }, [connect]);

  return { events, connected };
}
