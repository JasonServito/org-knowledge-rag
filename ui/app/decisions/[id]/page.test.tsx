import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { chains } from "../../../fixtures";
import DecisionPage from "./page";

// The page reads its id from the address with Next's `useParams`: here, the id each test sets,
// URI-encoded as Next gives it (`encodeURIComponent` in next/dist/shared/lib/router/utils/
// get-dynamic-param.js), so `/decisions/kep:3015` gives `kep%3A3015`.
const address = vi.hoisted(() => ({ id: "" }));
vi.mock("next/navigation", () => ({ useParams: () => ({ id: address.id }) }));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("a chain's page", () => {
  it("reads the chain of the address's id and shows its steps", async () => {
    address.id = "kep%3A3015";
    const fetch = vi.fn(async () => Response.json(chains["kep:3015"]));
    vi.stubGlobal("fetch", fetch);
    render(<DecisionPage />);

    const steps = await screen.findByRole("list", { name: "Steps" });
    expect(within(steps).getAllByRole("listitem")).toHaveLength(6);
    // Decoded once, then encoded once by the client for the path: never `kep%253A3015`.
    expect(fetch).toHaveBeenCalledWith("/api/decisions/kep%3A3015", undefined);
  });

  it("shows the fixed not_found message and request ID for an id with no stored chain", async () => {
    address.id = "kep%3A9999";
    const error = { code: "not_found", message: "no stored decision chain", request_id: "req-404" };
    vi.stubGlobal("fetch", vi.fn(async () => Response.json({ error }, { status: 404 })));
    render(<DecisionPage />);

    // The UI's own message (S17-R1 c6), written out here rather than imported.
    await screen.findByText("The API has nothing stored at this address.");
    screen.getByText("Request ID: req-404");
    expect(document.body.textContent).not.toContain("no stored decision chain");
  });
});
