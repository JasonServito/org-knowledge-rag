import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { decisions } from "../../fixtures";
import DecisionsPage from "./page";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

// Expected values: the S17-R1 design review's evidence (2 stored chains, kep:2572 and kep:3015; their
// titles), shown with S17-R1 c4's UTC times; never computed by the page.
describe("the Decisions page", () => {
  it("lists the stored chains, each linked to its page", async () => {
    const fetch = vi.fn(async () => Response.json(decisions));
    vi.stubGlobal("fetch", fetch);
    render(<DecisionsPage />);

    const list = await screen.findByRole("list", { name: "Decision chains" });
    const items = within(list)
      .getAllByRole("listitem")
      .map((item) => ({
        link: item.querySelector("a")?.textContent,
        href: item.querySelector("a")?.getAttribute("href"),
        built: item.querySelector(".built")?.textContent,
      }));
    expect(items).toEqual([
      {
        link: "KEP-2572: Defining the Kubernetes Release Cadence",
        href: "/decisions/kep:2572",
        built: "kep:2572 · built 2026-10-15 16:42 UTC",
      },
      {
        link: "KEP-3015: PreferSameZone and PreferSameNode Traffic Distribution",
        href: "/decisions/kep:3015",
        built: "kep:3015 · built 2026-10-15 16:42 UTC",
      },
    ]);
    expect(fetch).toHaveBeenCalledWith("/api/decisions", undefined);
  });

  it("says so when no chain is stored", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => Response.json([])));
    render(<DecisionsPage />);

    await screen.findByText("No decision chains are stored. make chains builds them.");
    expect(screen.queryByRole("list", { name: "Decision chains" })).toBeNull();
  });

  it("shows the fixed message and request ID when the API fails", async () => {
    const error = { code: "database_unavailable", message: "provider text", request_id: "req-503" };
    vi.stubGlobal("fetch", vi.fn(async () => Response.json({ error }, { status: 503 })));
    render(<DecisionsPage />);

    await screen.findByText("The API can't reach its database. Try again once it's back.");
    screen.getByText("Request ID: req-503");
    expect(document.body.textContent).not.toContain("provider text");
  });
});
