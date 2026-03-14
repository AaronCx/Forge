"use client";

import { useEffect } from "react";
import { supabase } from "@/lib/supabase";

export function AuthSync() {
  useEffect(() => {
    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, session) => {
      if (session?.access_token) {
        document.cookie = `sb-access-token=${session.access_token}; path=/; max-age=${60 * 60}; SameSite=Lax`;
      } else {
        document.cookie = "sb-access-token=; max-age=0; path=/";
      }
    });

    return () => subscription.unsubscribe();
  }, []);

  return null;
}
