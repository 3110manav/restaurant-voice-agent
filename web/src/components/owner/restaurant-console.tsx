"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { OrdersTab, RequestsTab } from "@/components/owner/activity-tabs";
import { LoginForm } from "@/components/owner/login-form";
import { MenuEditor } from "@/components/owner/menu-editor";
import { CustomersTab, ReportTab, TonightTab } from "@/components/owner/pilot-tabs";
import { SettingsTab } from "@/components/owner/settings-tab";
import { useOwnerSession } from "@/components/owner/use-owner-session";
import { buttonVariants } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { isHexColor, readableOn } from "@/lib/brand";
import { AuthRequiredError, fetchOwnerMenu, type OwnerMenu } from "@/lib/owner-api";
import { cn } from "@/lib/utils";

const TABS = [
  { key: "tonight", label: "Tonight" },
  { key: "customers", label: "Customers" },
  { key: "report", label: "Monthly report" },
  { key: "orders", label: "Orders" },
  { key: "requests", label: "Table requests" },
  { key: "menu", label: "Menu" },
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
  const [tab, setTab] = useState<TabKey>("tonight");

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

  const accent = isHexColor(restaurant.accent_color) ? restaurant.accent_color : "#1c1917";

  return (
    <div className="flex min-h-screen flex-col bg-muted/40">
      <header className="border-b bg-background">
        <div className="mx-auto w-full max-w-[1240px] px-6 pt-4">
          <Link href="/owner" className="text-xs text-muted-foreground underline-offset-4 hover:underline">
            ← All restaurants
          </Link>
          <div className="mt-2 mb-3 flex flex-wrap items-center gap-3">
            <div
              aria-hidden="true"
              className="flex size-10 shrink-0 items-center justify-center rounded-lg text-lg font-semibold"
              style={{ background: accent, color: readableOn(accent) }}
            >
              {restaurant.name.trim().charAt(0).toUpperCase()}
            </div>
            <div className="min-w-40 flex-1">
              <h1 className="text-lg leading-tight font-semibold">{restaurant.name}</h1>
              <p className="text-sm text-muted-foreground">
                {[restaurant.cuisine, `Waiter: ${restaurant.agent_name}`, restaurant.status === "live" ? "Live" : "Draft"]
                  .filter(Boolean)
                  .join(" · ")}
              </p>
            </div>
            <Link href={`/r/${restaurant.slug}`} target="_blank" className={buttonVariants({ variant: "outline" })}>
              Open guest page ↗
            </Link>
          </div>
          <nav aria-label="Console sections" className="flex flex-wrap gap-1">
            {TABS.map((t) => (
              <button
                key={t.key}
                type="button"
                aria-pressed={tab === t.key}
                onClick={() => setTab(t.key)}
                className={cn(
                  "h-11 border-b-2 px-3.5 text-sm",
                  tab === t.key ? "font-semibold text-foreground" : "border-transparent text-muted-foreground hover:text-foreground"
                )}
                style={tab === t.key ? { borderColor: accent } : undefined}
              >
                {t.label}
              </button>
            ))}
          </nav>
        </div>
      </header>

      <main className="mx-auto flex w-full max-w-[1240px] flex-col gap-5 p-6">
      {tab === "menu" &&
        (canEdit ? (
          <MenuEditor menu={menu} onChanged={reload} />
        ) : (
          <p className="text-sm text-muted-foreground">Only owners and managers can edit the menu.</p>
        ))}
      {tab === "tonight" && <TonightTab restaurant={restaurant} />}
      {tab === "orders" && <OrdersTab restaurantId={restaurant.id} />}
      {tab === "requests" && <RequestsTab restaurantId={restaurant.id} />}
      {tab === "customers" &&
        (canEdit ? (
          <CustomersTab restaurant={restaurant} />
        ) : (
          <p className="text-sm text-muted-foreground">Only owners and managers can see the customer list.</p>
        ))}
      {tab === "report" && <ReportTab restaurant={restaurant} />}
      {tab === "settings" &&
        (canEdit ? (
          <SettingsTab restaurant={restaurant} onChanged={reload} />
        ) : (
          <p className="text-sm text-muted-foreground">Only owners and managers can change settings.</p>
        ))}
      </main>
    </div>
  );
}
