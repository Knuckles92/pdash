"use client";

/**
 * One-EventSource-per-app realtime fan-out (Phase 5).
 *
 * - A single ``EventSource`` for the entire app, listening to the union of
 *   subscribed channels.
 * - Consumers register via ``useChannel(channel, handler)``; we close and
 *   reopen the EventSource whenever the topic set changes (per PLAN).
 * - Always-on channels: ``approvals`` and ``pages`` (the sidebar pending
 *   badge + page list need them).
 * - On ``resync_required``, any handler registered as a refetch callback for
 *   the affected channel is invoked.
 * - Browser handles reconnect + ``Last-Event-Id`` automatically; we expose a
 *   coarse ``status`` for the optional debug indicator.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";

export type RealtimeStatus = "connecting" | "open" | "reconnecting" | "offline";

export type RealtimeEvent = {
  // SSE ``event`` field (e.g. "module_added").
  kind: string;
  // From the ``data`` JSON envelope.
  topic: string;
  ts: string;
  payload: Record<string, unknown>;
  id: number | null;
};

export type Handler = (ev: RealtimeEvent) => void;

const ALWAYS_ON: ReadonlySet<string> = new Set(["approvals", "pages"]);

type RealtimeContextValue = {
  status: RealtimeStatus;
  subscribe(channel: string, handler: Handler): () => void;
};

const RealtimeContext = createContext<RealtimeContextValue>({
  status: "offline",
  subscribe: () => () => {},
});

export function RealtimeProvider({ children }: { children: ReactNode }) {
  const handlersRef = useRef<Map<string, Set<Handler>>>(new Map());
  // Tracks topics that should be in the EventSource URL.
  const subscribedTopicsRef = useRef<Set<string>>(new Set(ALWAYS_ON));
  // Current EventSource instance.
  const esRef = useRef<EventSource | null>(null);
  const [status, setStatus] = useState<RealtimeStatus>("connecting");
  // Bump this when we want to force a recompute of the EventSource.
  const [topicsVersion, setTopicsVersion] = useState(0);

  const closeConnection = useCallback(() => {
    if (esRef.current) {
      try {
        esRef.current.close();
      } catch {
        /* ignore */
      }
      esRef.current = null;
    }
  }, []);

  const openConnection = useCallback((topics: string[]) => {
    closeConnection();
    if (topics.length === 0) {
      setStatus("offline");
      return;
    }
    const url = `/api/v1/events?topics=${encodeURIComponent(topics.join(","))}`;
    setStatus("connecting");
    let es: EventSource;
    try {
      es = new EventSource(url, { withCredentials: true });
    } catch (err) {
      console.warn("[realtime] failed to construct EventSource", err);
      setStatus("offline");
      return;
    }
    esRef.current = es;
    es.onopen = () => {
      setStatus("open");
    };
    es.onerror = () => {
      // EventSource auto-reconnects; we just reflect the transient state.
      setStatus("reconnecting");
    };
    // Generic envelope handler — fires on every event (named or default).
    const dispatch = (ev: MessageEvent, kind: string) => {
      let parsed: { topic?: string; ts?: string; payload?: Record<string, unknown> } = {};
      try {
        parsed = JSON.parse(ev.data) as typeof parsed;
      } catch {
        return;
      }
      const topic = parsed.topic ?? "";
      const ts = parsed.ts ?? "";
      const payload = parsed.payload ?? {};
      const idNum = ev.lastEventId ? Number(ev.lastEventId) : null;
      const env: RealtimeEvent = {
        kind,
        topic,
        ts,
        payload,
        id: idNum != null && !Number.isNaN(idNum) ? idNum : null,
      };
      // Fan to topic-specific handlers AND any wildcard ones registered as
      // ``"*"``.
      const invoke = (set?: Set<Handler>) => {
        if (!set) return;
        for (const h of set) {
          try {
            h(env);
          } catch (e) {
            console.warn("[realtime] handler threw", e);
          }
        }
      };
      invoke(handlersRef.current.get(topic));
      invoke(handlersRef.current.get("*"));
    };
    // Listen for known event names + a generic "message" fallback (the SSE
    // default if the server omits ``event:``, which never happens here but
    // costs nothing to defend against).
    const KNOWN_EVENTS = [
      "approval_pending",
      "approval_decided",
      "module_added",
      "module_updated",
      "module_removed",
      "modules_reordered",
      "page_added",
      "page_updated",
      "page_removed",
      "log_appended",
      "activity_appended",
      "resync_required",
    ];
    for (const name of KNOWN_EVENTS) {
      es.addEventListener(name, (ev) => dispatch(ev as MessageEvent, name));
    }
    es.onmessage = (ev) => dispatch(ev, "message");
  }, [closeConnection]);

  // Recompute topics + reopen whenever subscriptions change.
  useEffect(() => {
    const topics = Array.from(subscribedTopicsRef.current).sort();
    openConnection(topics);
    return () => {
      closeConnection();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [topicsVersion]);

  const subscribe = useCallback((channel: string, handler: Handler) => {
    const map = handlersRef.current;
    let set = map.get(channel);
    if (!set) {
      set = new Set();
      map.set(channel, set);
    }
    set.add(handler);
    const wasNew = !subscribedTopicsRef.current.has(channel);
    if (wasNew && channel !== "*") {
      subscribedTopicsRef.current.add(channel);
      setTopicsVersion((v) => v + 1);
    }
    return () => {
      const s = map.get(channel);
      if (s) {
        s.delete(handler);
        if (s.size === 0) {
          map.delete(channel);
          if (channel !== "*" && !ALWAYS_ON.has(channel)) {
            subscribedTopicsRef.current.delete(channel);
            setTopicsVersion((v) => v + 1);
          }
        }
      }
    };
  }, []);

  return (
    <RealtimeContext.Provider value={{ status, subscribe }}>
      {children}
      <ConnectionPill status={status} />
    </RealtimeContext.Provider>
  );
}

export function useRealtime(): RealtimeContextValue {
  return useContext(RealtimeContext);
}

/**
 * Subscribe to one realtime channel for the lifetime of the consumer.
 * The handler is wrapped in a ref so callers can declare it inline without
 * re-subscribing on every render.
 */
export function useChannel(channel: string, handler: Handler): void {
  const { subscribe } = useRealtime();
  const ref = useRef(handler);
  ref.current = handler;
  useEffect(() => {
    return subscribe(channel, (ev) => ref.current(ev));
  }, [channel, subscribe]);
}

function ConnectionPill({ status }: { status: RealtimeStatus }) {
  const [dismissed, setDismissed] = useState(false);
  useEffect(() => {
    if (status === "open") setDismissed(false);
  }, [status]);
  if (status === "open" || status === "connecting" || dismissed) return null;
  return (
    <button
      type="button"
      onClick={() => setDismissed(true)}
      aria-label="Realtime connection status — dismiss"
      className="fixed z-50 rounded-full bg-amber-500/90 text-white text-xs px-3 py-1 shadow
                 bottom-4 right-4
                 max-md:bottom-auto max-md:right-2 max-md:top-2"
    >
      {status === "reconnecting" ? "reconnecting…" : "offline"}
    </button>
  );
}
