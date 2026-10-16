/**
 * Offline Queue Service — session-scoped queue for interview sessions.
 *
 * Interview transcripts are sensitive. They are kept in sessionStorage rather
 * than localStorage, namespaced by the current user/guest scope, expired after
 * a bounded period, and cleared on logout. The queue is intentionally not
 * cached by the service worker.
 */

import config from "../config";
import { getAccessToken } from "../api/client";
import { getAuthHeaders } from "../utils/authFetch";

const STORAGE_PREFIX = "wenjin_offline_queue:v2:";
const LEGACY_STORAGE_KEY = "wenjin_offline_queue";
const MAX_QUEUE = 100;
const QUEUE_TTL_MS = 72 * 60 * 60 * 1000;

export interface QueuedSession {
  /** Unique client-generated ID for dedup */
  client_id: string;
  /** Endpoint to POST to (e.g. "/fieldwork/sessions") */
  endpoint: string;
  /** Request body */
  payload: Record<string, any>;
  /** ISO timestamp when queued */
  queued_at: string;
  /** ISO timestamp after which the item is discarded */
  expires_at: string;
  /** Number of retry attempts */
  retries: number;
}

let isOnline = typeof navigator !== "undefined" ? navigator.onLine : true;

function safeStorage(kind: "sessionStorage" | "localStorage"): Storage | null {
  try {
    return typeof window !== "undefined" ? window[kind] : null;
  } catch {
    return null;
  }
}

function getProfileScope(): string | null {
  const storage = safeStorage("localStorage");
  if (!storage) return null;
  try {
    const profile = JSON.parse(storage.getItem("user_profile") || "null");
    return profile?.id ? `profile:${String(profile.id)}` : null;
  } catch {
    return null;
  }
}

function getGuestScope(): string | null {
  const storage = safeStorage("localStorage");
  if (!storage) return null;
  try {
    const guest = JSON.parse(storage.getItem("wenjin_guest") || "null");
    return guest?.guestId ? `guest:${String(guest.guestId)}` : null;
  } catch {
    return null;
  }
}

function getTokenSubject(): string | null {
  const token = getAccessToken();
  if (!token || token === "guest") return null;
  try {
    const segment = token.split(".")[1];
    if (!segment) return null;
    const payload = JSON.parse(atob(segment.replace(/-/g, "+").replace(/_/g, "/")));
    return payload?.sub ? `user:${String(payload.sub)}` : null;
  } catch {
    return null;
  }
}

function getStorageScope(): string {
  return getTokenSubject() || getProfileScope() || getGuestScope() || "anonymous";
}

function getStorageKey(scope: string = getStorageScope()): string {
  return `${STORAGE_PREFIX}${scope.replace(/[^a-zA-Z0-9:_-]/g, "_")}`;
}

function discardLegacyQueue() {
  // The pre-v2 queue had no owner scope. It cannot be safely attributed after
  // an account switch, so the release removes it rather than risking leakage.
  try { safeStorage("localStorage")?.removeItem(LEGACY_STORAGE_KEY); } catch { /* best effort */ }
}

function parseQueue(raw: string | null): QueuedSession[] {
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    const now = Date.now();
    return parsed.filter((item): item is QueuedSession => {
      if (!item || typeof item !== "object" || typeof item.endpoint !== "string") return false;
      const queuedAt = Date.parse(String(item.queued_at || ""));
      if (!Number.isFinite(queuedAt)) return false;
      const expiresAt = Date.parse(String(item.expires_at || ""));
      return Number.isFinite(expiresAt) ? expiresAt > now : now - queuedAt < QUEUE_TTL_MS;
    });
  } catch {
    return [];
  }
}

function getQueue(): QueuedSession[] {
  const storage = safeStorage("sessionStorage");
  if (!storage) return [];
  const scope = getStorageScope();
  const queue = parseQueue(storage.getItem(getStorageKey(scope)));
  const key = getStorageKey(scope);
  try {
    storage.setItem(key, JSON.stringify(queue.slice(-MAX_QUEUE)));
  } catch { /* storage unavailable or full; enqueue will report a normal failure */ }
  return queue;
}

function persistQueue(queue: QueuedSession[]) {
  const storage = safeStorage("sessionStorage");
  if (!storage) return;
  try {
    storage.setItem(getStorageKey(), JSON.stringify(queue.slice(-MAX_QUEUE)));
  } catch {
    // Keep the newest half if a browser session quota is reached.
    try {
      storage.setItem(getStorageKey(), JSON.stringify(queue.slice(-Math.floor(MAX_QUEUE / 2))));
    } catch { /* best effort; caller still has the in-memory result */ }
  }
}

/** Remove the old unscoped queue and all session-scoped draft queues. */
export function clearOfflineQueue() {
  const session = safeStorage("sessionStorage");
  if (session) {
    try {
      for (let i = session.length - 1; i >= 0; i -= 1) {
        const key = session.key(i);
        if (key?.startsWith(STORAGE_PREFIX)) session.removeItem(key);
      }
    } catch { /* best effort */ }
  }
  // Remove the pre-v2 unscoped transcript queue so it cannot cross accounts.
  discardLegacyQueue();
}

function updateOnlineStatus() {
  const wasOffline = !isOnline;
  isOnline = navigator.onLine;
  if (wasOffline && isOnline) flushQueue().catch(() => {});
}

if (typeof window !== "undefined") {
  discardLegacyQueue();
  window.addEventListener("online", updateOnlineStatus);
  window.addEventListener("offline", () => { isOnline = false; });
}

/** Enqueue a session for later sync. Tries immediate send first; queues on failure. */
export async function enqueueSession(
  endpoint: string,
  payload: Record<string, any>,
): Promise<{ queued: boolean; client_id: string }> {
  const client_id = crypto.randomUUID();
  const apiBase = config.apiBaseUrl || "";

  if (isOnline) {
    try {
      const resp = await fetch(`${apiBase}/api/v1${endpoint}`, {
        method: "POST",
        headers: { ...getAuthHeaders() },
        credentials: "include",
        body: JSON.stringify(payload),
      });
      if (resp.ok) return { queued: false, client_id };
    } catch { /* queue below */ }
  }

  const queuedAt = new Date();
  const queue = getQueue();
  queue.push({
    client_id,
    endpoint,
    payload,
    queued_at: queuedAt.toISOString(),
    expires_at: new Date(queuedAt.getTime() + QUEUE_TTL_MS).toISOString(),
    retries: 0,
  });
  persistQueue(queue);
  return { queued: true, client_id };
}

/** Flush queued sessions. Authentication failures remain queued for re-login. */
export async function flushQueue(): Promise<{ flushed: number; failed: number }> {
  const queue = getQueue();
  if (queue.length === 0) return { flushed: 0, failed: 0 };

  let flushed = 0;
  let failed = 0;
  const remaining: QueuedSession[] = [];
  const apiBase = config.apiBaseUrl || "";

  for (const item of queue) {
    try {
      const resp = await fetch(`${apiBase}/api/v1${item.endpoint}`, {
        method: "POST",
        headers: { ...getAuthHeaders() },
        credentials: "include",
        body: JSON.stringify(item.payload),
      });
      if (resp.ok || (resp.status >= 400 && resp.status < 500 && resp.status !== 401 && resp.status !== 403)) {
        flushed++;
      } else {
        item.retries++;
        if (item.retries < 5) remaining.push(item);
        else failed++;
      }
    } catch {
      item.retries++;
      if (item.retries < 5) remaining.push(item);
      else failed++;
    }
  }

  persistQueue(remaining);
  return { flushed, failed };
}

export function getQueueSize(): number {
  return getQueue().length;
}

export function getOnlineStatus(): boolean {
  return isOnline;
}

let flushTimer: ReturnType<typeof setInterval> | null = null;

export function startAutoFlush(intervalMs: number = 60000) {
  if (flushTimer) return;
  flushTimer = setInterval(() => {
    if (getQueue().length === 0) { stopAutoFlush(); return; }
    if (isOnline) flushQueue().catch(() => {});
  }, intervalMs);
}

export function stopAutoFlush() {
  if (flushTimer) { clearInterval(flushTimer); flushTimer = null; }
}
