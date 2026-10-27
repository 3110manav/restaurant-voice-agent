"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { OrdersTab, RequestsTab } from "@/components/owner/activity-tabs";
import { LoginForm } from "@/components/owner/login-form";
import { MenuEditor } from "@/components/owner/menu-editor";
import { SettingsTab } from "@/components/owner/settings-tab";
import { useOwnerSession } from "@/components/owner/use-owner-session";
import { buttonVariants } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { AuthRequiredError, fetchOwnerMenu, type OwnerMenu } from "@/lib/owner-api";
import { cn } from "@/lib/utils";

const TABS = [
  { key: "menu", label: "Menu" },
  { key: "orders", label: "Orders" },
  { key: "requests", label: "Table requests" },
  { key: "settings", label: "Settings & QR" },
] as const;
type TabKey = (typeof TABS)[number]["key"];

export function RestaurantConsole({ id }: { id: string }) {
  const { session, loading, configured } = useOwnerSession();
  if (!configured) return <p className="p-6 text-sm text-muted-foreground">Supabase isn&apos;t configured for the portal.</p>;
  if (loading) return <Skeleton className="m-6 h-40" />;
  if (!session) return <LoginForm />;
  return <Console id={id} />;
}

function Console({ id }: { id: string }) {
  const [menu, setMenu] = useState<OwnerMenu | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<TabKey>("menu");

  const reload = useCallback(async () => {
    try {
      setMenu(await fetchOwnerMenu(id));
      setError(null);
    } catch (err) {
      if (!(err instanceof AuthRequiredError)) setError((err as Error).message);
    }
  }, [id]);

  useEffect(() => {
    void reload();
  }, [reload]);

  if (error) {
    return (
      <div className="mx-auto max-w-md p-6 text-sm">
        <p className="text-destructive">{error}</p>
        <Link href="/owner" className="mt-3 inline-block underline underline-offset-4">
          Back to your restaurants
        </Link>
      </div>
    );
  }
  if (!menu) return <Skeleton className="m-6 h-64" />;

  const { restaurant } = menu;
  const canEdit = restaurant.role !== "staff";

  return (
    <div className="mx-auto flex min-h-screen max-w-4xl flex-col gap-5 p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <Link href="/owner" className="text-xs text-muted-foreground underline-offset-4 hover:underline">
            ← All restaurants
          </Link>
          <h1 className="text-xl font-semibold">{restaurant.name}</h1>
          <p className="text-sm text-muted-foreground">
            {[restaurant.cuisine, `Waiter: ${restaurant.agent_name}`].filter(Boolean).join(" · ")}
          </p>
        </div>
        <Link
          href={`/r/${restaurant.slug}`}
          target="_blank"
          className={buttonVariants({ variant: "outline", size: "sm" })}
        >
          Open customer page ↗
        </Link>
      </div>

      <div className="flex gap-1 border-b">
        {TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            onClick={() => setTab(t.key)}
            className={cn(
              "-mb-px border-b-2 px-3 py-2 text-sm",
              tab === t.key ? "border-primary font-medium" : "border-transparent text-muted-foreground"
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "menu" &&
        (canEdit ? (
          <MenuEditor menu={menu} onChanged={reload} />
        ) : (
          <p className="text-sm text-muted-foreground">Only owners and managers can edit the menu.</p>
        ))}
      {tab === "orders" && <OrdersTab restaurantId={restaurant.id} />}
      {tab === "requests" && <RequestsTab restaurantId={restaurant.id} />}
      {tab === "settings" &&
        (canEdit ? (
          <SettingsTab restaurant={restaurant} onChanged={reload} />
        ) : (
          <p className="text-sm text-muted-foreground">Only owners and managers can change settings.</p>
        ))}
    </div>
  );
}
