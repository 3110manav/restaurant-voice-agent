import Link from "next/link";
import {
  ArrowRight,
  ChefHat,
  ClipboardList,
  Languages,
  Mic,
  QrCode,
  Receipt,
  Search,
  Smartphone,
} from "lucide-react";

import { RestaurantCard } from "@/components/demo/restaurant-card";
import { WarmBackend } from "@/components/warm-backend";
import { DEMO_RESTAURANTS } from "@/lib/demo";
import { PERSONAS } from "@/lib/personas";

const STEPS = [
  { icon: QrCode, title: "Guest scans the table QR", body: "The menu opens in the browser. No app to install, no login." },
  { icon: Mic, title: "Talks to Kabir, or types", body: "Ask what's good, how spicy something is, or just say what you want." },
  { icon: Receipt, title: "The kitchen gets the order", body: "Tagged with the table. Water and bill requests reach staff too." },
];

const OWNER_FEATURES = [
  { icon: Search, title: "Knows every dish", body: "Kabir explains dishes from the owner's own descriptions, and finds things by meaning: “something creamy and mild”." },
  { icon: ChefHat, title: "Menu edits in seconds", body: "Change a price, mark a dish sold out, or edit a story. Guests see it within seconds." },
  { icon: ClipboardList, title: "Orders and table requests", body: "One live board for orders, water, bill and anything else a table asks for." },
  { icon: Languages, title: "Says it their way", body: "Handles misspellings, Half/Full portions and pizza sizes, and asks when it isn't sure." },
];

export default function Home() {
  return (
    <div className="flex flex-1 flex-col bg-background">
      <WarmBackend />
      <header className="mx-auto flex w-full max-w-6xl items-center justify-between px-6 py-5">
        <span className="text-lg font-semibold tracking-tight">Sarthi</span>
        <nav className="flex items-center gap-5 text-sm text-muted-foreground">
          <a href="#demo" className="hover:text-foreground">Live demo</a>
          <Link href="/demo" className="hidden hover:text-foreground sm:inline">QR sheet</Link>
          <Link href="/owner" className="rounded-lg border px-3 py-1.5 text-foreground hover:bg-muted">
            Owner login
          </Link>
        </nav>
      </header>

      <section className="mx-auto flex w-full max-w-4xl flex-col items-center gap-6 px-6 pt-12 pb-16 text-center sm:pt-20">
        <p className="rounded-full border bg-muted/50 px-3 py-1 text-xs text-muted-foreground">
          An AI waiter for every table
        </p>
        <h1 className="text-4xl font-bold tracking-tight text-balance sm:text-6xl">
          Meet Kabir, the waiter who never misses a table.
        </h1>
        <p className="max-w-2xl text-base text-muted-foreground text-balance sm:text-lg">
          Guests scan a QR code, ask about the menu and order by voice or text. Kabir knows every dish, takes the order
          and tells your staff what each table needs.
        </p>
        <div className="flex flex-col items-center gap-3 sm:flex-row">
          <a
            href="#demo"
            className="inline-flex h-11 items-center gap-2 rounded-xl bg-foreground px-5 text-sm font-medium text-background hover:opacity-90"
          >
            Try the live demo <ArrowRight className="size-4" />
          </a>
          <Link
            href="/owner"
            className="inline-flex h-11 items-center rounded-xl border px-5 text-sm font-medium hover:bg-muted"
          >
            I own a restaurant
          </Link>
        </div>
      </section>

      <section className="border-y bg-muted/30">
        <div className="mx-auto grid w-full max-w-6xl gap-6 px-6 py-12 sm:grid-cols-3">
          {STEPS.map(({ icon: Icon, title, body }, i) => (
            <div key={title} className="flex gap-4">
              <div className="flex size-10 shrink-0 items-center justify-center rounded-full bg-foreground text-background">
                <Icon className="size-5" />
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Step {i + 1}</p>
                <h2 className="font-semibold">{title}</h2>
                <p className="mt-1 text-sm text-muted-foreground">{body}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      <section id="demo" className="mx-auto w-full max-w-6xl scroll-mt-6 px-6 py-16">
        <div className="mb-8 flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h2 className="text-2xl font-bold tracking-tight sm:text-3xl">Three restaurants, three kinds of menu</h2>
            <p className="mt-2 max-w-xl text-sm text-muted-foreground">
              Pick one and order as a guest would. On a laptop, scan the QR with your phone to see the real thing.
              Every restaurant has its own menu, its own look and its own owner console.
            </p>
          </div>
          <Link href="/demo" className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground">
            <Smartphone className="size-4" /> Printable QR sheet
          </Link>
        </div>
        <div className="grid gap-5 md:grid-cols-3">
          {DEMO_RESTAURANTS.map((r) => (
            <RestaurantCard key={r.slug} restaurant={r} />
          ))}
        </div>
      </section>

      <section className="border-t bg-muted/30">
        <div className="mx-auto w-full max-w-6xl px-6 py-16">
          <h2 className="text-2xl font-bold tracking-tight sm:text-3xl">What the owner gets</h2>
          <p className="mt-2 max-w-xl text-sm text-muted-foreground">
            A console to run the menu, with no engineer needed.
          </p>
          <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {OWNER_FEATURES.map(({ icon: Icon, title, body }) => (
              <div key={title} className="rounded-xl border bg-card p-4">
                <Icon className="size-5 text-muted-foreground" />
                <h3 className="mt-3 font-semibold">{title}</h3>
                <p className="mt-1 text-sm text-muted-foreground">{body}</p>
              </div>
            ))}
          </div>
          <div className="mt-8">
            <Link
              href="/owner"
              className="inline-flex h-10 items-center gap-2 rounded-xl bg-foreground px-4 text-sm font-medium text-background hover:opacity-90"
            >
              Open the owner console <ArrowRight className="size-4" />
            </Link>
          </div>
        </div>
      </section>

      <footer className="border-t">
        <div className="mx-auto flex w-full max-w-6xl flex-col gap-4 px-6 py-8 text-sm text-muted-foreground">
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
            <span>More Sarthi agents:</span>
            {PERSONAS.filter((p) => p.key !== "waiter").map((p) => (
              <Link key={p.slug} href={`/chat/${p.slug}`} className="underline-offset-4 hover:text-foreground hover:underline">
                {p.agentName} · {p.vertical}
              </Link>
            ))}
          </div>
          <p className="text-xs">Sarthi · voice and text ordering for restaurants.</p>
        </div>
      </footer>
    </div>
  );
}
