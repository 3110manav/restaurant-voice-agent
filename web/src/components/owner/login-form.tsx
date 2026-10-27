"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { getSupabase } from "@/lib/supabase";

export function LoginForm() {
  const [mode, setMode] = useState<"signin" | "signup">("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setNotice(null);
    const supabase = getSupabase();
    try {
      if (mode === "signin") {
        const { error: err } = await supabase.auth.signInWithPassword({ email, password });
        if (err) setError(err.message);
      } else {
        const { data, error: err } = await supabase.auth.signUp({ email, password });
        if (err) setError(err.message);
        else if (!data.session) setNotice("Check your email to confirm your account, then log in.");
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto flex min-h-screen w-full max-w-sm flex-col justify-center p-6">
      <Card>
        <CardHeader>
          <CardTitle>{mode === "signin" ? "Restaurant login" : "Create your account"}</CardTitle>
          <CardDescription>
            {mode === "signin"
              ? "Manage your menu, orders and waiter."
              : "Set up your restaurant on Sarthi in a couple of minutes."}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={submit} className="flex flex-col gap-3">
            <Input
              type="email"
              required
              autoComplete="email"
              placeholder="you@restaurant.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
            <Input
              type="password"
              required
              minLength={6}
              autoComplete={mode === "signin" ? "current-password" : "new-password"}
              placeholder="Password (6+ characters)"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
            {error && <p className="text-sm text-destructive">{error}</p>}
            {notice && <p className="text-sm text-muted-foreground">{notice}</p>}
            <Button type="submit" disabled={busy}>
              {busy ? "One moment…" : mode === "signin" ? "Log in" : "Create account"}
            </Button>
          </form>
          <button
            type="button"
            className="mt-4 text-sm text-muted-foreground underline-offset-4 hover:underline"
            onClick={() => {
              setMode(mode === "signin" ? "signup" : "signin");
              setError(null);
              setNotice(null);
            }}
          >
            {mode === "signin" ? "New here? Create an account" : "Already have an account? Log in"}
          </button>
        </CardContent>
      </Card>
    </div>
  );
}
