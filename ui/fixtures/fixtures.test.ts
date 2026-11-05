import { describe, expect, it } from "vitest";

import { answers } from "./index";

// Expected values from the S17-R1 design review's evidence (the slice doc), counted then from
// questions.jsonl; never computed here from the fixtures.
describe("the saved answers", () => {
  const rows = Object.entries(answers);

  it("holds 43 answers", () => {
    expect(rows).toHaveLength(43);
  });

  it("has 36 answered and 7 with insufficient evidence", () => {
    const insufficient = rows.filter(([, answer]) => answer.answer_status === "insufficient_evidence");
    expect(insufficient.map(([id]) => id)).toEqual(["q05", "q10", "q15", "q20", "q27", "q47", "q48"]);
    expect(rows.filter(([, answer]) => answer.answer_status === "answered")).toHaveLength(36);
  });

  it("has 16 answers with conflicts, 20 conflicts in all", () => {
    expect(rows.filter(([, answer]) => answer.conflicts.length > 0)).toHaveLength(16);
    expect(rows.reduce((total, [, answer]) => total + answer.conflicts.length, 0)).toBe(20);
  });
});
