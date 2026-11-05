import { afterEach, describe, expect, it, vi } from "vitest";

import { readSettings } from "./settings";

// Expected values from the S17-R1 contract (c15), not from the code under test.
describe("readSettings", () => {
  it("defaults to the local API and 120 s", () => {
    expect(readSettings({})).toEqual({ apiBaseUrl: "http://127.0.0.1:8000", apiTimeoutS: 120 });
  });

  it("takes API_BASE_URL and API_TIMEOUT_S from the environment", () => {
    const env = { API_BASE_URL: "http://127.0.0.1:9000", API_TIMEOUT_S: "300" };
    expect(readSettings(env)).toEqual({ apiBaseUrl: "http://127.0.0.1:9000", apiTimeoutS: 300 });
  });

  it("refuses a timeout that isn't a number of seconds above 0", () => {
    // 0 matters: Next would read a 0 ms proxy timeout as its 30 s default.
    expect(() => readSettings({ API_TIMEOUT_S: "abc" })).toThrow("API_TIMEOUT_S");
    expect(() => readSettings({ API_TIMEOUT_S: "0" })).toThrow("API_TIMEOUT_S");
  });
});

describe("next.config", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("forwards /api/* to API_BASE_URL, with API_TIMEOUT_S as the proxy timeout in ms", async () => {
    vi.stubEnv("API_BASE_URL", "http://127.0.0.1:9000");
    vi.stubEnv("API_TIMEOUT_S", "300");
    // Imported after the stubs: the config reads the environment when it loads.
    const config = (await import("../next.config")).default;
    expect(await config.rewrites?.()).toEqual([
      { source: "/api/:path*", destination: "http://127.0.0.1:9000/:path*" },
    ]);
    expect(config.experimental?.proxyTimeout).toBe(300_000);
  });
});
