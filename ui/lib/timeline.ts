// The release timeline's positions (S17-R1 c7): pure functions over the citations' release
// windows. The axis has one slot per release; a window covers the slots from its start release
// to its end release, both ends included, so ["1.24", "1.24"] covers 1 slot. A null end is
// still valid: it runs to the axis's end. The component draws slot n as grid column n + 1.

import type { Evidence } from "./types";

export type ReleaseWindow = Evidence["release_windows"][number];

// The axis: the corpus manifest's release range, the same for every answer
// (config/corpus_manifest.yaml, `releases.first` and `releases.latest`; a test checks they agree).
export const MANIFEST_RELEASES = { first: "1.20", latest: "1.37" };

// One window's place on the axis.
export type Segment = {
  window: ReleaseWindow;
  slot: number; // the slot of its start release: 0 is the axis's first release
  span: number; // how many releases it covers, both ends included
  open: boolean; // a null end: still valid, so it runs to the axis's end
};

// A release's minor: "1.24" → 24. Releases are consecutive minors 1.N.
function minor(release: string): number {
  return Number(release.split(".")[1]);
}

// The axis's releases, in order: the manifest's range, "1.20" ... "1.37". A window outside it
// (a later release, say) widens the axis to cover it, so no window is dropped or cut.
export function releaseAxis(windows: ReleaseWindow[]): string[] {
  const named = windows.flatMap(([start, end]) => (end === null ? [start] : [start, end]));
  const first = Math.min(minor(MANIFEST_RELEASES.first), ...named.map(minor));
  const last = Math.max(minor(MANIFEST_RELEASES.latest), ...named.map(minor));
  return Array.from({ length: last - first + 1 }, (_, index) => `1.${first + index}`);
}

// A citation's windows as the UI shows them (S18-R1 d1), for its badges and its timeline row:
// windows that overlap, repeat or follow on (the next starts at the release after the previous
// ends: 1.24-1.24 then 1.25-1.25) are joined into one, since "valid in" means the releases that
// held the text; a real gap (1.24-1.25 then 1.27 onward: 1.26 is missing) stays. An open end
// (null) absorbs every later window. The API sends a citation's windows sorted by their start
// release (db/retrieval.py), which this relies on; the API's own values are unchanged.
export function mergeWindows(windows: ReleaseWindow[]): ReleaseWindow[] {
  const merged: ReleaseWindow[] = [];
  for (const [start, end] of windows) {
    const last = merged.at(-1);
    if (last === undefined) {
      merged.push([start, end]); // the first window
    } else if (last[1] === null) {
      continue; // the joined window is still valid: it already covers this one
    } else if (minor(start) > minor(last[1]) + 1) {
      merged.push([start, end]); // a gap before it: a new window
    } else if (end === null || minor(end) > minor(last[1])) {
      last[1] = end; // it overlaps or follows on, and ends later: the joined window ends with it
    }
  }
  return merged;
}

// Each window's segment on `axis` (from `releaseAxis`), in the given order. Windows are placed as
// given (the component passes them through `mergeWindows` first).
export function placeWindows(windows: ReleaseWindow[], axis: string[]): Segment[] {
  const first = minor(axis[0]);
  const last = minor(axis[axis.length - 1]);
  return windows.map((window) => {
    const [start, end] = window;
    const from = minor(start);
    const to = end === null ? last : minor(end);
    return { window, slot: from - first, span: to - from + 1, open: end === null };
  });
}
