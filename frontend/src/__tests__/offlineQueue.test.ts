import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../api/client", () => ({
  getAccessToken: vi.fn(() => null),
}));

import {
  clearOfflineQueue,
  enqueueSession,
  flushQueue,
  getQueueSize,
} from "../services/offlineQueue";

const fetchMock = vi.fn();
globalThis.fetch = fetchMock;

describe("offline interview queue", () => {
  beforeEach(() => {
    clearOfflineQueue();
    window.sessionStorage.clear();
    window.localStorage.clear();
    fetchMock.mockReset();
  });

  it("stores sensitive drafts in scoped sessionStorage, not legacy localStorage", async () => {
    fetchMock.mockRejectedValue(new Error("offline"));

    const result = await enqueueSession("/fieldwork/sessions", {
      transcript_text: "受访者内容",
    });

    expect(result.queued).toBe(true);
    expect(getQueueSize()).toBe(1);
    expect(window.localStorage.getItem("wenjin_offline_queue")).toBeNull();
    expect(Object.keys(window.sessionStorage).some((key) => key.startsWith("wenjin_offline_queue:v2:"))).toBe(true);
    expect(fetchMock.mock.calls[0][1]).toMatchObject({ credentials: "include" });
  });

  it("keeps queued work after an authentication failure", async () => {
    fetchMock.mockResolvedValueOnce({ ok: false, status: 503 });
    await enqueueSession("/fieldwork/sessions", { transcript_text: "draft" });

    fetchMock.mockResolvedValueOnce({ ok: false, status: 401 });
    const result = await flushQueue();

    expect(result).toEqual({ flushed: 0, failed: 0 });
    expect(getQueueSize()).toBe(1);
  });

  it("expires stale drafts and clears all queue scopes", async () => {
    window.sessionStorage.setItem(
      "wenjin_offline_queue:v2:anonymous",
      JSON.stringify([{
        client_id: "old",
        endpoint: "/fieldwork/sessions",
        payload: { transcript_text: "stale" },
        queued_at: "2020-01-01T00:00:00.000Z",
        expires_at: "2020-01-02T00:00:00.000Z",
        retries: 0,
      }]),
    );

    expect(getQueueSize()).toBe(0);
    await enqueueSession("/fieldwork/sessions", { transcript_text: "new" });
    expect(getQueueSize()).toBe(1);
    clearOfflineQueue();
    expect(Object.keys(window.sessionStorage).filter((key) => key.startsWith("wenjin_offline_queue:v2:"))).toHaveLength(0);
    expect(getQueueSize()).toBe(0);
  });
});
