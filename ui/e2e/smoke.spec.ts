import { expect, test, type Page } from "@playwright/test";

import { answers, chains, decisions } from "../fixtures";

// The browser smoke test (ADR-016 D2): the answer page (q25) and a chain page (kep:3015) in
// Chromium, on the built app. No API runs: every `/api/*` request is answered inside the browser
// from the fixtures, with the status, body and X-Request-ID the forwarder passes on from the API.
// Any page error or console error fails the test. Each test saves a screenshot in test-results/
// (gitignored; Playwright empties it at the start of each run) for a person to open.

const REQUEST_ID = "e2e-fixture";

async function answerFromFixtures(page: Page) {
  await page.route("**/api/**", async (route) => {
    const path = decodeURIComponent(new URL(route.request().url()).pathname);
    const headers = { "X-Request-ID": REQUEST_ID };
    if (path === "/api/query") {
      return route.fulfill({ json: answers.q25, headers });
    }
    if (path === "/api/decisions") {
      return route.fulfill({ json: decisions, headers });
    }
    const chain = chains[path.replace("/api/decisions/", "")];
    if (chain !== undefined) {
      return route.fulfill({ json: chain, headers });
    }
    const error = { code: "not_found", message: "Not Found", request_id: REQUEST_ID };
    return route.fulfill({ status: 404, json: { error }, headers });
  });
}

// Every page error (an uncaught exception) and console error, as one line each.
function collectErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(`pageerror: ${error.message}`));
  page.on("console", (message) => {
    if (message.type() === "error") {
      errors.push(`console: ${message.text()}`);
    }
  });
  return errors;
}

// Expected values: the S17-R1 design review's evidence (q25's 7 citations and 2 conflicts; kep:3015's
// missing decision step, `no_link`).
test("the answer page shows q25's 2 conflicts and 7 citations", async ({ page }) => {
  const errors = collectErrors(page);
  await answerFromFixtures(page);

  await page.goto("/");
  await page.getByLabel("Question").fill(answers.q25.question);
  await page.getByRole("button", { name: "Ask" }).click();

  const citations = page.getByRole("list", { name: "Citations" }).getByRole("listitem");
  await expect(citations).toHaveCount(7);
  await expect(page.getByRole("list", { name: "Conflicts" }).locator(":scope > li")).toHaveCount(2);
  await page.screenshot({ path: "test-results/answer-q25.png", fullPage: true });
  expect(errors).toEqual([]);
});

test("kep:3015's chain page shows 6 steps, the decision step missing (no_link)", async ({ page }) => {
  const errors = collectErrors(page);
  await answerFromFixtures(page);

  await page.goto("/decisions/kep:3015");

  const steps = page.getByRole("list", { name: "Steps" }).getByRole("listitem");
  await expect(steps).toHaveCount(6);
  await expect(steps.nth(3)).toContainText("decision");
  await expect(steps.nth(3)).toContainText("missing: no_link");
  await expect(page.getByRole("heading", { level: 2 })).toHaveText(
    "KEP-3015: PreferSameZone and PreferSameNode Traffic Distribution",
  );
  await page.screenshot({ path: "test-results/chain-kep-3015.png", fullPage: true });
  expect(errors).toEqual([]);
});
