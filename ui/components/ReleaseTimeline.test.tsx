import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { answers } from "../fixtures";
import { ReleaseTimeline } from "./ReleaseTimeline";

afterEach(cleanup);

// The axis's labels, read from the page.
function axisLabels() {
  return [...document.querySelectorAll(".timeline-axis span")].map((label) => label.textContent);
}

// One citation's bars, read from the page: its grid column, its tooltip, whether it is open.
function bars(chunk: string) {
  const list = screen.getByRole("list", { name: "Release timeline" });
  const row = [...list.querySelectorAll(":scope > li")].find(
    (item) => item.querySelector(".timeline-label")?.textContent === chunk,
  );
  return [...(row?.querySelectorAll<HTMLElement>(".segment") ?? [])].map((bar) => ({
    column: bar.style.gridColumn,
    title: bar.title,
    open: bar.classList.contains("open"),
  }));
}

// Expected values: q31's chunk 5819's windows from the S17-R1 design review, placed by hand on the
// 18-release axis 1.20-1.37 (grid column 1 = 1.20, so a window starting at 1.N starts at column
// N - 19); q19's chunk 47405's windows as answers.json holds them (8 times [1.36, 1.36], then
// [1.36, open]; read with a Python one-off in the T4 run). Since S18-R1 d1 a row draws its
// citation's windows merged: windows that overlap, repeat or follow on make one bar.
describe("the release timeline", () => {
  it("draws q31's chunk 5819's 12 touching windows as 1 bar from 1.24 to the end, still valid", () => {
    render(<ReleaseTimeline evidence={answers.q31.evidence} />);
    expect(axisLabels()).toEqual([
      "1.20", "1.21", "1.22", "1.23", "1.24", "1.25", "1.26", "1.27", "1.28",
      "1.29", "1.30", "1.31", "1.32", "1.33", "1.34", "1.35", "1.36", "1.37",
    ]);
    // 1.24 is column 24 - 19 = 5; 1.24 to 1.37, both ends included, is 37 - 24 + 1 = 14 columns.
    expect(bars("chunk 5819")).toEqual([
      { column: "5 / span 14", title: "1.24 onward, still valid", open: true },
    ]);
  });

  it("draws q19's 8 repeats of 1.36, then 1.36 onward, as 1 bar", () => {
    render(<ReleaseTimeline evidence={answers.q19.evidence} />);
    // 1.36 is column 36 - 19 = 17; 1.36 to 1.37 is 2 columns.
    expect(bars("chunk 47405")).toEqual([
      { column: "17 / span 2", title: "1.36 onward, still valid", open: true },
    ]);
  });

  it("shows a citation with no windows as an empty row", () => {
    render(<ReleaseTimeline evidence={[{ ...answers.q31.evidence[0], release_windows: [] }]} />);
    expect(axisLabels()).toHaveLength(18);
    expect(bars(`chunk ${answers.q31.evidence[0].chunk_id}`)).toEqual([]);
  });
});
