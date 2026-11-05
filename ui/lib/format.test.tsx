import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { answers } from "../fixtures";
import { formatText } from "./format";

afterEach(cleanup);

// The formatter's elements, rendered as a page shows them.
function show(text: string): HTMLElement {
  return render(<div>{formatText(text)}</div>).container;
}

// Expected values from the S17-R1 design review's evidence (markdown in 20 answers, bold in 8); the ids
// were listed once by a regex count over answers.json (the T3 brief has the command), never by
// the formatter.
const MARKDOWN_ANSWERS = [
  "q11", "q12", "q15", "q16", "q17", "q19", "q25", "q30", "q31", "q33",
  "q34", "q35", "q36", "q40", "q41", "q42", "q43", "q44", "q45", "q46",
];
const BOLD_ANSWERS = ["q17", "q25", "q35", "q36", "q40", "q44", "q45", "q46"];

describe("the formatter", () => {
  it("shows q42's flag with its <IPv4 CIDR> exactly, inside a code element", () => {
    const container = show(answers.q42.answer);
    const codes = [...container.querySelectorAll("code")].map((code) => code.textContent);
    expect(codes).toContain("--service-cluster-ip-range=<IPv4 CIDR>,<IPv6 CIDR>");
    // q42's 2 bullet lists: the 4 components, then the 3 prerequisites (counted by hand).
    const lists = [...container.querySelectorAll("ul")].map((list) => list.children.length);
    expect(lists).toEqual([4, 3]);
  });

  it("never makes a link, an image or a script: it shows them as text", () => {
    const crafted = [
      "See [click](https://evil.example) for more.",
      "- ![x](https://evil.example/a.png)",
      "**<script>alert(1)</script>**",
    ].join("\n");
    const container = show(crafted);
    expect(container.querySelectorAll("a, img, script")).toHaveLength(0);
    expect(container.textContent).toContain("[click](https://evil.example)");
    expect(container.textContent).toContain("![x](https://evil.example/a.png)");
    expect(container.textContent).toContain("<script>alert(1)</script>");
  });

  it("shows an unclosed ** or backtick as text, without swallowing the rest", () => {
    const container = show("**bold** and `code`, then **open and `open too");
    expect(container.querySelector("strong")?.textContent).toBe("bold");
    expect(container.querySelector("code")?.textContent).toBe("code");
    expect(container.textContent).toBe("bold and code, then **open and `open too");
  });

  it("puts - and * bullet lines in one list, other lines in paragraphs", () => {
    const container = show("Before:\n- one\n* two\n\nAfter, with *one star*.");
    expect([...container.querySelectorAll("li")].map((item) => item.textContent)).toEqual([
      "one",
      "two",
    ]);
    expect([...container.querySelectorAll("p")].map((line) => line.textContent)).toEqual([
      "Before:",
      "After, with *one star*.",
    ]);
  });

  it("leaves no raw ** or backtick in the 20 markdown answers; 8 of them show bold", () => {
    const withBold = MARKDOWN_ANSWERS.filter((id) => {
      const container = show(answers[id].answer);
      expect(container.textContent, id).not.toContain("**");
      expect(container.textContent, id).not.toContain("`");
      return container.querySelector("strong") !== null;
    });
    expect(withBold).toEqual(BOLD_ANSWERS);
  });
});
