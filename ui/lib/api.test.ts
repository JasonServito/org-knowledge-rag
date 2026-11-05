import { afterEach, describe, expect, it, vi } from "vitest";

import { askQuestion, getDecision, listDecisions } from "./api";

// Stands in for the browser's fetch: answers a copy of `response` (a body can be read only
// once), or fails with it.
function stubFetch(response: Response | Error) {
  const fetch = vi.fn(async () => {
    if (response instanceof Error) {
      throw response;
    }
    return response.clone();
  });
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("the API client", () => {
  it("posts the question to /api/query and returns the parsed body", async () => {
    const fetch = stubFetch(Response.json({ question: "Why?" }));
    expect(await askQuestion("Why?")).toEqual({ ok: true, data: { question: "Why?" } });
    expect(fetch).toHaveBeenCalledWith(
      "/api/query",
      expect.objectContaining({ method: "POST", body: '{"question":"Why?"}' }),
    );
  });

  it("gets the chains from /api/decisions and one from /api/decisions/<id>", async () => {
    const fetch = stubFetch(Response.json([]));
    await listDecisions();
    await getDecision("kep:2572");
    // The id is URL-encoded; the forwarder and the API read "kep%3A2572" as "kep:2572".
    expect(fetch.mock.calls.map((call: unknown[]) => call[0])).toEqual([
      "/api/decisions",
      "/api/decisions/kep%3A2572",
    ]);
  });

  it("returns the API's status, code and request ID, never its message", async () => {
    const envelope = {
      error: { code: "upstream_failed", message: "Voyage 401 provider text", request_id: "abc123" },
    };
    stubFetch(Response.json(envelope, { status: 502 }));
    const result = await askQuestion("Why?");
    expect(result).toEqual({
      ok: false,
      failure: { kind: "api", status: 502, code: "upstream_failed", requestId: "abc123" },
    });
    expect(JSON.stringify(result)).not.toContain("Voyage");
  });

  it("reads the forwarder's own plain-text 500 as no answer from the API", async () => {
    stubFetch(new Response("Internal Server Error", { status: 500 }));
    expect(await getDecision("kep:2572")).toEqual({
      ok: false,
      failure: { kind: "network", status: 500 },
    });
  });

  it("reads a failed fetch as no answer from the API", async () => {
    stubFetch(new TypeError("Failed to fetch"));
    expect(await askQuestion("Why?")).toEqual({
      ok: false,
      failure: { kind: "network", status: null },
    });
  });
});
