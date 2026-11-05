import { describe, expect, it } from "vitest";

import { utcDate } from "./dates";

// Expected values typed by hand from the times (S17-R1 c4: dates in UTC; a day-only time,
// T00:00:00Z, as the date alone). The tests run in America/Edmonton (vitest.config.mts), 6-7
// hours behind UTC, so a formatter that used local time would show the day before for the
// midnights below.
describe("utcDate", () => {
  it("shows a day-only time (midnight UTC) as the date alone", () => {
    expect(utcDate("2020-10-14T00:00:00Z")).toBe("2020-10-14");
  });

  it("shows any other time as its UTC date, hours and minutes", () => {
    expect(utcDate("2020-10-14T20:36:05Z")).toBe("2020-10-14 20:36 UTC");
    // The API's microseconds (a chain's built_at).
    expect(utcDate("2026-10-15T16:42:36.520397Z")).toBe("2026-10-15 16:42 UTC");
  });

  it("converts a time given with another offset to UTC", () => {
    expect(utcDate("2021-04-23T21:38:03+06:00")).toBe("2021-04-23 15:38 UTC");
    expect(utcDate("2021-07-19T18:00:00-06:00")).toBe("2021-07-20");
  });
});
