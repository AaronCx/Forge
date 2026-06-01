import { describe, it, expect } from "vitest";
import { isActive as computeIsActive } from "@/app/dashboard/nav-active";

const ALL_HREFS = [
  "/dashboard",
  "/dashboard/agents",
  "/dashboard/blueprints",
  "/dashboard/library",
  "/dashboard/workspace",
  "/dashboard/ops",
  "/dashboard/ops/approvals",
  "/dashboard/evals",
  "/dashboard/marketplace",
  "/dashboard/connections",
  "/dashboard/team",
  "/dashboard/settings/api-keys",
  "/dashboard/settings",
];

const isActive = (itemHref: string, pathname: string) => computeIsActive(itemHref, pathname, ALL_HREFS);

/**
 * PR-3 acceptance: active-state highlighting must work for the new nested workspace
 * routes AND for routes that were re-homed under a workspace via deep link.
 */

describe("isActive — nested workspace routes", () => {
  it("Dashboard lights only on the exact /dashboard path", () => {
    expect(isActive("/dashboard", "/dashboard")).toBe(true);
    expect(isActive("/dashboard", "/dashboard/agents")).toBe(false);
  });

  it("Operations lights on /dashboard/ops", () => {
    expect(isActive("/dashboard/ops", "/dashboard/ops")).toBe(true);
  });

  it("Approvals lights on /dashboard/ops/approvals, NOT Operations", () => {
    // Longest-prefix wins so Runs/Operations does not also highlight.
    expect(isActive("/dashboard/ops/approvals", "/dashboard/ops/approvals")).toBe(true);
    expect(isActive("/dashboard/ops", "/dashboard/ops/approvals")).toBe(false);
  });

  it("Settings/Connections lights on /dashboard/connections", () => {
    expect(isActive("/dashboard/connections", "/dashboard/connections")).toBe(true);
  });

  it("Settings/Preferences lights on /dashboard/settings but NOT on /dashboard/settings/api-keys", () => {
    // api-keys is its own registered nav item — longest-prefix wins.
    expect(isActive("/dashboard/settings/api-keys", "/dashboard/settings/api-keys")).toBe(true);
    expect(isActive("/dashboard/settings", "/dashboard/settings/api-keys")).toBe(false);
  });
});

describe("isActive — re-homed routes light up the workspace label", () => {
  // PR-3 keeps /dashboard/runs etc. live for deep links (Operations drawer points there).
  // The sidebar still highlights the workspace ("Runs" under Operations) on those URLs.

  it("Operations lights on legacy /dashboard/runs", () => {
    expect(isActive("/dashboard/ops", "/dashboard/runs")).toBe(true);
    expect(isActive("/dashboard/ops", "/dashboard/runs/abc-123")).toBe(true);
  });

  it("Operations lights on /dashboard/traces, /dashboard/recordings, /dashboard/orchestrate, /dashboard/triggers, /dashboard/messages", () => {
    for (const path of [
      "/dashboard/traces",
      "/dashboard/recordings",
      "/dashboard/orchestrate",
      "/dashboard/triggers",
      "/dashboard/messages",
    ]) {
      expect(isActive("/dashboard/ops", path)).toBe(true);
    }
  });

  it("Library lights on /dashboard/prompts and /dashboard/knowledge", () => {
    expect(isActive("/dashboard/library", "/dashboard/prompts")).toBe(true);
    expect(isActive("/dashboard/library", "/dashboard/knowledge")).toBe(true);
  });

  it("Connections lights on /dashboard/providers, /dashboard/mcp, /dashboard/targets, /dashboard/computer-use", () => {
    for (const path of [
      "/dashboard/providers",
      "/dashboard/mcp",
      "/dashboard/targets",
      "/dashboard/computer-use",
    ]) {
      expect(isActive("/dashboard/connections", path)).toBe(true);
    }
  });

  it("Evals lights on /dashboard/compare (the legacy Compare deep link)", () => {
    expect(isActive("/dashboard/evals", "/dashboard/compare")).toBe(true);
  });
});

describe("isActive — unrelated paths do not light up", () => {
  it("Operations does not light up on /dashboard/agents", () => {
    expect(isActive("/dashboard/ops", "/dashboard/agents")).toBe(false);
  });

  it("Library does not light up on /dashboard/agents", () => {
    expect(isActive("/dashboard/library", "/dashboard/agents")).toBe(false);
  });

  it("Connections does not light up on /dashboard/team", () => {
    expect(isActive("/dashboard/connections", "/dashboard/team")).toBe(false);
  });
});
