// Dates as the UI shows them (S17-R1 c4): always in UTC, whatever the browser's time zone.

// An API time (ISO 8601 with its offset) as its UTC date: "2020-10-14T00:00:00Z" → "2020-10-14",
// a day-only time (a source that gives only the day); any other time with its UTC hours and
// minutes: "2020-10-14T20:36:05Z" → "2020-10-14 20:36 UTC". `toISOString` is always in UTC.
export function utcDate(time: string): string {
  const [date, clock] = new Date(time).toISOString().split("T"); // "2020-10-14", "20:36:05.000Z"
  return clock === "00:00:00.000Z" ? date : `${date} ${clock.slice(0, 5)} UTC`;
}
