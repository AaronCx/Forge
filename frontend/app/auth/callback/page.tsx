"use client";

import { useEffect, useState } from "react";
import { supabase } from "@/lib/supabase";

export default function AuthCallbackPage() {
  const [status, setStatus] = useState("Signing you in...");

  useEffect(() => {
    async function handleCallback() {
      // For PKCE flow: exchange the code from the URL for a session
      const params = new URLSearchParams(window.location.search);
      const code = params.get("code");

      if (code) {
        const { data, error } = await supabase.auth.exchangeCodeForSession(code);
        if (error) {
          setStatus("Sign-in failed. Redirecting...");
          setTimeout(() => { window.location.href = "/login"; }, 1500);
          return;
        }
        if (data.session) {
          document.cookie = `sb-access-token=${data.session.access_token}; path=/; max-age=${60 * 60}; SameSite=Lax`;
          window.location.href = "/dashboard";
          return;
        }
      }

      // Fallback: check if Supabase already has a session (hash fragment flow)
      const { data } = await supabase.auth.getSession();
      if (data.session) {
        document.cookie = `sb-access-token=${data.session.access_token}; path=/; max-age=${60 * 60}; SameSite=Lax`;
        window.location.href = "/dashboard";
        return;
      }

      // Wait briefly for onAuthStateChange to fire
      await new Promise((r) => setTimeout(r, 1000));
      const retry = await supabase.auth.getSession();
      if (retry.data.session) {
        document.cookie = `sb-access-token=${retry.data.session.access_token}; path=/; max-age=${60 * 60}; SameSite=Lax`;
        window.location.href = "/dashboard";
        return;
      }

      setStatus("Sign-in failed. Redirecting...");
      setTimeout(() => { window.location.href = "/login"; }, 1500);
    }

    handleCallback();
  }, []);

  return (
    <div className="flex min-h-screen items-center justify-center">
      <p className="text-muted-foreground">{status}</p>
    </div>
  );
}
