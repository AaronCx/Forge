"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function DemoPage() {
  const router = useRouter();

  useEffect(() => {
    document.cookie = "agentforge_demo=1; path=/";
    router.replace("/dashboard?demo=true");
  }, [router]);

  return (
    <div className="flex min-h-screen items-center justify-center">
      <p className="text-muted-foreground">Loading demo...</p>
    </div>
  );
}
