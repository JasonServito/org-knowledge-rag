import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { answers } from "../fixtures";
import { AnswerView } from "./AnswerView";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

// What each citation shows, read from the page.
function shownCitations() {
  const list = screen.getByRole("list", { name: "Citations" });
  return within(list)
    .getAllByRole("listitem")
    .map((item) => ({
      chunk: item.querySelector(".chunk")?.textContent,
      section: item.querySelector(".section")?.textContent ?? null,
      tier: item.querySelector(".tier")?.textContent,
      stages: [...item.querySelectorAll(".stage")].map((badge) => badge.textContent),
      windows: [...item.querySelectorAll(".window")].map((badge) => badge.textContent),
    }));
}

// Expected values: the S17-R1 design review's evidence (q25's 7 chunks, all tier 6; q10 0 citations,
// q05 1), the labels of c8, and each citation's section and windows as answers.json holds them
// (read once with a Python one-off, in the T3 brief); never computed by the view. Since S18-R1
// d1 the windows show merged; each merge below is by hand from the windows answers.json holds.
describe("the answer view", () => {
  it("shows q25's 7 citations, each a tier-6 blog post with its windows and chunk number", () => {
    render(<AnswerView answer={answers.q25} />);
    const blog = "tier 6 · blog post";
    expect(shownCitations()).toEqual([
      {
        chunk: "chunk 42549",
        section: "Timeline of changes",
        tier: blog,
        stages: [],
        windows: ["1.29 onward"], // 1.29, 1.29–1.30, 1.30 onward
      },
      { chunk: "chunk 42530", section: null, tier: blog, stages: [], windows: ["1.29–1.30"] }, // 1.29, 1.29–1.30
      { chunk: "chunk 42545", section: null, tier: blog, stages: [], windows: ["1.30 onward"] },
      {
        chunk: "chunk 42276",
        section: "What you need to know about the new package repositories?",
        tier: blog,
        stages: [],
        windows: ["1.29 onward"], // 1.29–1.30, 1.30 onward
      },
      {
        chunk: "chunk 42215",
        section: "What you need to know about the new package repositories?",
        tier: blog,
        stages: [],
        windows: ["1.28–1.29"], // 1.28, 1.28–1.29
      },
      {
        chunk: "chunk 43096",
        section:
          "Graduations, deprecations and removals for Kubernetes v1.29 > Deprecations and removals > Legacy Linux package repositories",
        tier: blog,
        stages: [],
        windows: ["1.29 onward"], // 1.29–1.30, 1.30–1.36, 1.36, 1.36 onward
      },
      {
        chunk: "chunk 42954",
        section: "A note about the Kubernetes community-owned package repositories",
        tier: blog,
        stages: [],
        windows: ["1.28 onward"], // 1.28–1.30, 1.30 onward
      },
    ]);
    // The answer goes through the formatter: q25's "**Removal date.**" shows as bold.
    expect(screen.getByText("Removal date.").tagName).toBe("STRONG");
  });

  it("shows q10's reason and no citations", () => {
    render(<AnswerView answer={answers.q10} />);
    screen.getByText("Insufficient evidence");
    screen.getByText(
      'None of the chunks mentions a "3-Tier Pod Security Proposal" doc or the comments made on it.',
    );
    expect(screen.queryByRole("list", { name: "Citations" })).toBeNull();
    screen.getByText("No citations.");
  });

  it("shows q05's reason and its 1 citation, with the KEP's status and stages", () => {
    render(<AnswerView answer={answers.q05} />);
    screen.getByText("Insufficient evidence");
    screen.getByText(
      "The only chunk about the leads meeting feedback session (33469) just links to external meeting notes. No chunk names who attended or who objected.",
    );
    expect(shownCitations()).toEqual([
      {
        chunk: "chunk 33469",
        section:
          "KEP-2572: Defining the Kubernetes Release Cadence > Implementation History > Leads meeting feedback session",
        tier: "tier 5 · KEP (not shipped)",
        stages: [
          "claimed status: implementable",
          "claimed stage: alpha",
          "effective stage: alpha (low confidence)",
        ],
        windows: ["1.21 onward"],
      },
    ]);
  });

  // Every saved answer (S17's exit check). Expected counts from the S17-R1 design review's evidence:
  // 43 answers, 16 with conflicts, 20 conflicts in all, 223 citations (one timeline row each);
  // and the S18-R1 design review's: merged, the 572 windows are 223, one per citation (one badge and
  // one timeline bar each). React reports a render problem (a repeated key, say) on
  // console.error: none is allowed.
  it("renders all 43 saved answers with no error: 16 conflict panels, 20 conflicts, 223 rows", () => {
    const errors = vi.spyOn(console, "error").mockImplementation(() => {});
    let rendered = 0;
    let panels = 0;
    let conflicts = 0;
    let rows = 0;
    let badges = 0;
    let bars = 0;
    for (const answer of Object.values(answers)) {
      expect(() => render(<AnswerView answer={answer} />)).not.toThrow();
      rendered += 1;
      const panel = document.querySelector('[aria-label="Conflicts"]');
      if (panel !== null) {
        panels += 1;
        conflicts += panel.querySelectorAll(":scope > li").length;
      }
      const timeline = document.querySelector('[aria-label="Release timeline"]');
      rows += timeline?.querySelectorAll(":scope > li").length ?? 0;
      badges += document.querySelectorAll(".badge.window").length;
      bars += document.querySelectorAll(".segment").length;
      cleanup();
    }
    expect({ rendered, panels, conflicts, rows, badges, bars }).toEqual({
      rendered: 43,
      panels: 16,
      conflicts: 20,
      rows: 223,
      badges: 223,
      bars: 223,
    });
    expect(errors).not.toHaveBeenCalled();
  });
});

// The links to the UI's own chain pages (`/decisions/...`), told apart from the citations' title
// links by their href (a title links to its pinned source on GitHub).
function chainLinks(): { chunk: string | null | undefined; href: string | null }[] {
  return screen
    .getAllByRole("link")
    .filter((link) => link.getAttribute("href")?.startsWith("/decisions/"))
    .map((link) => ({
      chunk: link.closest("li")?.querySelector(".chunk")?.textContent,
      href: link.getAttribute("href"),
    }));
}

// ADR-016 D4: a citation whose document is a stored chain's seed links to its chain; no other
// citation does. Expected values: the S17-R1 design review's evidence (q02 cites kep:2572; q18 cites
// kep:4858 only) and q02's 3 citations as answers.json holds them (read with a Python one-off:
// only chunk 33453 is kep:2572's).
describe("the chain links", () => {
  const seeds = ["kep:2572", "kep:3015"];

  it("links q02's kep:2572 citation, and only it, to the chain page", () => {
    render(<AnswerView answer={answers.q02} chainSeeds={seeds} />);
    expect(chainLinks()).toEqual([{ chunk: "chunk 33453", href: "/decisions/kep:2572" }]);
  });

  it("gives q18, which cites kep:4858 only, no chain link", () => {
    render(<AnswerView answer={answers.q18} chainSeeds={seeds} />);
    expect(chainLinks()).toEqual([]);
    expect(screen.getAllByRole("link").length).toBeGreaterThan(0); // its title links remain
  });

  // S18-R1 c1: both of a citation's links open a new tab, so the answer stays on screen.
  it("opens both of q02's kep:2572 citation's links in a new tab", () => {
    render(<AnswerView answer={answers.q02} chainSeeds={seeds} />);
    const citation = within(screen.getByRole("list", { name: "Citations" }))
      .getAllByRole("listitem")
      .find((item) => item.querySelector(".chunk")?.textContent === "chunk 33453");
    const links = [...(citation?.querySelectorAll("a") ?? [])].map((link) => ({
      href: link.getAttribute("href"),
      target: link.getAttribute("target"),
      rel: link.getAttribute("rel"),
    }));
    expect(links).toEqual([
      {
        href: "https://github.com/kubernetes/enhancements/blob/96fd20c76108d86a94abbbe9929cf862bdf82986/keps/sig-release/2572-release-cadence/README.md",
        target: "_blank",
        rel: "noopener noreferrer",
      },
      { href: "/decisions/kep:2572", target: "_blank", rel: "noopener noreferrer" },
    ]);
  });

  it("gives no chain link when no chain is listed", () => {
    render(<AnswerView answer={answers.q02} />);
    expect(chainLinks()).toEqual([]);
  });
});
