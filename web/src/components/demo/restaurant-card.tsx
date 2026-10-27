"use client";

import Link from "next/link";
import { ArrowRight, MessageCircle, QrCode } from "lucide-react";
import { QRCodeSVG } from "qrcode.react";

import { restaurantLink, useSiteOrigin } from "@/components/demo/use-site-origin";
import type { DemoRestaurant } from "@/lib/demo";

/** One demo restaurant on the landing page: open it on this screen, or scan it from a phone. */
export function RestaurantCard({ restaurant: r }: { restaurant: DemoRestaurant }) {
  const [origin] = useSiteOrigin();
  const link = restaurantLink(origin, r.slug, r.table);

  return (
    <article
      className="flex flex-col overflow-hidden rounded-2xl border bg-card shadow-sm transition-shadow hover:shadow-md"
      style={{ borderTopColor: r.accent, borderTopWidth: 4 }}
    >
      <div className="flex flex-1 flex-col gap-4 p-5">
        <div>
          <p className="text-xs font-medium tracking-wide uppercase" style={{ color: r.accent }}>
            {r.cuisine} · {r.dishes}
          </p>
          <h3 className="mt-1 text-xl font-semibold">{r.name}</h3>
          <p className="mt-1 text-sm text-muted-foreground">{r.pitch}</p>
        </div>

        <ul className="flex flex-wrap gap-1.5">
          {r.highlights.map((h) => (
            <li key={h} className="rounded-full bg-muted px-2.5 py-1 text-xs text-muted-foreground">
              {h}
            </li>
          ))}
        </ul>

        <div className="rounded-xl bg-muted/60 p-3">
          <p className="mb-1.5 flex items-center gap-1.5 text-xs font-medium">
            <MessageCircle className="size-3.5" /> Try asking Kabir
          </p>
          <ul className="flex flex-col gap-1 text-sm text-muted-foreground">
            {r.tryAsking.map((q) => (
              <li key={q}>&ldquo;{q}&rdquo;</li>
            ))}
          </ul>
        </div>

        <div className="mt-auto flex items-center gap-4 pt-1">
          <div className="flex size-24 shrink-0 items-center justify-center rounded-lg border bg-white p-1.5">
            {origin ? (
              <QRCodeSVG value={link} size={84} />
            ) : (
              <QrCode className="size-8 text-muted-foreground/40" />
            )}
          </div>
          <div className="flex flex-1 flex-col gap-2">
            <p className="text-xs text-muted-foreground">
              Scan with your phone, as a guest at table {r.table} would.
            </p>
            <Link
              href={`/r/${r.slug}?table=${r.table}`}
              className="inline-flex h-9 items-center justify-center gap-1.5 rounded-lg px-3 text-sm font-medium text-white transition-opacity hover:opacity-90"
              style={{ backgroundColor: r.accent }}
            >
              Open this restaurant <ArrowRight className="size-4" />
            </Link>
          </div>
        </div>
      </div>
    </article>
  );
}
