import { expect, it } from "vitest";

// vitest.config.ts sets the zone (S17-R1 c4); later tests rely on it to catch local-time dates.
it("runs the tests in America/Edmonton", () => {
  expect(Intl.DateTimeFormat().resolvedOptions().timeZone).toBe("America/Edmonton");
  expect(new Date("2020-10-14T00:00:00Z").getDate()).toBe(13); // the day before, locally
});
