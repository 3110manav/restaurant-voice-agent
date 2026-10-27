"use client";

import { useState, useSyncExternalStore } from "react";

const subscribe = () => () => {};
const configured = process.env.NEXT_PUBLIC_SITE_URL?.replace(/\/+$/, "");

/**
 * The address QR codes should point at. NEXT_PUBLIC_SITE_URL wins (set it to the
 * deployed site); otherwise the page's own origin. The server render has no URL, so
 * it is empty until hydration — QR codes never encode a wrong host. The setter lets
 * the /demo page override it, e.g. with a LAN address for a phone.
 */
export function useSiteOrigin(): [string, (value: string) => void] {
  const detected = useSyncExternalStore(
    subscribe,
    () => configured || window.location.origin,
    () => ""
  );
  const [override, setOverride] = useState<string | null>(null);
  return [override ?? detected, setOverride];
}

export function restaurantLink(origin: string, slug: string, table: string): string {
  return `${origin}/r/${slug}?table=${encodeURIComponent(table)}`;
}
