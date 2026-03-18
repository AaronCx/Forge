"use client";

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { API_URL } from "@/lib/constants";

type AppMode = "loading" | "live" | "demo";

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
    // If NEXT_PUBLIC_FORCE_DEMO is set (Vercel deployment), skip detection
    if (process.env.NEXT_PUBLIC_FORCE_DEMO === "true") {
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
          document.cookie = "agentforge_demo=; max-age=0; path=/";
        } else {
          setMode("demo");
        }
      })
      .catch(() => {
        clearTimeout(timeout);
        setMode("demo");
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
