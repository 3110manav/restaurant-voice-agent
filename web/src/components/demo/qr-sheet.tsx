"use client";

import { Printer } from "lucide-react";
import { QRCodeSVG } from "qrcode.react";

import { restaurantLink, useSiteOrigin } from "@/components/demo/use-site-origin";
import { Input } from "@/components/ui/input";
import { DEMO_RESTAURANTS } from "@/lib/demo";

/** A printable page with one table QR per demo restaurant, each opening that restaurant directly. */
export function QrSheet() {
  const [origin, setOrigin] = useSiteOrigin();
  const isLocal = /localhost|127\.0\.0\.1/.test(origin);

  return (
    <div className="mx-auto w-full max-w-5xl px-6 py-8 print:max-w-none print:p-0">
      <div className="mb-8 flex flex-col gap-4 print:hidden">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold tracking-tight">Demo QR codes</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Print this page, or keep it on screen. Each code opens that restaurant straight to its table.
            </p>
          </div>
          <button
            type="button"
            onClick={() => window.print()}
            className="inline-flex h-9 items-center gap-2 rounded-lg bg-foreground px-3 text-sm font-medium text-background hover:opacity-90"
          >
            <Printer className="size-4" /> Print
          </button>
        </div>
        <label className="flex flex-col gap-1.5 text-sm">
          Site address the codes point to
          <Input value={origin} onChange={(e) => setOrigin(e.target.value.replace(/\/+$/, ""))} placeholder="https://your-site.vercel.app" />
        </label>
        {isLocal && (
          <p className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
            These codes point to this computer (<code>{origin}</code>), so a phone can&apos;t open them. Open this page on
            the deployed site, or type your Vercel address above, before you print.
          </p>
        )}
      </div>

      <div className="grid gap-6 sm:grid-cols-3 print:grid-cols-3 print:gap-4">
        {DEMO_RESTAURANTS.map((r) => {
          const link = restaurantLink(origin, r.slug, r.table);
          return (
            <section
              key={r.slug}
              className="flex break-inside-avoid flex-col items-center gap-3 rounded-2xl border bg-white p-6 text-center text-black"
              style={{ borderTopColor: r.accent, borderTopWidth: 6 }}
            >
              <h2 className="text-xl font-semibold">{r.name}</h2>
              <p className="-mt-2 text-sm text-neutral-500">{r.cuisine}</p>
              {origin && <QRCodeSVG value={link} size={180} level="M" />}
              <p className="text-base font-medium">Scan to order · Table {r.table}</p>
              <p className="text-xs text-neutral-500">Ask Kabir anything, then order by voice or text.</p>
              <p className="text-[10px] break-all text-neutral-400">{link}</p>
            </section>
          );
        })}
      </div>
    </div>
  );
}
