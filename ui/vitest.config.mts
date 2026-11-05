import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// The UI shows dates in UTC (S17-R1 c4). Tests run in a zone 6-7 hours behind it, so a date
// shown in local time fails a test. Set before the test workers start, which inherit it.
process.env.TZ = "America/Edmonton";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    // Only `*.test.*`: Playwright's `*.spec.ts` files (e2e/) run in `make ui-e2e`.
    include: ["**/*.test.{ts,tsx}"],
  },
});
