/**
 * PR-3 sidebar active-state logic, extracted from layout.tsx so it can be unit-tested
 * directly (Next.js disallows non-default exports from layout/page files).
 */

const RE_HOMED_INTO_OPS = [
  "/dashboard/runs",
  "/dashboard/traces",
  "/dashboard/recordings",
  "/dashboard/orchestrate",
  "/dashboard/triggers",
  "/dashboard/approvals",
  "/dashboard/messages",
];
const RE_HOMED_INTO_CONNECTIONS = [
  "/dashboard/providers",
  "/dashboard/mcp",
  "/dashboard/targets",
  "/dashboard/computer-use",
];
const RE_HOMED_INTO_LIBRARY = ["/dashboard/prompts", "/dashboard/knowledge"];
const RE_HOMED_INTO_EVALS = ["/dashboard/compare"];

/**
 * Pick the sidebar item that should light up for a given URL.
 *
 * Rules:
 *  - Exact /dashboard only lights when the path is exactly /dashboard.
 *  - When two registered hrefs both prefix the path (e.g. /dashboard/ops and
 *    /dashboard/ops/approvals for /dashboard/ops/approvals/123), longest match wins.
 *  - Routes that were re-homed under a workspace (e.g. /dashboard/runs is now
 *    reachable from /dashboard/ops) light up the workspace label, not whichever
 *    legacy path the user navigated to via deep link.
 */
export function isActive(itemHref: string, pathname: string, allHrefs: readonly string[]): boolean {
  if (itemHref === "/dashboard") return pathname === "/dashboard";

  const inGroup = (group: readonly string[]) =>
    group.some((p) => pathname === p || pathname.startsWith(p + "/"));

  if (itemHref === "/dashboard/ops" && inGroup(RE_HOMED_INTO_OPS)) return true;
  if (itemHref === "/dashboard/connections" && inGroup(RE_HOMED_INTO_CONNECTIONS)) return true;
  if (itemHref === "/dashboard/library" && inGroup(RE_HOMED_INTO_LIBRARY)) return true;
  if (itemHref === "/dashboard/evals" && inGroup(RE_HOMED_INTO_EVALS)) return true;

  // Longest-prefix wins among registered nav hrefs.
  const longer = allHrefs.find(
    (h) =>
      h !== itemHref &&
      h.startsWith(itemHref + "/") &&
      (pathname === h || pathname.startsWith(h + "/")),
  );
  if (longer) return false;
  return pathname === itemHref || pathname.startsWith(itemHref + "/");
}
