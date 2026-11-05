import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import { answers } from "../fixtures";
import { MANIFEST_RELEASES, mergeWindows, placeWindows, releaseAxis } from "./timeline";

// q31's chunk 5819 (web:/docs/reference/access-authn-authz/rbac/), the citation with the most
// windows (12), as the S17-R1 design review read them.
const RBAC_WINDOWS: [string, string | null][] = [
  ["1.24", "1.24"],
  ["1.25", "1.25"],
  ["1.26", "1.26"],
  ["1.27", "1.27"],
  ["1.28", "1.29"],
  ["1.30", "1.31"],
  ["1.32", "1.32"],
  ["1.33", "1.33"],
  ["1.34", "1.34"],
  ["1.35", "1.35"],
  ["1.36", "1.36"],
  ["1.37", null],
];

// The 18 releases 1.20 ... 1.37, written out.
const AXIS = [
  "1.20", "1.21", "1.22", "1.23", "1.24", "1.25", "1.26", "1.27", "1.28",
  "1.29", "1.30", "1.31", "1.32", "1.33", "1.34", "1.35", "1.36", "1.37",
];

describe("the release timeline", () => {
  it("reads q31's chunk 5819 as the design review did", () => {
    const rbac = answers.q31.evidence.find((item) => item.chunk_id === 5819);
    expect(rbac?.release_windows).toEqual(RBAC_WINDOWS);
  });

  it("puts q31's chunk 5819 on the 18-release axis: 12 segments from 1.24 to the end", () => {
    const axis = releaseAxis(RBAC_WINDOWS);
    expect(axis).toEqual(AXIS);
    expect(axis).toHaveLength(18);
    // Placed by hand on the 18 slots (slot 0 = 1.20, slot 17 = 1.37): a window starting at 1.N
    // is at slot N - 20; it covers its start, its end and every release between, so [1.24, 1.24]
    // covers 1 slot and [1.28, 1.29] 2; the open end runs to 1.37, the last slot. Each segment
    // starts where the one before ends: 4+1=5, 5+1=6, 6+1=7, 7+1=8, 8+2=10, 10+2=12, 12+1=13,
    // 13+1=14, 14+1=15, 15+1=16, 16+1=17, and 17+1=18 is the axis's end.
    const placed = placeWindows(RBAC_WINDOWS, axis);
    expect(placed).toEqual([
      { window: ["1.24", "1.24"], slot: 4, span: 1, open: false },
      { window: ["1.25", "1.25"], slot: 5, span: 1, open: false },
      { window: ["1.26", "1.26"], slot: 6, span: 1, open: false },
      { window: ["1.27", "1.27"], slot: 7, span: 1, open: false },
      { window: ["1.28", "1.29"], slot: 8, span: 2, open: false },
      { window: ["1.30", "1.31"], slot: 10, span: 2, open: false },
      { window: ["1.32", "1.32"], slot: 12, span: 1, open: false },
      { window: ["1.33", "1.33"], slot: 13, span: 1, open: false },
      { window: ["1.34", "1.34"], slot: 14, span: 1, open: false },
      { window: ["1.35", "1.35"], slot: 15, span: 1, open: false },
      { window: ["1.36", "1.36"], slot: 16, span: 1, open: false },
      { window: ["1.37", null], slot: 17, span: 1, open: true },
    ]);
    // No gap and no overlap: each segment starts where the one before it ends, and the last
    // ends at the axis's end (slot 18).
    placed.slice(1).forEach((segment, index) => {
      expect(segment.slot).toBe(placed[index].slot + placed[index].span);
    });
    expect(placed[11].slot + placed[11].span).toBe(18);
  });

  it("takes its axis from the corpus manifest, which still says 1.20 to 1.37", () => {
    // A path, not a URL: in the jsdom environment, URL is jsdom's, which Node's fs rejects.
    const manifest = readFileSync(join(import.meta.dirname, "../../config/corpus_manifest.yaml"), "utf8");
    // The `releases:` block: its key's line, then every indented or blank line under it.
    const releases = manifest.match(/^releases:\n((?:[ \t].*\n|\n)*)/m)?.[1] ?? "";
    const first = releases.match(/^[ \t]+first:[ \t]*"([^"]+)"/m)?.[1];
    const latest = releases.match(/^[ \t]+latest:[ \t]*"([^"]+)"/m)?.[1];
    expect({ first, latest }).toEqual({ first: "1.20", latest: "1.37" });
    expect(MANIFEST_RELEASES).toEqual({ first: "1.20", latest: "1.37" });
  });

  it("widens the axis to cover a window outside it, rather than cutting the window", () => {
    // Made up: 1.19 and 1.38 are outside the manifest's range. The axis 1.19 ... 1.38 holds 20
    // releases; [1.19, 1.21] is at slot 0 and covers 3; [1.38, open] is at slot 19, the last.
    const windows: [string, string | null][] = [
      ["1.19", "1.21"],
      ["1.38", null],
    ];
    const axis = releaseAxis(windows);
    expect([axis[0], axis[19], axis.length]).toEqual(["1.19", "1.38", 20]);
    expect(placeWindows(windows, axis)).toEqual([
      { window: ["1.19", "1.21"], slot: 0, span: 3, open: false },
      { window: ["1.38", null], slot: 19, span: 1, open: true },
    ]);
  });
});

// Expected values: the S18-R1 contract's cases (decision d1), merged by hand. A window covers its
// start and end releases and every release between; one that starts at or before the release
// after the current end (an overlap, a repeat, or "follows on") joins it; an open end absorbs
// every later window; a real gap stays.
describe("merging a citation's release windows (S18-R1 d1)", () => {
  it("joins exact repeats and an overlap: chunk 37576's 1.21, 1.21, 1.21-1.30 is 1.21-1.30", () => {
    expect(
      mergeWindows([
        ["1.21", "1.21"],
        ["1.21", "1.21"],
        ["1.21", "1.30"],
      ]),
    ).toEqual([["1.21", "1.30"]]);
  });

  it("joins windows that follow on: 1.24 then 1.25 is 1.24-1.25", () => {
    expect(
      mergeWindows([
        ["1.24", "1.24"],
        ["1.25", "1.25"],
      ]),
    ).toEqual([["1.24", "1.25"]]);
  });

  it("joins q31's chunk 5819's 12 windows into one, from 1.24 and still valid", () => {
    expect(mergeWindows(RBAC_WINDOWS)).toEqual([["1.24", null]]);
  });

  it("keeps a real gap: 1.24-1.25 then 1.27 onward stays 2 windows (1.26 is missing)", () => {
    const gap: [string, string | null][] = [
      ["1.24", "1.25"],
      ["1.27", null],
    ];
    expect(mergeWindows(gap)).toEqual(gap);
  });

  it("lets an open end absorb every later window: 1.20 onward, then 1.25-1.30", () => {
    expect(
      mergeWindows([
        ["1.20", null],
        ["1.25", "1.30"],
      ]),
    ).toEqual([["1.20", null]]);
  });

  it("keeps the later end when a window lies inside the one before it", () => {
    // Made up: 1.22-1.25 lies inside 1.20-1.30, so the merged end stays 1.30.
    expect(
      mergeWindows([
        ["1.20", "1.30"],
        ["1.22", "1.25"],
      ]),
    ).toEqual([["1.20", "1.30"]]);
  });

  it("compares releases as numbers: 1.9 then 1.10 follow on", () => {
    // Made up: as strings "1.10" < "1.9", so a string compare would not join them.
    expect(
      mergeWindows([
        ["1.9", "1.9"],
        ["1.10", "1.10"],
      ]),
    ).toEqual([["1.9", "1.10"]]);
  });

  it("returns no windows for none", () => {
    expect(mergeWindows([])).toEqual([]);
  });

  // Expected counts: the S18-R1 design review's evidence (a one-off Python script over the run's
  // questions.jsonl, which answers.json copies): 223 citations, 572 windows; merging changes 116
  // citations and leaves 223 windows, 1 per citation (0 with a gap).
  it("merges the 43 saved answers' 572 windows into 223, 1 per citation", () => {
    const citations = Object.values(answers).flatMap((answer) => answer.evidence);
    const merged = citations.map((item) => mergeWindows(item.release_windows));
    const changed = citations.filter((item, index) => merged[index].length !== item.release_windows.length);
    expect({
      citations: citations.length,
      before: citations.reduce((total, item) => total + item.release_windows.length, 0),
      after: merged.reduce((total, windows) => total + windows.length, 0),
      changed: changed.length,
      withGap: merged.filter((windows) => windows.length > 1).length,
    }).toEqual({ citations: 223, before: 572, after: 223, changed: 116, withGap: 0 });
  });
});
