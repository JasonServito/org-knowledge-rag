import { expect, it } from "vitest";

import { tierLabel } from "./labels";

// Expected labels: S17-R1 c8, from ADR-003 D3's tier table.
it("names each authority tier as ADR-003 D3 does", () => {
  expect([1, 2, 3, 4, 5, 6, 7].map((tier) => tierLabel(tier, false))).toEqual([
    "tier 1 · docs page or feature-gate reference",
    "tier 2 · release record",
    "tier 3 · KEP (shipped)",
    "tier 4 · governance doc",
    "tier 5 · KEP (not shipped)",
    "tier 6 · blog post",
    "tier 7 · discussion",
  ]);
  expect(tierLabel(null, true)).toBe("superseded proposal");
  expect(tierLabel(null, false)).toBe("no tier");
});
