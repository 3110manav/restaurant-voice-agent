"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { LoginForm } from "@/components/owner/login-form";
import { useOwnerSession } from "@/components/owner/use-owner-session";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { AuthRequiredError, createRestaurant, listRestaurants, type OwnerRestaurant } from "@/lib/owner-api";
import { getSupabase } from "@/lib/supabase";

export function OwnerHome() {
  const { session, loading, configured } = useOwnerSession();

  if (!configured) {
    return (
      <div className="mx-auto max-w-md p-6 text-sm text-muted-foreground">
        The owner portal needs <code>NEXT_PUBLIC_SUPABASE_URL</code> and{" "}
        <code>NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY</code> to be set (see <code>web/.env.example</code>).
      </div>
    );
  }
  if (loading) return <Skeleton className="m-6 h-40 max-w-md" />;
  if (!session) return <LoginForm />;
  return <Dashboard email={session.user.email ?? ""} />;
}

function Dashboard({ email }: { email: string }) {
  const [restaurants, setRestaurants] = useState<OwnerRestaurant[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setRestaurants(await listRestaurants());
      setError(null);
    } catch (err) {
      if (!(err instanceof AuthRequiredError)) setError((err as Error).message);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="mx-auto flex min-h-screen max-w-3xl flex-col gap-6 p-6">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Your restaurants</h1>
          <p className="text-sm text-muted-foreground">{email}</p>
        </div>
        <Button variant="outline" size="sm" onClick={() => getSupabase().auth.signOut()}>
          Log out
        </Button>
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      {restaurants === null ? (
        <Skeleton className="h-24" />
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          {restaurants.map((r) => (
            <Card key={r.id}>
              <CardHeader>
                <CardTitle className="flex items-center justify-between gap-2">
                  {r.name}
                  <Badge variant="outline" className="capitalize">
                    {r.role}
                  </Badge>
                </CardTitle>
                <CardDescription>{r.cuisine ?? "Restaurant"}</CardDescription>
              </CardHeader>
              <CardContent className="flex flex-wrap gap-2">
                <Link href={`/owner/${r.id}`} className={buttonVariants({ size: "sm" })}>
                  Open console
                </Link>
                <Link href={`/r/${r.slug}`} className={buttonVariants({ size: "sm", variant: "outline" })}>
                  Customer page
                </Link>
              </CardContent>
            </Card>
          ))}
          {restaurants.length === 0 && (
            <p className="text-sm text-muted-foreground">No restaurants yet — create your first one below.</p>
          )}
        </div>
      )}

      <CreateRestaurant onCreated={load} />
    </div>
  );
}

function CreateRestaurant({ onCreated }: { onCreated: () => Promise<void> }) {
  const [name, setName] = useState("");
  const [cuisine, setCuisine] = useState("");
  const [starter, setStarter] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [created, setCreated] = useState<OwnerRestaurant | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setCreated(null);
    try {
      const result = await createRestaurant({ name, cuisine: cuisine || undefined, starter_menu: starter });
      setCreated(result.restaurant);
      setName("");
      setCuisine("");
      await onCreated();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Add a restaurant</CardTitle>
        <CardDescription>
          It goes live immediately at its own link, with its own waiter. Start from a sample menu to try it right away.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} className="flex flex-col gap-3">
          <div className="grid gap-3 sm:grid-cols-2">
            <Input required placeholder="Restaurant name" value={name} onChange={(e) => setName(e.target.value)} />
            <Input placeholder="Cuisine (e.g. Punjabi, Pizza)" value={cuisine} onChange={(e) => setCuisine(e.target.value)} />
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={starter} onChange={(e) => setStarter(e.target.checked)} />
            Start with a sample menu (12 dishes, with descriptions)
          </label>
          {error && <p className="text-sm text-destructive">{error}</p>}
          <div className="flex items-center gap-3">
            <Button type="submit" disabled={busy || !name.trim()}>
              {busy ? "Setting things up…" : "Create restaurant"}
            </Button>
            {created && (
              <Link href={`/owner/${created.id}`} className="text-sm underline underline-offset-4">
                {created.name} is live — open its console
              </Link>
            )}
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
