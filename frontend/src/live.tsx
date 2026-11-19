import { createContext, ReactNode, useCallback, useContext, useEffect, useRef, useState } from "react";
import { api } from "./api";
import type { Alert, TrailerSummary } from "./types";

type Listener = (a: Alert, isNew: boolean) => void;

interface LiveState {
  connected: boolean;
  trailers: Record<string, TrailerSummary>;
  activeAlerts: Alert[];
  onAlert: (fn: Listener) => () => void;
  refreshTrailers: () => Promise<void>;
  ackAlert: (id: number, by?: string) => Promise<void>;
}

const Ctx = createContext<LiveState | null>(null);

export function LiveProvider({ children }: { children: ReactNode }) {
  const [connected, setConnected] = useState(false);
  const [trailers, setTrailers] = useState<Record<string, TrailerSummary>>({});
  const [activeAlerts, setActiveAlerts] = useState<Alert[]>([]);
  const listeners = useRef(new Set<Listener>());

  const refreshTrailers = useCallback(async () => {
    const list = await api.get<TrailerSummary[]>("/api/trailers");
    setTrailers(Object.fromEntries(list.map((t) => [t.trailerId, t])));
  }, []);

  const refreshAlerts = useCallback(async () => {
    const r = await api.get<{ alerts: Alert[] }>("/api/alerts?status=active,acknowledged&limit=200");
    setActiveAlerts(r.alerts.filter((a) => a.status !== "resolved"));
  }, []);

  useEffect(() => {
    refreshTrailers().catch(() => undefined);
    refreshAlerts().catch(() => undefined);
    let ws: WebSocket | null = null;
    let timer: number | undefined;
    let ping: number | undefined;
    let closed = false;

    const connect = () => {
      const proto = location.protocol === "https:" ? "wss" : "ws";
      ws = new WebSocket(`${proto}://${location.host}/ws`);
      ws.onopen = () => {
        setConnected(true);
        refreshTrailers().catch(() => undefined);
        refreshAlerts().catch(() => undefined);
        ping = window.setInterval(() => ws?.readyState === 1 && ws.send("ping"), 20000);
      };
      ws.onclose = () => {
        setConnected(false);
        window.clearInterval(ping);
        if (!closed) timer = window.setTimeout(connect, 2000);
      };
      ws.onmessage = (ev) => {
        const msg = JSON.parse(ev.data);
        if (msg.type === "trailer_update") {
          const t = msg.trailer as TrailerSummary;
          setTrailers((prev) => ({ ...prev, [t.trailerId]: { ...prev[t.trailerId], ...t } }));
        } else if (msg.type === "alert" || msg.type === "alert_update") {
          const a = msg.alert as Alert;
          setActiveAlerts((prev) => {
            const rest = prev.filter((x) => x.id !== a.id);
            return a.status === "resolved" ? rest : [a, ...rest];
          });
          listeners.current.forEach((fn) => fn(a, msg.type === "alert"));
        }
      };
    };
    connect();
    return () => {
      closed = true;
      window.clearTimeout(timer);
      window.clearInterval(ping);
      ws?.close();
    };
  }, [refreshTrailers, refreshAlerts]);

  const onAlert = useCallback((fn: Listener) => {
    listeners.current.add(fn);
    return () => void listeners.current.delete(fn);
  }, []);

  const ackAlert = useCallback(async (id: number, by = "manager") => {
    const a = await api.post<Alert>(`/api/alerts/${id}/ack`, { by });
    setActiveAlerts((prev) => prev.map((x) => (x.id === id ? a : x)));
  }, []);

  return (
    <Ctx.Provider value={{ connected, trailers, activeAlerts, onAlert, refreshTrailers, ackAlert }}>
      {children}
    </Ctx.Provider>
  );
}

export function useLive() {
  const v = useContext(Ctx);
  if (!v) throw new Error("useLive outside LiveProvider");
  return v;
}

/** Re-run `fn` on an interval while mounted (used for polling detail views). */
export function useInterval(fn: () => void, ms: number, deps: unknown[] = []) {
  useEffect(() => {
    fn();
    const id = window.setInterval(fn, ms);
    return () => window.clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
}
