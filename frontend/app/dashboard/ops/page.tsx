import { redirect } from "next/navigation";

/**
 * PR-3 placeholder. PR-5 replaces this with the Operations kanban board.
 * Until then we redirect to the existing Runs page so the sidebar link doesn't 404.
 */
export default function OpsRedirect() {
  redirect("/dashboard/runs");
}
