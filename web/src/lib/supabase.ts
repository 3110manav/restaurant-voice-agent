import { createClient, type SupabaseClient } from "@supabase/supabase-js";

// Only the *publishable* key ever reaches the browser — it is public by design and
// can do nothing the database's row-level security doesn't allow. The service
// (secret) key stays on the backend. Owner logins live here; everything else the
// owner portal does goes through the backend, which checks the login token.
const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
const publishableKey = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;

let client: SupabaseClient | null = null;

export function supabaseConfigured(): boolean {
  return Boolean(url && publishableKey);
}

export function getSupabase(): SupabaseClient {
  if (!url || !publishableKey) {
    throw new Error("Supabase isn't configured: set NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY");
  }
  client ??= createClient(url, publishableKey);
  return client;
}
