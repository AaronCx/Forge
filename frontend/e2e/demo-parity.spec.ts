import { test, expect, type Page } from "@playwright/test";

const ROUTES = [
  "/dashboard",
  "/dashboard/agents",
  "/dashboard/blueprints",
  "/dashboard/prompts",
  "/dashboard/knowledge",
  "/dashboard/workspace",
  "/dashboard/orchestrate",
  "/dashboard/approvals",
  "/dashboard/triggers",
  "/dashboard/targets",
  "/dashboard/runs",
  "/dashboard/traces",
  "/dashboard/recordings",
  "/dashboard/evals",
  "/dashboard/compare",
  "/dashboard/computer-use",
  "/dashboard/providers",
  "/dashboard/mcp",
  "/dashboard/marketplace",
  "/dashboard/team",
  "/dashboard/settings",
  "/dashboard/settings/api-keys",
] as const;

// Network-level 404s and "Failed to fetch" complaints are expected in demo
// because the frontend tries to reach the backend on localhost:8000 first.
// We only fail on uncaught React/JS errors, which surface as `pageerror`
// or as console errors with stack traces.
const NETWORK_NOISE = [
  /failed to load resource/i,
  /failed to fetch/i,
  /networkerror/i,
  /the server responded with a status of/i,
];

async function captureFatalErrors(page: Page) {
  const errors: string[] = [];
  page.on("pageerror", (err) => errors.push(err.message));
  page.on("console", (msg) => {
    if (msg.type() !== "error") return;
    const text = msg.text();
    if (NETWORK_NOISE.some((pattern) => pattern.test(text))) return;
    errors.push(text);
  });
  return errors;
}

for (const route of ROUTES) {
  test(`demo route ${route} loads with seed data`, async ({ page }) => {
    const errors = await captureFatalErrors(page);

    const response = await page.goto(route, { waitUntil: "domcontentloaded" });
    expect(response?.status(), `expected non-error status on ${route}`).toBeLessThan(400);

    // Wait for client-side hydration + initial useEffect to settle.
    await page.waitForLoadState("load");
    await page.waitForTimeout(800);

    // The page must not render a 404 / error fallback.
    await expect(
      page.locator("text=/^(error|404|something went wrong)$/i")
    ).toHaveCount(0);

    // Either a seeded list rendered, or the surface shows an *expected* empty state
    // tagged with data-seeded="true" so we can tell genuine empty from broken.
    const empty = await page.locator("text=/no .* yet/i").count();
    if (empty > 0) {
      const seeded = page.locator('[data-seeded="true"]').first();
      await expect(seeded, `${route}: empty state without a data-seeded marker`).toBeVisible({
        timeout: 5_000,
      });
    }

    // No fatal client-side errors should reach the console.
    expect(errors, `${route}: console errors\n${errors.join("\n")}`).toEqual([]);
  });
}

test("redirects from monitor and analytics resolve to dashboard anchors", async ({ page }) => {
  await page.goto("/dashboard/monitor");
  expect(page.url()).toMatch(/\/dashboard(#live)?$/);

  await page.goto("/dashboard/analytics");
  expect(page.url()).toMatch(/\/dashboard(#usage)?$/);
});
