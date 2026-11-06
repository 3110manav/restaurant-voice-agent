import Link from "next/link";
import {
  ArrowRight,
  ClipboardList,
  Languages,
  Mic,
  Pencil,
  QrCode,
  Receipt,
  Search,
  Smartphone,
} from "lucide-react";

import { AgentCard } from "@/components/demo/agent-card";
import { RestaurantCard } from "@/components/demo/restaurant-card";
import { WarmBackend } from "@/components/warm-backend";
import { AGENTS } from "@/lib/agents";
import { DEMO_STORES } from "@/lib/demo";

const RESTAURANTS = DEMO_STORES.filter((s) => s.kind === "restaurant");
const DELIVERY_STORES = DEMO_STORES.filter((s) => s.kind !== "restaurant");

const STEPS = [
  { icon: QrCode, title: "A customer scans, calls or chats", body: "The menu or catalog opens in the browser. No app to install, no login." },
  { icon: Mic, title: "They talk to the agent, or type", body: "Ask what's good, what helps a headache, or just say what you want." },
  { icon: Receipt, title: "The shop gets the order", body: "Tagged with who ordered and where it goes. Table requests and prescriptions reach staff too." },
];

const OWNER_FEATURES = [
  { icon: Search, title: "Knows every item", body: "The agents answer from the owner's own descriptions and find things by meaning: “something creamy and mild”, “something for a sore throat”." },
  { icon: Pencil, title: "Edits in seconds", body: "Change a price, mark an item sold out or rewrite a description. Customers see it within seconds." },
  { icon: ClipboardList, title: "Orders and requests", body: "One live board for orders, table requests and anything else a customer asks for." },
  { icon: Languages, title: "Says it their way", body: "Handles misspellings, sizes and packs, English and Hindi, and asks when it isn't sure." },
];

export default function Home() {
  return (
    <div className="flex flex-1 flex-col bg-background">
      <WarmBackend />
      <header className="mx-auto flex w-full max-w-6xl items-center justify-between px-6 py-5">
        <span className="text-lg font-semibold tracking-tight">Sarthi</span>
        <nav className="flex items-center gap-5 text-sm text-muted-foreground">
          <a href="#agents" className="hover:text-foreground">Agents</a>
          <a href="#demo" className="hover:text-foreground">Live demo</a>
          <Link href="/demo" className="hidden hover:text-foreground sm:inline">QR sheet</Link>
          <Link href="/owner" className="rounded-lg border px-3 py-1.5 text-foreground hover:bg-muted">
            Owner login
          </Link>
        </nav>
      </header>

      <section className="mx-auto flex w-full max-w-4xl flex-col items-center gap-6 px-6 pt-12 pb-16 text-center sm:pt-20">
        <p className="rounded-full border bg-muted/50 px-3 py-1 text-xs text-muted-foreground">
          Voice agents for local business
        </p>
        <h1 className="text-4xl font-bold tracking-tight text-balance sm:text-6xl">
          An AI agent for every local counter.
        </h1>
        <p className="max-w-2xl text-base text-muted-foreground text-balance sm:text-lg">
          Restaurants, kirana stores, pharmacies and more. Customers scan a QR code, call or chat. Sarthi&apos;s agents
          know the catalog, take the order, and tell the shop what to do next.
        </p>
        <ul className="flex flex-wrap items-center justify-center gap-2">
          {AGENTS.map((a) => (
            <li
              key={a.name}
              className={`flex items-center gap-1.5 rounded-full border bg-card px-3 py-1 text-xs ${a.status === "soon" ? "border-dashed text-muted-foreground" : ""}`}
            >
              <span className="size-2 rounded-full" style={{ backgroundColor: a.accent }} />
              <span className="font-medium">{a.name}</span>
              <span className="text-muted-foreground">{a.works.split(" and ")[0].split(" that")[0]}</span>
            </li>
          ))}
        </ul>
        <div className="flex flex-col items-center gap-3 sm:flex-row">
          <a
            href="#agents"
            className="inline-flex h-11 items-center gap-2 rounded-xl bg-foreground px-5 text-sm font-medium text-background hover:opacity-90"
          >
            Meet the agents <ArrowRight className="size-4" />
          </a>
          <a
            href="#demo"
            className="inline-flex h-11 items-center rounded-xl border px-5 text-sm font-medium hover:bg-muted"
          >
            Try a live demo
          </a>
        </div>
      </section>

      <section id="agents" className="mx-auto w-full max-w-6xl scroll-mt-6 px-6 pb-16">
        <div className="mb-8">
          <h2 className="text-2xl font-bold tracking-tight sm:text-3xl">One platform, an agent for every trade</h2>
          <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
            Each agent has its own name, voice and manners, and solves a different problem. They share the same engine
            underneath: the conversation, the memory of every customer, and the owner&apos;s console.
          </p>
        </div>
        <div className="grid gap-5 md:grid-cols-2 lg:grid-cols-3">
          {AGENTS.map((agent) => (
            <AgentCard key={agent.name} agent={agent} />
          ))}
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
            <h2 className="text-2xl font-bold tracking-tight sm:text-3xl">Try them on a real menu</h2>
            <p className="mt-2 max-w-xl text-sm text-muted-foreground">
              Pick one and order as a customer would. On a laptop, scan the QR with your phone to see the real thing.
              Every store has its own menu, its own look and its own owner console.
            </p>
          </div>
          <Link href="/demo" className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground">
            <Smartphone className="size-4" /> Printable QR sheet
          </Link>
        </div>
        <h3 className="mb-3 text-sm font-semibold tracking-wide text-muted-foreground uppercase">Restaurants</h3>
        <div className="grid gap-5 md:grid-cols-3">
          {RESTAURANTS.map((r) => (
            <RestaurantCard key={r.slug} restaurant={r} />
          ))}
        </div>
        <h3 className="mt-10 mb-3 text-sm font-semibold tracking-wide text-muted-foreground uppercase">
          Stores that deliver
        </h3>
        <div className="grid gap-5 md:grid-cols-3">
          {DELIVERY_STORES.map((r) => (
            <RestaurantCard key={r.slug} restaurant={r} />
          ))}
        </div>
      </section>

      <section className="border-t bg-muted/30">
        <div className="mx-auto w-full max-w-6xl px-6 py-16">
          <h2 className="text-2xl font-bold tracking-tight sm:text-3xl">What the owner gets</h2>
          <p className="mt-2 max-w-xl text-sm text-muted-foreground">
            A console to run the catalog, with no engineer needed.
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
        <div className="mx-auto flex w-full max-w-6xl flex-col gap-3 px-6 py-8 text-sm text-muted-foreground">
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
            <span>The agents:</span>
            {AGENTS.map((a) => (
              <a key={a.name} href="#agents" className="underline-offset-4 hover:text-foreground hover:underline">
                {a.name} · {a.works}
              </a>
            ))}
          </div>
          <p className="text-xs">Sarthi · voice and text agents for restaurants, stores and more.</p>
        </div>
      </footer>
    </div>
  );
}
