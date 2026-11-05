// Labels for a citation's badges: pure functions over the API's values.

// ADR-003 D3's tiers (1 = highest), as S17-R1 c8 words them.
const TIERS: Record<number, string> = {
  1: "docs page or feature-gate reference",
  2: "release record",
  3: "KEP (shipped)",
  4: "governance doc",
  5: "KEP (not shipped)",
  6: "blog post",
  7: "discussion",
};

// "tier 6 · blog post"; no tier: a withdrawn, rejected or replaced KEP, or no authority at all.
export function tierLabel(tier: number | null, supersededProposal: boolean): string {
  if (tier === null) {
    return supersededProposal ? "superseded proposal" : "no tier";
  }
  return `tier ${tier} · ${TIERS[tier]}`;
}

// A release window, both ends included: ["1.24", "1.24"] → "1.24"; ["1.28", "1.29"] →
// "1.28–1.29"; a null end is still valid: ["1.30", null] → "1.30 onward".
export function windowLabel([start, end]: [string, string | null]): string {
  if (end === null) {
    return `${start} onward`;
  }
  return start === end ? start : `${start}–${end}`;
}
