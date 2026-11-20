"use client";

import { Check, Mic, Search } from "lucide-react";
import { useMemo, useState } from "react";

import { ChatPanel } from "@/components/chat/chat-panel";
import { Monogram, Stepper, VegMark, agentRole, isStore, lineKey, lineLabel, placeholderFor, sum, useMenu, welcomeLine } from "@/components/guest/parts";
import { PhotoCredits } from "@/components/photo-credits";
import { SpeechToggle } from "@/components/speech-toggle";
import { BillStep, DoneStep } from "@/components/table/table-steps";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { CallStrip } from "@/components/voice/call-strip";
import { CallerNumberDialog } from "@/components/voice/caller-number-dialog";
import type { ChatSession } from "@/hooks/use-chat-session";
import type { useRealtimeCall } from "@/hooks/use-realtime-call";
import type { TableSession } from "@/hooks/use-table-session";
import type { MenuItem, RestaurantInfo } from "@/lib/api";
import type { Persona } from "@/lib/personas";
import { cn, formatPrice } from "@/lib/utils";

type View = "menu" | "bill" | "done";

/**
 * The guest's page on a laptop or desktop: the whole screen, not a phone column. A category rail and a card
 * grid on the left, and on the right (always in view) the order and the agent: chat inline, a call one click
 * away. It shares every hook with the phone layout (guest-app.tsx), so the cart, table rounds and calls are
 * the same; only the arrangement differs. Shown from Tailwind's `lg` up.
 */
export function GuestDesktop({
  info,
  persona,
  tableNo,
  session,
  table,
  call,
}: {
  info: RestaurantInfo;
  persona: Persona;
  tableNo: string | null;
  session: ChatSession;
  table: TableSession;
  call: ReturnType<typeof useRealtimeCall>;
}) {
  const store = isStore(info);
  const { items, failed } = useMenu(persona, info);
  const [category, setCategory] = useState("All");
  const [query, setQuery] = useState("");
  const [picked, setPicked] = useState<View>("menu");
  const view: View = picked === "menu" && table.table?.payment_method ? "done" : picked;

  const categories = useMemo(() => {
    const counts = new Map<string, number>();
    for (const item of items ?? []) counts.set(item.category, (counts.get(item.category) ?? 0) + 1);
    return [{ name: "All", count: items?.length ?? 0 }, ...Array.from(counts, ([name, count]) => ({ name, count }))];
  }, [items]);

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (items ?? []).filter(
      (item) =>
        (category === "All" || item.category === category) &&
        (!q || item.name.toLowerCase().includes(q) || (item.brand ?? "").toLowerCase().includes(q) || item.description.toLowerCase().includes(q))
    );
  }, [category, items, query]);

  const quantities = useMemo(() => new Map(session.cart.map((line) => [lineKey(line.id, line.variant), line.quantity])), [session.cart]);
  const quantityOf = (id: string, variant?: string) => quantities.get(lineKey(id, variant)) ?? 0;
  const add = (id: string, variant?: string) => session.addItemDirect(id, 1, variant);
  const remove = (id: string, variant?: string) => session.removeItemDirect(id, 1, variant);

  return (
    <div className="flex h-dvh flex-col bg-background text-foreground">
      <CallerNumberDialog prompt={call.numberPrompt} agentName={persona.agentName} />

      <header className="flex shrink-0 items-center gap-4 border-b px-6 py-3">
        <Monogram info={info} className="size-11 text-xl" />
        <div className="min-w-0 flex-1">
          <h1 className="truncate font-heading text-xl leading-tight font-semibold">{info.name}</h1>
          <p className="truncate text-sm text-muted-foreground">
            {[info.cuisine, info.tagline, tableNo ? `Table ${tableNo}` : null].filter(Boolean).join(" · ")}
          </p>
        </div>
        <SpeechToggle />
        <Button className="h-10 gap-2 px-4" onClick={() => void call.start()} disabled={call.connection !== null || call.isConnecting}>
          <Mic className="size-4" />
          Talk to {persona.agentName}
        </Button>
      </header>

      <div className="grid min-h-0 flex-1 grid-cols-[minmax(0,1fr)_380px] xl:grid-cols-[240px_minmax(0,1fr)_420px] 2xl:grid-cols-[260px_minmax(0,1fr)_460px]">
        <nav aria-label="Sections" className="hidden overflow-y-auto border-r px-3 py-5 xl:block">
          <p className="px-3 pb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">{store ? "Aisles" : "Menu"}</p>
          <ul className="flex flex-col gap-0.5">
            {categories.map((c) => (
              <li key={c.name}>
                <button
                  type="button"
                  aria-current={c.name === category}
                  onClick={() => {
                    setPicked("menu");
                    setCategory(c.name);
                  }}
                  className={cn(
                    "flex w-full items-center justify-between rounded-[var(--radius)] px-3 py-2 text-left text-sm font-medium",
                    c.name === category ? "bg-primary text-primary-foreground" : "hover:bg-muted"
                  )}
                >
                  <span className="truncate">{c.name}</span>
                  <span className={cn("text-xs", c.name === category ? "text-primary-foreground/80" : "text-muted-foreground")}>{c.count}</span>
                </button>
              </li>
            ))}
          </ul>
        </nav>

        <main className="min-w-0 overflow-y-auto">
          {view === "bill" && (
            <div className="mx-auto flex max-w-xl flex-col gap-4 p-8">
              <BillStep t={table} restaurantName={info.name} onBack={() => setPicked("menu")} onPaid={() => setPicked("done")} />
              {table.error && <p className="text-sm text-destructive">{table.error}</p>}
            </div>
          )}
          {view === "done" && (
            <div className="mx-auto flex max-w-xl flex-col gap-4 p-8 pt-16">
              <DoneStep t={table} restaurantName={info.name} />
              {table.error && <p className="text-sm text-destructive">{table.error}</p>}
            </div>
          )}
          {view === "menu" && (
            <div className="flex flex-col gap-6 p-6 xl:p-8">
              <section className="flex flex-col gap-5 rounded-2xl bg-primary/10 p-6">
                <div className="max-w-3xl">
                  <p className="text-sm font-medium text-primary">
                    {persona.agentName} · {agentRole(info)}
                  </p>
                  <p className="mt-1 font-heading text-2xl leading-snug font-semibold">{welcomeLine(info, persona)}</p>
                </div>
                <div className="relative w-full max-w-md">
                  <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
                  <Input
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    placeholder={store ? "Search items or brands" : "Search the menu"}
                    aria-label="Search"
                    className="h-11 bg-background pl-9"
                  />
                </div>
              </section>

              <div className="flex gap-2 overflow-x-auto xl:hidden" role="tablist" aria-label="Sections">
                {categories.map((c) => (
                  <button
                    key={c.name}
                    type="button"
                    aria-pressed={c.name === category}
                    onClick={() => setCategory(c.name)}
                    className={cn(
                      "h-10 shrink-0 rounded-[var(--radius)] border px-4 text-sm font-medium",
                      c.name === category ? "border-foreground bg-foreground text-background" : "hover:bg-muted"
                    )}
                  >
                    {c.name}
                  </button>
                ))}
              </div>

              {items === null ? (
                <div className="grid grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-4">
                  {Array.from({ length: 8 }).map((_, i) => (
                    <Skeleton key={i} className="h-64 rounded-2xl" />
                  ))}
                </div>
              ) : failed ? (
                <p className="py-10 text-muted-foreground">Couldn&apos;t load the list right now. Give it a minute and refresh.</p>
              ) : shown.length === 0 ? (
                <p className="py-10 text-muted-foreground">Nothing matches that. Try another word, or ask {persona.agentName}.</p>
              ) : (
                <ul className="grid grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-4">
                  {shown.map((item) => (
                    <li key={item.id}>
                      <ItemCard item={item} store={store} quantityOf={quantityOf} onAdd={add} onRemove={remove} />
                    </li>
                  ))}
                </ul>
              )}
              <PhotoCredits slug={info.slug} />
            </div>
          )}
        </main>

        <aside className="flex min-h-0 flex-col gap-4 border-l bg-muted/30 p-4">
          <OrderPanel
            info={info}
            persona={persona}
            store={store}
            session={session}
            table={table}
            onAdd={add}
            onRemove={remove}
            onBill={() => setPicked("bill")}
          />
          <AgentPanel info={info} persona={persona} session={session} call={call} />
        </aside>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------- menu --

function ItemCard({
  item,
  store,
  quantityOf,
  onAdd,
  onRemove,
}: {
  item: MenuItem;
  store: boolean;
  quantityOf: (id: string, variant?: string) => number;
  onAdd: (id: string, variant?: string) => void;
  onRemove: (id: string, variant?: string) => void;
}) {
  const variants = item.variants ?? [];
  const unavailable = item.is_available === false;
  const spice = item.spice_level && item.spice_level !== "none" ? item.spice_level : null;

  return (
    <article className={cn("flex h-full flex-col overflow-hidden rounded-2xl border bg-card", unavailable && "opacity-60")}>
      {item.image_url && (
        <div className="relative aspect-[16/10] bg-primary/10">
          {/* eslint-disable-next-line @next/next/no-img-element -- photos live on any host */}
          <img src={item.image_url} alt="" loading="lazy" className="size-full object-cover" />
          {unavailable && <span className="absolute top-3 left-3 rounded-full bg-background px-2.5 py-1 text-xs font-medium">Not available</span>}
        </div>
      )}
      <div className="flex flex-1 flex-col gap-2 p-4">
        {unavailable && !item.image_url && <span className="w-fit rounded-full bg-muted px-2.5 py-1 text-xs font-medium">Not available</span>}
        <div className="flex items-start gap-2">
          {!store && typeof item.veg === "boolean" && <span className="mt-1"><VegMark veg={item.veg} /></span>}
          <div className="min-w-0">
            <h3 className="leading-snug font-semibold">{item.name}</h3>
            {store && item.brand && <p className="text-xs text-muted-foreground">{item.brand}</p>}
          </div>
        </div>
        {item.description && <p className="line-clamp-2 text-sm text-muted-foreground">{item.description}</p>}
        <div className="mt-auto flex flex-col gap-2 pt-2">
          {variants.length === 0 ? (
            <div className="flex items-center justify-between gap-3">
              <p className="font-medium">
                {formatPrice(item.price)}
                {spice && <span className="ml-2 text-xs font-normal text-muted-foreground capitalize">{spice}</span>}
              </p>
              {!unavailable && (
                <Stepper compact quantity={quantityOf(item.id)} label={item.name} onAdd={() => onAdd(item.id)} onRemove={() => onRemove(item.id)} />
              )}
            </div>
          ) : (
            !unavailable &&
            variants.map((v) => (
              <div key={v.name} className="flex items-center justify-between gap-3">
                <span className="text-sm">
                  {v.name} · <span className="font-medium">{formatPrice(v.price)}</span>
                </span>
                <Stepper
                  compact
                  quantity={quantityOf(item.id, v.name)}
                  label={`${item.name} (${v.name})`}
                  onAdd={() => onAdd(item.id, v.name)}
                  onRemove={() => onRemove(item.id, v.name)}
                />
              </div>
            ))
          )}
        </div>
      </div>
    </article>
  );
}

// --------------------------------------------------------------------- order --

function OrderPanel({
  info,
  persona,
  store,
  session,
  table: t,
  onAdd,
  onRemove,
  onBill,
}: {
  info: RestaurantInfo;
  persona: Persona;
  store: boolean;
  session: ChatSession;
  table: TableSession;
  onAdd: (id: string, variant?: string) => void;
  onRemove: (id: string, variant?: string) => void;
  onBill: () => void;
}) {
  // A table's page sends rounds to the kitchen itself; a store, or a restaurant opened from a link rather than a
  // table's QR code, has the agent place the order (it takes the address and reads it back).
  const kitchen = !store && t.active;
  const rounds = kitchen ? (t.table?.rounds ?? 0) : 0;
  const lines = kitchen ? t.unsent : session.cart;
  const ordered = t.table?.ordered ?? [];
  const asking = session.isSending;

  return (
    <section aria-label="Your order" className="flex max-h-[55%] min-h-0 flex-col rounded-2xl border bg-background">
      <div className="flex items-center justify-between border-b px-4 py-3">
        <h2 className="font-heading text-lg font-semibold">Your order</h2>
        {lines.length > 0 && <span className="text-sm text-muted-foreground">{lines.reduce((n, l) => n + l.quantity, 0)} items</span>}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-4">
        {lines.length === 0 && rounds === 0 && (
          <p className="py-8 text-center text-sm text-muted-foreground">
            Nothing here yet. Add {store ? "an item" : "a dish"} from the list, or ask {persona.agentName}.
          </p>
        )}
        {lines.map((line) => (
          <div key={lineKey(line.id, line.variant)} className="flex items-center gap-3 border-b py-3 last:border-b-0">
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium">{lineLabel(line)}</p>
              <p className="text-xs text-muted-foreground">{formatPrice(line.price)} each</p>
            </div>
            <Stepper compact filled={false} quantity={line.quantity} label={lineLabel(line)} onAdd={() => onAdd(line.id, line.variant)} onRemove={() => onRemove(line.id, line.variant)} />
            <span className="w-16 text-right text-sm font-medium">{formatPrice(line.price * line.quantity)}</span>
          </div>
        ))}

        {kitchen && t.suggestion && (
          <div className="my-3 rounded-[var(--radius)] bg-muted p-3">
            <p className="text-xs font-semibold text-muted-foreground">{persona.agentName} suggests</p>
            <p className="mt-1 text-sm">{t.suggestion.reason}</p>
            <div className="mt-2 flex gap-2">
              <Button className="h-9 flex-1 text-sm" onClick={() => void t.acceptSuggestion()}>
                Add {t.suggestion.name} · {formatPrice(t.suggestion.price)}
              </Button>
              <Button variant="ghost" className="h-9 text-sm" onClick={() => void t.dismissSuggestion()}>
                No thanks
              </Button>
            </div>
          </div>
        )}

        {rounds > 0 && (
          <div className="my-3 flex flex-col gap-2">
            <div className="flex items-center gap-2">
              <span className="flex size-6 items-center justify-center rounded-full bg-primary text-primary-foreground">
                <Check className="size-3.5" aria-hidden="true" />
              </span>
              <p className="text-sm font-semibold">The kitchen has your order{rounds > 1 ? ` · ${rounds} rounds` : ""}</p>
            </div>
            {ordered.map((line) => (
              <div key={lineKey(line.id, line.variant)} className="flex justify-between gap-3 text-sm text-muted-foreground">
                <span>
                  {line.quantity} × {lineLabel(line)}
                </span>
                <span>{formatPrice(line.price * line.quantity)}</span>
              </div>
            ))}
            {!t.table?.food_served && (
              <Button variant="outline" className="mt-1 h-9 text-sm" disabled={t.busy} onClick={() => void t.foodServed()}>
                My food is here
              </Button>
            )}
          </div>
        )}
        {t.error && <p className="py-2 text-sm text-destructive">{t.error}</p>}
      </div>

      <div className="flex flex-col gap-2 border-t p-4">
        {kitchen ? (
          <>
            {t.unsent.length > 0 && (
              <Button className="h-12 justify-between px-4 text-base" disabled={t.busy} onClick={() => void t.send()}>
                <span>{t.busy ? "Sending…" : "Send to kitchen"}</span>
                <span>{formatPrice(sum(t.unsent))}</span>
              </Button>
            )}
            {rounds > 0 && (
              <Button variant={t.unsent.length > 0 ? "outline" : "default"} className="h-11" onClick={onBill}>
                Get the bill
              </Button>
            )}
          </>
        ) : (
          lines.length > 0 && (
            <>
              <Button
                className="h-12 justify-between px-4 text-base"
                disabled={asking}
                onClick={() =>
                  void session.sendText("That's all, please place my order.")
                }
              >
                <span>{asking ? "One moment…" : `Ask ${persona.agentName} to place it`}</span>
                <span>{formatPrice(sum(lines))}</span>
              </Button>
              <p className="text-center text-xs text-muted-foreground">
                {store
                  ? `${persona.agentName} will confirm your address${info.business_type === "pharmacy" ? " and any prescription" : ""} before it goes through.`
                  : `${persona.agentName} will confirm it with you before it goes through.`}
              </p>
            </>
          )
        )}
      </div>
    </section>
  );
}

// --------------------------------------------------------------------- agent --

function AgentPanel({
  info,
  persona,
  session,
  call,
}: {
  info: RestaurantInfo;
  persona: Persona;
  session: ChatSession;
  call: ReturnType<typeof useRealtimeCall>;
}) {
  return (
    <section aria-label={`Talk to ${persona.agentName}`} className="flex min-h-0 flex-1 flex-col gap-2">
      {call.connection && <CallStrip agentName={persona.agentName} connection={call.connection} onEnd={call.end} onFail={call.fail} />}
      {call.error && <p className="text-xs text-destructive">{call.error}</p>}
      <ChatPanel
        persona={persona}
        session={session}
        placeholder={placeholderFor(info, persona)}
        scrollHeight="auto"
        onRequestCall={() => void call.start()}
        callBusy={call.connection !== null || call.isConnecting}
      />
    </section>
  );
}
