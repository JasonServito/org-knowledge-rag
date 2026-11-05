import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { answers, decisions } from "../fixtures";
import AnswerPage from "./page";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

// Types the question and presses Ask, as a person would.
function ask(question: string) {
  fireEvent.change(screen.getByLabelText("Question"), { target: { value: question } });
  fireEvent.click(screen.getByRole("button", { name: "Ask" }));
}

// The API, faked by path: `/api/decisions`, which the page reads once when it loads, answers
// `listed` (no stored chains, unless a test gives some); `/api/query` answers `query`.
function stubApi(
  query: () => Promise<Response>,
  listed: () => Promise<Response> = async () => Response.json([]),
) {
  const fetch = vi.fn((path: string) => (path === "/api/decisions" ? listed() : query()));
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

function askButton(name: string): HTMLButtonElement {
  return screen.getByRole("button", { name }) as HTMLButtonElement;
}

// The API's error envelope (docs/interfaces.md, "Errors"), with provider text in its message.
function envelope(code: string, status: number): Response {
  const error = { code, message: "Voyage 401 provider text", request_id: "req-123" };
  return Response.json({ error }, { status });
}

// The UI's own messages (S17-R1 c6), written out here rather than imported from the component.
const NETWORK_MESSAGE =
  "No answer from the API: it isn't running, can't be reached, or took longer than the UI waits.";

describe("the answer page", () => {
  it("disables Ask and shows a working state while the ask is in flight, then the answer", async () => {
    let respond: (response: Response) => void = () => {};
    const fetch = stubApi(() => new Promise<Response>((resolve) => (respond = resolve)));
    render(<AnswerPage />);

    ask(answers.q25.question);
    expect(askButton("Working…").disabled).toBe(true);
    screen.getByRole("status");

    respond(Response.json(answers.q25));
    await screen.findByRole("list", { name: "Citations" });
    expect(askButton("Ask").disabled).toBe(false);
    expect(screen.queryByRole("status")).toBeNull();
    // The list of chains once, at load; the question once.
    expect(fetch.mock.calls.map(([path]) => path)).toEqual(["/api/decisions", "/api/query"]);
  });

  it.each([
    [422, "invalid_request", "The API rejected the question as invalid. Check that it isn't empty."],
    [502, "upstream_failed", "The answer failed upstream: the embedding or the model service. Try again in a minute."],
    [503, "database_unavailable", "The API can't reach its database. Try again once it's back."],
    [500, "internal", "The API hit an unexpected error."],
  ])("shows a %i's fixed message and request ID, never the API's message", async (status, code, message) => {
    stubApi(async () => envelope(code, status));
    render(<AnswerPage />);

    ask("Why?");
    await screen.findByText(message);
    screen.getByText("Request ID: req-123");
    expect(document.body.textContent).not.toContain("Voyage 401 provider text");
  });

  it.each([
    ["the browser can't reach the UI's server", () => Promise.reject(new TypeError("Failed to fetch"))],
    ["the forwarder gives up (its own plain-text 500)", async () => new Response("Internal Server Error", { status: 500 })],
  ])("shows the network message when %s", async (_, fetch) => {
    stubApi(fetch);
    render(<AnswerPage />);

    ask("Why?");
    await screen.findByText(NETWORK_MESSAGE);
    expect(screen.queryByText(/Request ID/)).toBeNull();
  });

  // ADR-016 D4. Expected values: q02 cites kep:2572 (the S17-R1 design review's evidence) in chunk
  // 33453 (answers.json, read with a Python one-off).
  it("links a citation of a stored chain's KEP to the chain's page", async () => {
    stubApi(
      async () => Response.json(answers.q02),
      async () => Response.json(decisions),
    );
    render(<AnswerPage />);

    ask(answers.q02.question);
    const link = await screen.findByRole("link", { name: "decision chain" });
    expect(link.getAttribute("href")).toBe("/decisions/kep:2572");
    expect(link.closest("li")?.querySelector(".chunk")?.textContent).toBe("chunk 33453");
  });

  it("still shows the answer, without chain links or an error, when the list of chains fails", async () => {
    stubApi(
      async () => Response.json(answers.q02),
      async () => envelope("database_unavailable", 503),
    );
    render(<AnswerPage />);

    ask(answers.q02.question);
    await screen.findByRole("list", { name: "Citations" });
    expect(screen.queryByRole("link", { name: "decision chain" })).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
