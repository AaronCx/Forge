import { redirect } from "next/navigation";

/**
 * PR-3 placeholder — the Operations workspace's Approvals link points here so it
 * can live under /dashboard/ops/* once PR-5 wires the kanban. Until then we keep
 * the redirect into the existing top-level page.
 */
export default function OpsApprovalsRedirect() {
  redirect("/dashboard/approvals");
}
