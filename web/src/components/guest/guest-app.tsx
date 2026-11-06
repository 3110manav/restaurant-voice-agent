"use client";

import { Check, ChevronLeft, Mic, Minus, Plus, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { ChatPanel } from "@/components/chat/chat-panel";
import { LanguageToggle } from "@/components/language-toggle";
import { PhotoCredits } from "@/components/photo-credits";
import { BillStep, DoneStep } from "@/components/table/table-steps";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { CallStrip } from "@/components/voice/call-strip";
import { useChatSession } from "@/hooks/use-chat-session";
import { useRealtimeCall } from "@/hooks/use-realtime-call";
import { useTableSession, type TableSession } from "@/hooks/use-table-session";
import { fetchMenu, type CartLine, type MenuItem, type RestaurantInfo } from "@/lib/api";
import type { Persona } from "@/lib/personas";
import { cn, formatPrice } from "@/lib/utils";

type Screen = "welcome" | "menu" | "order" | "bill" | "done";

const lineKey = (id: string, variant?: string | null) => `${id}|${variant ?? ""}`;
const lineLabel = (line: { name: string; variant?: string | null }) => (line.variant ? `${line.name} (${line.variant})` : line.name);
const sum = (lines: CartLine[]) => lines.reduce((total, line) => total + line.price * line.quantity, 0);

/**
 * The guest's side of a restaurant, as designed for the table QR pilot: a welcome card after the
 * scan, a list menu with a bottom bar, then full screens for the order (send to the kitchen, round by
 * round), the bill and the rating. One phone-width column on every screen size, in the restaurant's
 * own look (set by RestaurantPage). The waiter is a sheet over any screen; a voice call keeps running
 * as a strip while the guest browses.
 */
export function GuestApp({ info, persona, tableNo }: { info: RestaurantInfo; persona: Persona; tableNo: string | null }) {
  const session = useChatSession(persona, { restaurant: info.slug, tableNo });
  const table = useTableSession(session);
  const call = useRealtimeCall({
    persona,
    sessionId: session.sessionId,
    restaurant: info.slug,
    tableNo,
    language: session.language,
    onCartSync: session.refreshCart,
  });
  const [screen, setScreen] = useState<Screen>("welcome");
  const [talking, setTalking] = useState(false);

  // A guest coming back to the tab mid-meal skips the welcome card.
  const returning = (table.table?.rounds ?? 0) > 0 || Boolean(table.table?.payment_method);
  const current: Screen = screen === "welcome" && returning ? (table.table?.payment_method ? "done" : "order") : screen;

  async function beginCall() {
    if (await call.start()) setTalking(false);
  }

  return (
    <div className="relative mx-auto flex min-h-dvh w-full max-w-md flex-col sm:border-x">
      {current === "welcome" && (
        <Welcome
          info={info}
          persona={persona}
          tableNo={tableNo}
          language={session.language}
          onLanguage={session.setLanguage}
          onTalk={() => {
            setScreen("menu");
            setTalking(true);
          }}
          onMenu={() => setScreen("menu")}
        />
      )}

      {current === "menu" && (
        <MenuScreen
          info={info}
          persona={persona}
          tableNo={tableNo}
          cart={session.cart}
          table={table}
          language={session.language}
          onLanguage={session.setLanguage}
          onAdd={(id, variant) => session.addItemDirect(id, 1, variant)}
          onRemove={(id, variant) => session.removeItemDirect(id, 1, variant)}
          onTalk={() => setTalking(true)}
          onOrder={() => setScreen("order")}
          callLive={call.connection !== null}
        />
      )}

      {current === "order" && (
        <OrderScreen
          persona={persona}
          tableNo={tableNo}
          table={table}
          onAdd={(id, variant) => session.addItemDirect(id, 1, variant)}
          onRemove={(id, variant) => session.removeItemDirect(id, 1, variant)}
          onBack={() => setScreen("menu")}
          onBill={() => setScreen("bill")}
        />
      )}

      {current === "bill" && (
        <div className="flex flex-col gap-4 p-4">
          <BillStep t={table} restaurantName={info.name} onBack={() => setScreen("order")} onPaid={() => setScreen("done")} />
          {table.error && <p className="text-sm text-destructive">{table.error}</p>}
        </div>
      )}

      {current === "done" && (
        <div className="flex flex-col gap-4 p-4 pt-10">
          <DoneStep t={table} restaurantName={info.name} />
          {table.error && <p className="text-sm text-destructive">{table.error}</p>}
        </div>
      )}

      {call.connection && (
        <div className="fixed inset-x-0 bottom-24 z-40 mx-auto w-full max-w-md px-3">
          <CallStrip agentName={persona.agentName} connection={call.connection} onEnd={call.end} onFail={call.fail} />
        </div>
      )}

      {talking && (
        <Overlay title={`Talk to ${persona.agentName}`} onClose={() => setTalking(false)}>
          <ChatPanel
            persona={persona}
            session={session}
            placeholder={persona.placeholder}
            scrollHeight="45vh"
            onRequestCall={() => void beginCall()}
            callBusy={call.connection !== null || call.isConnecting}
          />
          {call.error && <p className="mt-2 text-xs text-destructive">{call.error}</p>}
        </Overlay>
      )}
    </div>
  );
}

// ------------------------------------------------------------------- welcome --

function Monogram({ info, className }: { info: RestaurantInfo; className?: string }) {
  if (info.logo_url) {
    // eslint-disable-next-line @next/next/no-img-element -- the owner's logo, any host
    return <img src={info.logo_url} alt="" className={cn("rounded-[var(--radius)] object-cover", className)} />;
  }
  return (
    <div
      aria-hidden="true"
      className={cn("flex items-center justify-center rounded-[var(--radius)] bg-primary font-heading text-primary-foreground", className)}
    >
      {info.name.trim().charAt(0).toUpperCase()}
    </div>
  );
}

function Welcome({
  info,
  persona,
  tableNo,
  language,
  onLanguage,
  onTalk,
  onMenu,
}: {
  info: RestaurantInfo;
  persona: Persona;
  tableNo: string | null;
  language: "en" | "hi";
  onLanguage: (next: "en" | "hi") => void;
  onTalk: () => void;
  onMenu: () => void;
}) {
  const hi = language === "hi";
  return (
    <div className="flex min-h-dvh flex-col px-6 pt-5 pb-6">
      <div className="flex justify-end">
        <LanguageToggle value={language} onChange={onLanguage} />
      </div>
      <div className="flex flex-1 flex-col justify-center gap-5">
        <Monogram info={info} className="size-16 text-3xl" />
        <div>
          <h1 className="font-heading text-4xl leading-tight font-semibold">{info.name}</h1>
          <p className="mt-2 text-muted-foreground">
            {[info.cuisine, tableNo ? `Table ${tableNo}` : null].filter(Boolean).join(" · ")}
          </p>
        </div>
        <p className="text-lg leading-snug">
          {hi
            ? `नमस्ते! मैं ${persona.agentName} हूँ। मेन्यू से ऑर्डर करें, या बस बताइए क्या खाने का मन है।`
            : `Welcome! I'm ${persona.agentName}, your waiter today. Order from the menu, or just tell me what you feel like eating.`}
        </p>
      </div>
      <div className="flex flex-col gap-2.5">
        <Button className="h-14 gap-2 text-base" onClick={onTalk}>
          <Mic className="size-5" />
          {hi ? `${persona.agentName} से बात करें` : `Talk to ${persona.agentName}`}
        </Button>
        <Button variant="outline" className="h-12 text-base" onClick={onMenu}>
          {hi ? "मेन्यू देखें" : "See the menu"}
        </Button>
        <p className="mt-2 text-center text-xs text-muted-foreground">Powered by Sarthi</p>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------- menu --

function VegMark({ veg }: { veg: boolean }) {
  return (
    <span
      role="img"
      aria-label={veg ? "Vegetarian" : "Non-vegetarian"}
      className={cn(
        "inline-flex size-3.5 shrink-0 items-center justify-center rounded-[2px] border-[1.5px]",
        veg ? "border-emerald-600 dark:border-emerald-400" : "border-amber-800 dark:border-amber-400"
      )}
    >
      {veg ? (
        <span className="size-1.5 rounded-full bg-emerald-600 dark:bg-emerald-400" />
      ) : (
        <span className="size-0 border-x-[3.5px] border-b-[6px] border-x-transparent border-b-amber-800 dark:border-b-amber-400" />
      )}
    </span>
  );
}

function Stepper({
  quantity,
  label,
  onAdd,
  onRemove,
  filled = true,
}: {
  quantity: number;
  label: string;
  onAdd: () => void;
  onRemove: () => void;
  filled?: boolean;
}) {
  if (quantity === 0) {
    return (
      <Button variant="outline" className="h-11 w-20 border-primary text-primary" onClick={onAdd} aria-label={`Add ${label}`}>
        Add
      </Button>
    );
  }
  return (
    <div className={cn("flex h-11 w-24 items-center justify-between rounded-[var(--radius)]", filled ? "bg-primary text-primary-foreground" : "border")}>
      <button type="button" className="flex h-11 w-9 items-center justify-center" onClick={onRemove} aria-label={`Remove one ${label}`}>
        <Minus className="size-4" />
      </button>
      <span className="text-sm font-semibold">{quantity}</span>
      <button type="button" className="flex h-11 w-9 items-center justify-center" onClick={onAdd} aria-label={`Add one more ${label}`}>
        <Plus className="size-4" />
      </button>
    </div>
  );
}

function DishRow({
  item,
  quantityOf,
  onAdd,
  onRemove,
}: {
  item: MenuItem;
  quantityOf: (id: string, variant?: string) => number;
  onAdd: (id: string, variant?: string) => void;
  onRemove: (id: string, variant?: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const variants = item.variants ?? [];
  const unavailable = item.is_available === false;
  const spice = item.spice_level && item.spice_level !== "none" ? ` · ${item.spice_level}` : "";

  return (
    <div className={cn("flex flex-col gap-2 border-b py-4", unavailable && "opacity-60")}>
      <div className="flex gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            {item.veg !== undefined && <VegMark veg={item.veg} />}
            <h3 className="font-semibold">{item.name}</h3>
          </div>
          <p className="mt-1 line-clamp-2 text-sm text-muted-foreground">{item.description}</p>
          <p className="mt-1.5 text-sm">
            <span className="font-medium">{variants.length ? `From ${formatPrice(item.price)}` : formatPrice(item.price)}</span>
            <span className="text-muted-foreground capitalize">{spice}</span>
          </p>
          {item.long_description && (
            <button
              type="button"
              onClick={() => setOpen((v) => !v)}
              className="mt-1 text-xs text-muted-foreground underline underline-offset-4"
            >
              {open ? "Hide details" : "About this dish"}
            </button>
          )}
        </div>
        <div className="flex shrink-0 flex-col items-end gap-2">
          {item.image_url && (
            // eslint-disable-next-line @next/next/no-img-element -- photos live on any host
            <img src={item.image_url} alt="" loading="lazy" className="size-20 rounded-[var(--radius)] object-cover" />
          )}
          {unavailable ? (
            <span className="text-xs text-muted-foreground">Not available</span>
          ) : (
            variants.length === 0 && (
              <Stepper quantity={quantityOf(item.id)} label={item.name} onAdd={() => onAdd(item.id)} onRemove={() => onRemove(item.id)} />
            )
          )}
        </div>
      </div>
      {open && (
        <div className="flex flex-col gap-1 text-sm text-muted-foreground">
          <p>{item.long_description}</p>
          {item.allergens && item.allergens.length > 0 && <p>Contains: {item.allergens.join(", ")}</p>}
        </div>
      )}
      {!unavailable &&
        variants.map((v) => (
          <div key={v.name} className="flex items-center justify-between gap-3 pl-5">
            <span className="text-sm">
              {v.name} · <span className="font-medium">{formatPrice(v.price)}</span>
            </span>
            <Stepper
              quantity={quantityOf(item.id, v.name)}
              label={`${item.name} (${v.name})`}
              onAdd={() => onAdd(item.id, v.name)}
              onRemove={() => onRemove(item.id, v.name)}
            />
          </div>
        ))}
    </div>
  );
}

function MenuScreen({
  info,
  persona,
  tableNo,
  cart,
  table,
  language,
  onLanguage,
  onAdd,
  onRemove,
  onTalk,
  onOrder,
  callLive,
}: {
  info: RestaurantInfo;
  persona: Persona;
  tableNo: string | null;
  cart: CartLine[];
  table: TableSession;
  language: "en" | "hi";
  onLanguage: (next: "en" | "hi") => void;
  onAdd: (id: string, variant?: string) => void;
  onRemove: (id: string, variant?: string) => void;
  onTalk: () => void;
  onOrder: () => void;
  callLive: boolean;
}) {
  const [items, setItems] = useState<MenuItem[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [category, setCategory] = useState("All");

  useEffect(() => {
    let cancelled = false;
    fetchMenu(persona.key, info.slug)
      .then((menu) => !cancelled && setItems(menu))
      .catch(() => {
        if (cancelled) return;
        setItems([]);
        setFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [info.slug, persona.key]);

  const categories = useMemo(() => ["All", ...Array.from(new Set((items ?? []).map((i) => i.category)))], [items]);
  const shown = useMemo(() => (items ?? []).filter((i) => category === "All" || i.category === category), [category, items]);
  const quantities = useMemo(() => new Map(cart.map((line) => [lineKey(line.id, line.variant), line.quantity])), [cart]);

  const unsentCount = table.unsent.reduce((n, line) => n + line.quantity, 0);
  const rounds = table.table?.rounds ?? 0;
  const dockLabel =
    unsentCount > 0
      ? `${unsentCount} ${unsentCount === 1 ? "item" : "items"} · View order`
      : rounds > 0
        ? "Your table · Get the bill"
        : "Your order";

  return (
    <>
      <header className="sticky top-0 z-30 flex items-center gap-3 border-b bg-background px-4 py-3">
        <Monogram info={info} className="size-10 text-xl" />
        <div className="min-w-0 flex-1">
          <p className="truncate font-heading text-lg leading-tight font-semibold">{info.name}</p>
          <p className="text-xs text-muted-foreground">{tableNo ? `Table ${tableNo}` : info.cuisine}</p>
        </div>
        <LanguageToggle value={language} onChange={onLanguage} />
      </header>

      <nav aria-label="Menu sections" className="sticky top-[65px] z-20 flex gap-2 overflow-x-auto border-b bg-background px-4 py-2.5">
        {categories.map((c) => (
          <button
            key={c}
            type="button"
            aria-pressed={c === category}
            onClick={() => setCategory(c)}
            className={cn(
              "h-10 shrink-0 rounded-[var(--radius)] border px-3.5 text-sm font-medium",
              c === category ? "border-foreground bg-foreground text-background" : "text-foreground"
            )}
          >
            {c}
          </button>
        ))}
      </nav>

      <main className="flex-1 px-4 pb-32">
        {items === null ? (
          <div className="flex flex-col gap-3 py-4">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-24" />
            ))}
          </div>
        ) : failed ? (
          <p className="py-8 text-sm text-muted-foreground">Couldn&apos;t load the menu right now. Give it a minute and refresh.</p>
        ) : (
          shown.map((item) => (
            <DishRow
              key={item.id}
              item={item}
              quantityOf={(id, variant) => quantities.get(lineKey(id, variant)) ?? 0}
              onAdd={onAdd}
              onRemove={onRemove}
            />
          ))
        )}
        <PhotoCredits slug={info.slug} />
      </main>

      <div className="fixed inset-x-0 bottom-0 z-40 mx-auto w-full max-w-md px-3 pb-[max(0.75rem,env(safe-area-inset-bottom))]">
        <div className="flex gap-2 rounded-2xl border bg-background p-2 shadow-lg">
          <Button
            variant="outline"
            className="size-14 shrink-0"
            onClick={onTalk}
            aria-label={`Talk to ${persona.agentName}`}
            disabled={callLive}
          >
            <Mic className="size-5" />
          </Button>
          <Button className="h-14 flex-1 justify-between px-4 text-base" onClick={onOrder}>
            <span>{dockLabel}</span>
            {unsentCount > 0 && <span>{formatPrice(sum(table.unsent))}</span>}
          </Button>
        </div>
      </div>
    </>
  );
}

// --------------------------------------------------------------------- order --

function OrderScreen({
  persona,
  tableNo,
  table: t,
  onAdd,
  onRemove,
  onBack,
  onBill,
}: {
  persona: Persona;
  tableNo: string | null;
  table: TableSession;
  onAdd: (id: string, variant?: string) => void;
  onRemove: (id: string, variant?: string) => void;
  onBack: () => void;
  onBill: () => void;
}) {
  const rounds = t.table?.rounds ?? 0;
  const ordered = t.table?.ordered ?? [];

  return (
    <div className="flex min-h-dvh flex-col">
      <header className="flex items-center gap-1 px-1 py-2">
        <button type="button" onClick={onBack} aria-label="Back to the menu" className="flex size-11 items-center justify-center">
          <ChevronLeft className="size-5" />
        </button>
        <h1 className="font-heading text-2xl font-semibold">Your order{tableNo ? ` · Table ${tableNo}` : ""}</h1>
      </header>

      <div className="flex flex-1 flex-col gap-5 px-4 pb-6">
        {!t.active && (
          <p className="rounded-lg border border-dashed p-3 text-sm text-muted-foreground">
            To order from your table, scan the QR code on it.
          </p>
        )}

        {t.unsent.length > 0 && (
          <section className="flex flex-col">
            {rounds > 0 && <h2 className="mb-1 text-sm font-medium text-muted-foreground">Not sent to the kitchen yet</h2>}
            {t.unsent.map((line) => (
              <div key={lineKey(line.id, line.variant)} className="flex items-center gap-3 border-b py-3">
                <div className="min-w-0 flex-1">
                  <p className="font-medium">{lineLabel(line)}</p>
                  <p className="text-xs text-muted-foreground">{formatPrice(line.price)} each</p>
                </div>
                <Stepper
                  filled={false}
                  quantity={line.quantity}
                  label={lineLabel(line)}
                  onAdd={() => onAdd(line.id, line.variant)}
                  onRemove={() => onRemove(line.id, line.variant)}
                />
                <span className="w-16 text-right text-sm font-medium">{formatPrice(line.price * line.quantity)}</span>
              </div>
            ))}
          </section>
        )}

        {t.suggestion && (
          <div className="rounded-[var(--radius)] bg-muted p-4">
            <p className="text-xs font-semibold text-muted-foreground">{persona.agentName} suggests</p>
            <p className="mt-1">{t.suggestion.reason}</p>
            <div className="mt-3 flex gap-2">
              <Button className="h-11 flex-1" onClick={() => void t.acceptSuggestion()}>
                Add {t.suggestion.name} · {formatPrice(t.suggestion.price)}
              </Button>
              <Button variant="ghost" className="h-11" onClick={() => void t.dismissSuggestion()}>
                No thanks
              </Button>
            </div>
          </div>
        )}

        {t.unsent.length === 0 && rounds === 0 && (
          <p className="py-10 text-center text-muted-foreground">
            Nothing here yet. Add a dish, or ask {persona.agentName} what to order.
          </p>
        )}

        {rounds > 0 && (
          <section className="flex flex-col gap-3">
            <div className="flex items-start gap-3">
              <span className="flex size-10 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground">
                <Check className="size-5" aria-hidden="true" />
              </span>
              <div>
                <h2 className="font-heading text-xl font-semibold">The kitchen has your order</h2>
                <p className="text-sm text-muted-foreground">
                  {rounds === 1 ? "Round 1." : `${rounds} rounds.`} No need to wait for anyone: order more or get the bill from here.
                </p>
              </div>
            </div>
            <div className="rounded-[var(--radius)] border px-4 py-1">
              {ordered.map((line) => (
                <div key={lineKey(line.id, line.variant)} className="flex justify-between gap-3 py-2 text-sm">
                  <span>
                    {line.quantity} × {lineLabel(line)}
                  </span>
                  <span className="font-medium">{formatPrice(line.price * line.quantity)}</span>
                </div>
              ))}
            </div>
            {t.table?.food_served ? (
              <p className="text-sm font-medium">Enjoy your meal.</p>
            ) : (
              <Button variant="outline" className="h-12" disabled={t.busy} onClick={() => void t.foodServed()}>
                My food is here
              </Button>
            )}
          </section>
        )}

        {t.error && <p className="text-sm text-destructive">{t.error}</p>}
      </div>

      <div className="sticky bottom-0 flex flex-col gap-2 border-t bg-background px-4 pt-3 pb-[max(1rem,env(safe-area-inset-bottom))]">
        {t.unsent.length > 0 && (
          <Button className="h-14 justify-between px-4 text-base" disabled={t.busy || !t.active} onClick={() => void t.send()}>
            <span>{t.busy ? "Sending…" : "Send to kitchen"}</span>
            <span>{formatPrice(sum(t.unsent))}</span>
          </Button>
        )}
        {rounds > 0 && (
          <Button variant={t.unsent.length > 0 ? "outline" : "default"} className="h-12 text-base" onClick={onBill}>
            Get the bill
          </Button>
        )}
        <Button variant="ghost" className="h-11" onClick={onBack}>
          {rounds > 0 ? "Order more" : "Back to the menu"}
        </Button>
      </div>
    </div>
  );
}

// ------------------------------------------------------------------- overlay --

function Overlay({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/45" onClick={onClose}>
      <div
        role="dialog"
        aria-label={title}
        className="flex max-h-[85dvh] w-full max-w-md flex-col rounded-t-2xl bg-background p-4 text-foreground"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-2 flex items-center justify-between">
          <h2 className="font-heading text-xl font-semibold">{title}</h2>
          <button type="button" onClick={onClose} aria-label="Close" className="flex size-11 items-center justify-center">
            <X className="size-5" />
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto">{children}</div>
      </div>
    </div>
  );
}
