"use client";

import type { Session } from "@supabase/supabase-js";
import { useEffect, useState } from "react";

import { getSupabase, supabaseConfigured } from "@/lib/supabase";

/** The logged-in owner's session (null = logged out), kept live across tabs and sign-outs. */
export function useOwnerSession() {
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);
  const configured = supabaseConfigured();

  useEffect(() => {
    if (!configured) {
      setLoading(false);
      return;
    }
    const supabase = getSupabase();
    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session);
      setLoading(false);
    });
    const { data } = supabase.auth.onAuthStateChange((_event, next) => setSession(next));
    return () => data.subscription.unsubscribe();
  }, [configured]);

  return { session, loading, configured };
}
