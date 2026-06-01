import { redirect } from "next/navigation";

/**
 * PR-3 placeholder. PR-4 replaces this with the tabbed Library page (Prompts +
 * Knowledge). Until then we redirect into the existing Prompts route so the
 * sidebar link doesn't 404.
 */
export default function LibraryRedirect() {
  redirect("/dashboard/prompts");
}
