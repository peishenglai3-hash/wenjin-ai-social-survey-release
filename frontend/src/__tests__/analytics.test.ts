import { beforeEach, describe, expect, it, vi } from "vitest";
import { trackEvent, trackSearch } from "../utils/analytics";

describe("analytics search privacy boundary", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
    window.sessionStorage.clear();
    vi.stubGlobal("fetch", vi.fn());
  });

  it("sends metadata only and never includes raw search values", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValue({ ok: true } as Response);
    const query = "涉及家庭暴力的访谈关键词";

    trackSearch(
      query,
      {
        langPref: "zh",
        methodFilter: "grounded_theory",
        yearFrom: "2020",
        secretFilter: "should-not-be-included",
      },
      4,
    );

    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const requestBody = JSON.parse(String(fetchMock.mock.calls[0][1]?.body));
    const properties = requestBody.events[0].properties;

    expect(properties).toEqual({
      query_length: Array.from(query).length,
      filter_keys: ["langPref", "methodFilter", "yearFrom"],
      result_count: 4,
    });
    expect(JSON.stringify(requestBody)).not.toContain(query);
    expect(JSON.stringify(requestBody)).not.toContain("grounded_theory");
    expect(window.localStorage.getItem("wenjin_analytics_queue")).toBeNull();
  });

  it("queues only sanitized metadata in sessionStorage and removes the legacy persistent queue", async () => {
    window.localStorage.setItem(
      "wenjin_analytics_queue",
      JSON.stringify([{ properties: { query: "old private search" } }]),
    );
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockRejectedValue(new Error("offline"));

    trackSearch("private interview transcript", { methodFilter: "sensitive" }, 0);

    await vi.waitFor(() =>
      expect(window.sessionStorage.getItem("wenjin_analytics_queue:v2")).not.toBeNull(),
    );
    const queued = window.sessionStorage.getItem("wenjin_analytics_queue:v2");

    expect(queued).not.toContain("private interview transcript");
    expect(queued).not.toContain("sensitive");
    expect(window.localStorage.getItem("wenjin_analytics_queue")).toBeNull();
  });

  it("drops properties from unsupported event types", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValue({ ok: true } as Response);

    trackEvent("custom_event", { transcript: "private content", secret: "value" });

    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const requestBody = JSON.parse(String(fetchMock.mock.calls[0][1]?.body));
    expect(requestBody.events[0].properties).toEqual({});
    expect(JSON.stringify(requestBody)).not.toContain("private content");
  });
});
