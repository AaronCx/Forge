"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

/**
 * Legacy /demo route — redirects to dashboard.
 * Demo mode is now auto-detected based on backend availability.
 */
export default function DemoPage() {
  const router = useRouter();

  useEffect(() => {
    router.replace("/dashboard");
  }, [router]);

  return (
    <div className="flex min-h-screen items-center justify-center">
      <p className="text-muted-foreground">Redirecting to dashboard...</p>
    </div>
  );
}
