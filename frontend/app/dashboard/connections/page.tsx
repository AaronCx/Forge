import { redirect } from "next/navigation";

/**
 * PR-3 placeholder. PR-4 replaces this with the tabbed Connections page
 * (Providers, MCP, Targets, Computer-Use config). Until then we redirect to
 * the existing Providers route so the sidebar link doesn't 404.
 */
export default function ConnectionsRedirect() {
  redirect("/dashboard/providers");
}
