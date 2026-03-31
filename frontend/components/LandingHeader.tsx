"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";

export function LandingHeader() {
  // Default to demo-style links (all point to /dashboard) to avoid hydration mismatch.
  // On mount, check if we're actually in non-demo mode and swap to login/signup links.
  const [isDemo, setIsDemo] = useState(true);

  useEffect(() => {
    const onVercel = window.location.hostname.includes("vercel.app");
    const forceDemo = process.env.NEXT_PUBLIC_FORCE_DEMO === "true";
    const cookieDemo = document.cookie.includes("forge_demo=1");
    if (!onVercel && !forceDemo && !cookieDemo) {
      setIsDemo(false);
    }
  }, []);

  return (
    <header className="border-b border-border">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-6">
        <div className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-primary-foreground font-bold text-sm">
            F
          </div>
          <span className="text-xl font-bold">Forge</span>
        </div>
        <div className="flex items-center gap-4">
          <Link href={isDemo ? "/dashboard" : "/login"}>
            <Button variant="ghost">{isDemo ? "Dashboard" : "Log in"}</Button>
          </Link>
          <Link href={isDemo ? "/dashboard" : "/signup"}>
            <Button>{isDemo ? "Try Demo" : "Get Started"}</Button>
          </Link>
        </div>
      </div>
    </header>
  );
}
