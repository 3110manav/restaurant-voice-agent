"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { OrderingPage } from "@/components/ordering-page";
import { PhotoCredits } from "@/components/photo-credits";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { fetchRestaurant, type RestaurantInfo } from "@/lib/api";
import { personaForRestaurant } from "@/lib/personas";

/** After a few seconds of loading, says why: on the free tier the first scan after a quiet spell wakes the server. */
function WakingNotice() {
  const [slow, setSlow] = useState(false);
  useEffect(() => {
    const timer = setTimeout(() => setSlow(true), 5000);
    return () => clearTimeout(timer);
  }, []);
  if (!slow) return null;
  return (
    <p className="fixed inset-x-0 bottom-6 mx-auto w-fit rounded-full border bg-background px-4 py-2 text-xs text-muted-foreground shadow-sm">
      Waking up the kitchen… the first order of the day can take up to a minute.
    </p>
  );
}

export function RestaurantSkeleton() {
  return (
    <div className="flex min-h-screen flex-col">
      <div className="border-b px-4 py-4">
        <Skeleton className="h-6 w-48" />
        <Skeleton className="mt-2 h-4 w-72" />
      </div>
      <div className="grid grid-cols-2 gap-4 p-4 sm:grid-cols-3 lg:grid-cols-4">
        {Array.from({ length: 8 }).map((_, i) => (
          <Skeleton key={i} className="h-48 rounded-lg" />
        ))}
      </div>
    </div>
  );
}

type State =
  | { status: "loading" }
  | { status: "ready"; info: RestaurantInfo }
  | { status: "missing" }
  | { status: "error" };

/** A restaurant's customer-facing page: its menu, its waiter, its table. */
export function RestaurantPage({ slug }: { slug: string }) {
  const [state, setState] = useState<State>({ status: "loading" });
  // The table number comes from the QR code's ?table=5, read after mount (no server-side URL data).
  const [tableNo, setTableNo] = useState<string | null>(null);

  useEffect(() => {
    setTableNo(new URLSearchParams(window.location.search).get("table"));
  }, []);

  useEffect(() => {
    let cancelled = false;
    setState({ status: "loading" });
    fetchRestaurant(slug)
      .then((info) => {
        if (cancelled) return;
        document.title = `${info.name} — Sarthi`;
        setState({ status: "ready", info });
      })
      .catch((err: Error) => {
        if (cancelled) return;
        setState({ status: /No restaurant/i.test(err.message) ? "missing" : "error" });
      });
    return () => {
      cancelled = true;
    };
  }, [slug]);

  if (state.status === "loading") {
    return (
      <>
        <RestaurantSkeleton />
        <WakingNotice />
      </>
    );
  }

  if (state.status === "missing") {
    return (
      <div className="mx-auto flex min-h-screen max-w-md flex-col items-center justify-center gap-3 p-6 text-center">
        <h1 className="text-lg font-semibold">We couldn&apos;t find that restaurant</h1>
        <p className="text-sm text-muted-foreground">Check the link or scan the QR code on your table again.</p>
        <Link href="/" className="text-sm underline underline-offset-4">
          Back to Sarthi
        </Link>
      </div>
    );
  }

  if (state.status === "error") {
    return (
      <div className="mx-auto flex min-h-screen max-w-md flex-col items-center justify-center gap-3 p-6 text-center">
        <h1 className="text-lg font-semibold">Having trouble loading the menu</h1>
        <p className="text-sm text-muted-foreground">
          The server may be waking up. Give it a minute and refresh the page.
        </p>
      </div>
    );
  }

  const { info } = state;
  const persona = personaForRestaurant(info);
  // Tint the whole page with the restaurant's own accent colour.
  const accent = info.accent_color
    ? ({ "--primary": info.accent_color, "--primary-foreground": "#ffffff" } as React.CSSProperties)
    : undefined;

  return (
    <div className="flex min-h-screen flex-col" style={accent}>
      <header className="flex items-center justify-between gap-3 border-b px-4 py-3">
        <div>
          <h1 className="text-lg font-semibold">{info.name}</h1>
          <p className="text-sm text-muted-foreground">
            {[info.cuisine, info.tagline].filter(Boolean).join(" · ")}
          </p>
        </div>
        {tableNo && <Badge variant="outline">Table {tableNo}</Badge>}
      </header>
      <div className="flex flex-1 flex-col">
        <OrderingPage persona={persona} restaurant={info.slug} tableNo={tableNo} />
      </div>
      <PhotoCredits slug={info.slug} />
    </div>
  );
}
