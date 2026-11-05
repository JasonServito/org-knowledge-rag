import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { answers } from "../fixtures";
import { ConflictPanel } from "./ConflictPanel";

afterEach(cleanup);

// What each conflict shows, read from the page.
function shownConflicts() {
  const list = screen.getByRole("list", { name: "Conflicts" });
  return [...list.querySelectorAll(":scope > li")].map((item) => ({
    kind: item.querySelector(".kind")?.textContent,
    foundBy: item.querySelector(".found-by")?.textContent,
    resolution: item.querySelector(".resolution")?.textContent,
    sides: [...item.querySelectorAll(".side")].map((side) => ({
      chunk: side.querySelector(".chunk")?.textContent,
      source: side.querySelector(".side-source")?.textContent,
    })),
    winners: [...item.querySelectorAll(".side.prevails .chunk")].map((chunk) => chunk.textContent),
    documents: item.querySelector(".documents")?.textContent,
    summary: item.querySelector(".summary")?.textContent,
    links: item.querySelectorAll("a").length,
  }));
}

const LEGACY_REPOS = "Kubernetes Legacy Package Repositories Will Be Frozen On September 13, 2023";
const NOT_CITED = "not among the citations";
const KEP_4858 = "KEP-4858: IP/CIDR Validation Improvements";

// Expected values: the S17-R1 design review's evidence (q25's 2 conflicts and q18's rule conflict),
// and each side's title as answers.json holds it, or its absence from the answer's citations
// (read with a Python one-off in the T4 run); never computed by the panel.
describe("the conflict panel", () => {
  it("shows q25's 2 conflicts: one unresolved, one won by 42954 as valid at target", () => {
    render(<ConflictPanel conflicts={answers.q25.conflicts} evidence={answers.q25.evidence} />);
    expect(shownConflicts()).toEqual([
      {
        kind: "contradiction",
        foundBy: "found by the model",
        resolution: "unresolved",
        sides: [
          { chunk: "chunk 43096", source: "Kubernetes v1.29: Mandala" },
          { chunk: "chunk 42549", source: LEGACY_REPOS },
        ],
        winners: [],
        documents:
          "Documents: web:/blog/2023/12/13/kubernetes-v1-29-release/, web:/blog/2023/08/31/legacy-package-repository-deprecation/",
        summary:
          "Chunk 43096 says the legacy repositories will go away entirely in January 2024, while 42549 records that January 2024 was only an announced intention and that removal happened on March 4, 2024.",
        links: 0,
      },
      {
        kind: "contradiction",
        foundBy: "found by the model",
        resolution: "valid at target",
        sides: [
          {
            chunk: "chunk 42954",
            source: "Kubernetes Removals, Deprecations, and Major Changes in Kubernetes 1.29",
          },
          { chunk: "chunk 42530", source: LEGACY_REPOS },
        ],
        winners: ["chunk 42954"],
        documents:
          "Documents: web:/blog/2023/11/16/kubernetes-1-29-upcoming-changes/, web:/blog/2023/08/31/legacy-package-repository-deprecation/",
        summary:
          "Chunk 42954 says the legacy repositories were formally deprecated on September 13, 2023, while 42530 says they were formally deprecated on August 31, 2023 with the freeze on September 13.",
        links: 0,
      },
    ]);
  });

  it("shows q18's rule conflict: 8 chunks, 6 of them not cited, observed beats claimed, no winner", () => {
    render(<ConflictPanel conflicts={answers.q18.conflicts} evidence={answers.q18.evidence} />);
    expect(shownConflicts()).toEqual([
      {
        kind: "claim mismatch",
        foundBy: "found by a rule",
        resolution: "observed beats claimed",
        sides: [
          { chunk: "chunk 31011", source: KEP_4858 },
          { chunk: "chunk 30877", source: NOT_CITED },
          { chunk: "chunk 30990", source: NOT_CITED },
          { chunk: "chunk 30934", source: NOT_CITED },
          { chunk: "chunk 31025", source: NOT_CITED },
          { chunk: "chunk 30991", source: NOT_CITED },
          { chunk: "chunk 30935", source: NOT_CITED },
          { chunk: "chunk 31042", source: KEP_4858 },
        ],
        winners: [],
        documents: "Documents: kep:4858",
        summary: "kep:4858 claims stable; the feature-gate reference at 1.37 says beta.",
        links: 0,
      },
    ]);
  });

  it("shows nothing for an answer with no conflicts", () => {
    const { container } = render(
      <ConflictPanel conflicts={answers.q10.conflicts} evidence={answers.q10.evidence} />,
    );
    expect(container.innerHTML).toBe("");
  });
});
