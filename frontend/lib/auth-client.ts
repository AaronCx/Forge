/**
 * Unified auth client that works with both Supabase and local JWT auth.
 *
 * - If NEXT_PUBLIC_SUPABASE_URL is set → uses Supabase Auth
 * - Otherwise → uses backend API endpoints (/api/auth/login, etc.)
 *
 * All dashboard pages just call getToken() to get the access token.
 */

import { API_URL } from "@/lib/constants";

const isSupabaseMode = !!(
  process.env.NEXT_PUBLIC_SUPABASE_URL &&
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY
);

const TOKEN_KEY = "agentforge_token";
const USER_KEY = "agentforge_user";

export interface AuthUser {
  id: string;
  email: string;
}

/**
 * Get the current access token. Returns null if not logged in.
 */
export async function getToken(): Promise<string | null> {
  if (isSupabaseMode) {
    // Use Supabase client
    const { supabase } = await import("@/lib/supabase");
    const { data } = await supabase.auth.getSession();
    return data.session?.access_token ?? null;
  }

  // Local mode — token in localStorage
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

/**
 * Get the current user info. Returns null if not logged in.
 */
export async function getUser(): Promise<AuthUser | null> {
  if (isSupabaseMode) {
    const { supabase } = await import("@/lib/supabase");
    const { data } = await supabase.auth.getUser();
    if (!data.user) return null;
    return { id: data.user.id, email: data.user.email || "" };
  }

  if (typeof window === "undefined") return null;
  const stored = localStorage.getItem(USER_KEY);
  if (stored) {
    try {
      return JSON.parse(stored);
    } catch {
      return null;
    }
  }
  return null;
}

/**
 * Login with email/password.
 */
export async function login(
  email: string,
  password: string
): Promise<{ error?: string }> {
  if (isSupabaseMode) {
    const { supabase } = await import("@/lib/supabase");
    const { error } = await supabase.auth.signInWithPassword({
      email,
      password,
    });
    if (error) return { error: error.message };
    return {};
  }

  // Local mode — call backend API
  try {
    const res = await fetch(`${API_URL}/api/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: "Login failed" }));
      return { error: err.detail || "Login failed" };
    }
    const data = await res.json();
    localStorage.setItem(TOKEN_KEY, data.access_token);
    localStorage.setItem(
      USER_KEY,
      JSON.stringify({ id: data.user_id, email: data.email })
    );
    // Set cookie for middleware
    document.cookie = `sb-access-token=${data.access_token}; path=/; max-age=86400`;
    return {};
  } catch {
    return { error: "Failed to connect to backend" };
  }
}

/**
 * Sign up with email/password.
 */
export async function signup(
  email: string,
  password: string
): Promise<{ error?: string }> {
  if (isSupabaseMode) {
    const { supabase } = await import("@/lib/supabase");
    const { error } = await supabase.auth.signUp({ email, password });
    if (error) return { error: error.message };
    return {};
  }

  try {
    const res = await fetch(`${API_URL}/api/auth/signup`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    if (!res.ok) {
      const err = await res
        .json()
        .catch(() => ({ detail: "Signup failed" }));
      return { error: err.detail || "Signup failed" };
    }
    const data = await res.json();
    localStorage.setItem(TOKEN_KEY, data.access_token);
    localStorage.setItem(
      USER_KEY,
      JSON.stringify({ id: data.user_id, email: data.email })
    );
    document.cookie = `sb-access-token=${data.access_token}; path=/; max-age=86400`;
    return {};
  } catch {
    return { error: "Failed to connect to backend" };
  }
}

/**
 * Logout.
 */
export async function logout(): Promise<void> {
  if (isSupabaseMode) {
    const { supabase } = await import("@/lib/supabase");
    await supabase.auth.signOut().catch(() => {});
  }

  if (typeof window !== "undefined") {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
    document.cookie = "sb-access-token=; max-age=0; path=/";
    document.cookie = "agentforge_demo=; max-age=0; path=/";
    // Clear Supabase session data
    for (const key of Object.keys(localStorage)) {
      if (key.startsWith("sb-")) localStorage.removeItem(key);
    }
  }
}

/**
 * GitHub OAuth login (Supabase mode only).
 */
export async function loginWithGitHub(): Promise<{ error?: string }> {
  if (!isSupabaseMode) {
    return { error: "OAuth not available in local mode" };
  }
  const { supabase } = await import("@/lib/supabase");
  const { error } = await supabase.auth.signInWithOAuth({
    provider: "github",
    options: {
      redirectTo: `${window.location.origin}/auth/callback`,
    },
  });
  if (error) return { error: error.message };
  return {};
}

/**
 * Whether we're using Supabase auth (for conditional UI).
 */
export const isSupabaseAuth = isSupabaseMode;
