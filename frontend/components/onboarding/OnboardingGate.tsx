"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { getToken } from "@/lib/auth-client";
import { useBackendMode } from "@/lib/backend-context";

/**
 * First-login onboarding gate. A logged-in user who hasn't onboarded is sent to
 * /onboarding. Live mode only (demo has no backend). Never traps — Skip sets
 * onboarded_at, and any error here is swallowed so the dashboard still loads.
 * Renders nothing.
 */
export function OnboardingGate() {
  const router = useRouter();
  const { mode } = useBackendMode();

  useEffect(() => {
    if (mode !== "live") return;
    let cancelled = false;
    (async () => {
      try {
        const token = await getToken();
        if (!token) return;
        const prefs = await api.preferences.get(token);
        if (!cancelled && !prefs.onboarded_at) {
          router.push("/onboarding");
        }
      } catch {
        // Don't trap the user on a preferences hiccup.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [mode, router]);

  return null;
}
