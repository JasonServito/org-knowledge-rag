import { defineConfig, devices } from "@playwright/test";

// The browser smoke test (ADR-016 D2; e2e/smoke.spec.ts), in Chromium. It runs the
// built app (`make ui-check` builds it) on port 3001, so a `make ui` dev server on 3000 doesn't
// get in the way.
export default defineConfig({
  testDir: "e2e",
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  use: { baseURL: "http://127.0.0.1:3001" },
  webServer: {
    command: "npx next start --hostname 127.0.0.1 --port 3001",
    url: "http://127.0.0.1:3001",
  },
});
