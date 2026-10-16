/**
 * Lightweight analytics/telemetry for Wenjin (问津).
 *
 * Events are POSTed to /api/v1/analytics/events.
 * Offline events are queued in sessionStorage and flushed on next successful send.
 * Search telemetry is metadata-only: query text and filter values never leave the
 * page or enter the queue.
 */

const STORAGE_KEY = "wenjin_analytics_queue:v2";
const LEGACY_STORAGE_KEY = "wenjin_analytics_queue";
const MAX_QUEUE = 50;
const MAX_QUERY_LENGTH = 200;
const SAFE_SEARCH_FILTER_KEYS = new Set(["langPref", "methodFilter", "yearFrom", "yearTo", "method"]);

function sanitizeEventProperties(
  eventName: string,
  properties: Record<string, unknown> | undefined,
): Record<string, unknown> {
  if (eventName === "search") {
    return {
      query_length: typeof properties?.query_length === "number"
        ? Math.max(0, Math.min(Math.trunc(properties.query_length), MAX_QUERY_LENGTH))
        : 0,
      filter_keys: Array.isArray(properties?.filter_keys)
        ? properties.filter_keys.filter(
          (key): key is string => typeof key === "string" && SAFE_SEARCH_FILTER_KEYS.has(key),
        ).slice(0, 10)
        : [],
      result_count: typeof properties?.result_count === "number" && Number.isFinite(properties.result_count)
        ? Math.max(0, Math.min(Math.trunc(properties.result_count), 100_000))
        : 0,
    };
  }
  if (eventName === "page_view") {
    const page = typeof properties?.page === "string" ? properties.page.slice(0, 120) : "";
    const url = typeof properties?.url === "string" ? properties.url.split(/[?#]/, 1)[0].slice(0, 120) : "";
    return { page, url };
  }
  return {};
}

interface AnalyticsEvent {
  event_name: string;
  properties: Record<string, unknown>;
  session_id: string;
  timestamp: string;
}

function getSessionId(): string {
  const storage = getSessionStorage();
  if (!storage) return crypto.randomUUID();
  let sid = storage.getItem("wenjin_sid");
  if (!sid) {
    sid = crypto.randomUUID();
    storage.setItem("wenjin_sid", sid);
  }
  return sid;
}

function getSessionStorage(): Storage | null {
  try {
    return typeof window === "undefined" ? null : window.sessionStorage;
  } catch {
    return null;
  }
}

function removeLegacyPersistentQueue() {
  if (typeof window === "undefined") return;
  try {
    // Remove the pre-v2 persistent queue without reading its contents. Search
    // strings may already be present there from an older build.
    window.localStorage.removeItem(LEGACY_STORAGE_KEY);
  } catch { /* storage unavailable */ }
}

function getOrCreateQueue(): AnalyticsEvent[] {
  removeLegacyPersistentQueue();
  const storage = getSessionStorage();
  if (!storage) return [];
  try {
    const raw = storage.getItem(STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function persistQueue(q: AnalyticsEvent[]) {
  const storage = getSessionStorage();
  if (!storage) return;
  try {
    storage.setItem(STORAGE_KEY, JSON.stringify(q.slice(-MAX_QUEUE)));
  } catch { /* storage full — drop oldest */ }
}

async function flushQueue(): Promise<void> {
  const queue = getOrCreateQueue();
  if (queue.length === 0) return;
  try {
    const resp = await fetch("/api/v1/analytics/events", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ events: queue }),
    });
    if (resp.ok) getSessionStorage()?.removeItem(STORAGE_KEY);
  } catch { /* offline — keep queued */ }
}

async function sendEvent(
  eventName: string,
  properties?: Record<string, unknown>
): Promise<void> {
  const event = {
    event_name: eventName,
    properties: sanitizeEventProperties(eventName, properties),
    session_id: getSessionId(),
    timestamp: new Date().toISOString(),
  };
  // Try flush first (LIFO batch)
  await flushQueue();
  try {
    const resp = await fetch("/api/v1/analytics/events", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ events: [event] }),
    });
    if (!resp.ok) throw new Error("send failed");
  } catch {
    const q = getOrCreateQueue();
    q.push(event);
    persistQueue(q);
  }
}

export function trackEvent(eventName: string, properties?: Record<string, unknown>) {
  sendEvent(eventName, properties).catch(() => { /* fire-and-forget */ });
}

export function trackPageView(pageName: string) {
  trackEvent("page_view", { page: pageName, url: window.location.pathname });
}

export function trackSearch(
  query: string,
  filters: Record<string, unknown>,
  resultCount: number
) {
  const filterKeys = Object.keys(filters)
    .filter((key) => SAFE_SEARCH_FILTER_KEYS.has(key))
    .sort();
  const queryLength = Array.from(query.trim()).length;
  trackEvent("search", {
    query_length: Math.min(queryLength, MAX_QUERY_LENGTH),
    filter_keys: filterKeys,
    result_count: Number.isFinite(resultCount)
      ? Math.max(0, Math.min(Math.trunc(resultCount), 100_000))
      : 0,
  });
}
