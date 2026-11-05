import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { chains } from "../fixtures";
import { ChainView } from "./ChainView";

afterEach(cleanup);

// What each step shows, read from the page, in the page's order.
function shownSteps() {
  const list = screen.getByRole("list", { name: "Steps" });
  return within(list)
    .getAllByRole("listitem")
    .map((item) => ({
      step: item.querySelector(".step-name")?.textContent,
      date: item.querySelector(".step-date")?.textContent,
      document: item.querySelector(".step-source")?.textContent ?? null,
      tier: item.querySelector(".tier")?.textContent ?? null,
      missing: item.querySelector(".missing-reason")?.textContent ?? null,
    }));
}

// Expected values: the S17-R1 design review's evidence (each step's UTC time, document and tier, read
// then from `GET /decisions/{id}` on the local database), shown as S17-R1 c4 says (a T00:00:00Z
// time as the date alone, any other with its UTC hours and minutes) with c8's tier labels; never
// computed by the view. The tests run in America/Edmonton: a local-time date fails them.
describe("the chain view", () => {
  it("shows kep:2572's 6 steps in order, each with its UTC date, document and tier", () => {
    render(<ChainView chain={chains["kep:2572"]} />);

    screen.getByRole("heading", { name: "KEP-2572: Defining the Kubernetes Release Cadence" });
    screen.getByText("kep:2572 · built 2026-10-15 16:42 UTC");
    const discussion = "gh:sig-release/discussions/1290";
    const blog = "web:/blog/2021/07/20/new-kubernetes-release-cadence/";
    expect(shownSteps()).toEqual([
      { step: "problem", date: "2020-10-14 20:36 UTC", document: discussion, tier: "tier 7 · discussion", missing: null },
      { step: "discussion", date: "2020-10-14", document: discussion, tier: "tier 7 · discussion", missing: null },
      { step: "proposal", date: "2021-03-12 14:32 UTC", document: "kep:2572", tier: "tier 5 · KEP (not shipped)", missing: null },
      { step: "decision", date: "2021-04-23 15:38 UTC", document: "gh:enhancements/pull/2567", tier: "tier 7 · discussion", missing: null },
      { step: "implementation", date: "2021-07-20", document: blog, tier: "tier 6 · blog post", missing: null },
      { step: "current_docs", date: "2024-12-11", document: "web:/releases/release/", tier: "tier 2 · release record", missing: null },
    ]);
  });

  it("shows kep:3015's decision step as missing with its reason, and the other 5 dated", () => {
    render(<ChainView chain={chains["kep:3015"]} />);

    const steps = shownSteps();
    expect(steps.map(({ step, date }) => [step, date])).toEqual([
      ["problem", "2021-10-14 13:59 UTC"],
      ["discussion", "2021-10-14"],
      ["proposal", "2025-01-23"],
      ["decision", "—"],
      ["implementation", "2025-07-28 14:42 UTC"],
      ["current_docs", "2026-08-26"],
    ]);
    // A missing step has only its step and reason: no document, tier or link.
    expect(steps[3]).toEqual({ step: "decision", date: "—", document: null, tier: null, missing: "missing: no_link" });
    const decision = within(screen.getByRole("list", { name: "Steps" })).getAllByRole("listitem")[3];
    expect(within(decision).queryByRole("link")).toBeNull();
    expect(steps.filter((step) => step.missing !== null)).toHaveLength(1);
    expect([steps[2].tier, steps[5].tier]).toEqual(["tier 3 · KEP (shipped)", "tier 1 · docs page or feature-gate reference"]);
  });
});
