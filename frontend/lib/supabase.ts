import { createClient, SupabaseClient } from "@supabase/supabase-js";

let _supabase: SupabaseClient | null = null;

function getSupabaseClient(): SupabaseClient {
  if (_supabase) return _supabase;

  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

  if (!supabaseUrl || !supabaseAnonKey) {
    // Local mode — no Supabase client available.
    // Auth is handled via API endpoints instead.
    // Return a no-op proxy that won't crash if accidentally imported.
    return new Proxy({} as SupabaseClient, {
      get(_target, prop) {
        if (prop === "auth") {
          return {
            getSession: async () => ({ data: { session: null }, error: null }),
            getUser: async () => ({ data: { user: null }, error: null }),
            signInWithPassword: async () => ({
              data: null,
              error: { message: "Use API auth in local mode" },
            }),
            signUp: async () => ({
              data: null,
              error: { message: "Use API auth in local mode" },
            }),
            signOut: async () => ({ error: null }),
            signInWithOAuth: async () => ({
              data: null,
              error: { message: "OAuth not available in local mode" },
            }),
            onAuthStateChange: () => ({
              data: { subscription: { unsubscribe: () => {} } },
            }),
          };
        }
        return undefined;
      },
    });
  }

  _supabase = createClient(supabaseUrl, supabaseAnonKey);
  return _supabase;
}

export const supabase = new Proxy({} as SupabaseClient, {
  get(_target, prop, receiver) {
    const client = getSupabaseClient();
    const value = Reflect.get(client, prop, receiver);
    return typeof value === "function" ? value.bind(client) : value;
  },
});
