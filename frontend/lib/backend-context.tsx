"use client";

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { API_URL } from "@/lib/constants";

type AppMode = "loading" | "live" | "demo" | "unreachable";

interface BackendContextValue {
  mode: AppMode;
  backendUrl: string;
}

const BackendContext = createContext<BackendContextValue>({
  mode: "loading",
  backendUrl: API_URL,
});

export function useBackendMode() {
  return useContext(BackendContext);
}

export function BackendProvider({ children }: { children: ReactNode }) {
  const [mode, setMode] = useState<AppMode>("loading");

  useEffect(() => {
    // If NEXT_PUBLIC_FORCE_DEMO is set or we're on vercel.app, skip health check entirely
    if (
      process.env.NEXT_PUBLIC_FORCE_DEMO === "true" ||
      window.location.hostname.includes("vercel.app")
    ) {
      setMode("demo");
      return;
    }

    // Try to reach the backend health endpoint
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 5000);

    fetch(`${API_URL}/health`, { signal: controller.signal })
      .then((res) => {
        clearTimeout(timeout);
        if (res.ok) {
          setMode("live");
          // Clear any stale demo cookie when backend is available
          document.cookie = "forge_demo=; max-age=0; path=/";
        } else {
          // Reachable but unhealthy — surface to the user, don't silently
          // fall back to demo data and pretend it's live.
          setMode("unreachable");
        }
      })
      .catch(() => {
        clearTimeout(timeout);
        // Backend unreachable on a non-demo deployment is a real problem;
        // tell the user instead of rendering zero values dressed up as live.
        setMode("unreachable");
      });

    return () => {
      clearTimeout(timeout);
      controller.abort();
    };
  }, []);

  return (
    <BackendContext.Provider value={{ mode, backendUrl: API_URL }}>
      {children}
    </BackendContext.Provider>
  );
}
