"use client";

import { useEffect, useState } from "react";
import { Mic, Phone, ShoppingBag, X } from "lucide-react";

import { ChatPanel } from "@/components/chat/chat-panel";
import { OrderPanel } from "@/components/chat/order-panel";
import { LanguageToggle } from "@/components/language-toggle";
import { BottomSheet } from "@/components/mobile/bottom-sheet";
import { Button } from "@/components/ui/button";
import { AgentOrb } from "@/components/voice/agent-orb";
import { CallStrip } from "@/components/voice/call-strip";
import type { ChatSession } from "@/hooks/use-chat-session";
import { useRealtimeCall } from "@/hooks/use-realtime-call";
import type { CartLine } from "@/lib/api";
import type { Persona } from "@/lib/personas";
import { formatPrice } from "@/lib/utils";

const lineKey = (line: CartLine) => `${line.id}|${line.variant ?? ""}`;

/** "Added Large Margherita" when the cart grew between two snapshots, else null. */
function describeAddition(before: CartLine[], after: CartLine[]): string | null {
  const had = new Map(before.map((line) => [lineKey(line), line.quantity]));
  const added = after.filter((line) => line.quantity > (had.get(lineKey(line)) ?? 0));
  if (added.length === 0) return null;
  if (added.length > 1) return `Added ${added.length} items`;
  const [line] = added;
  return `Added ${line.variant ? `${line.variant} ` : ""}${line.name}`;
}

type Sheet = "chat" | "cart" | "call" | null;

/**
 * The phone layout of the ordering page: a bar pinned to the bottom with the cart and an "Ask Kabir"
 * button, bottom sheets for the chat and the cart, and, while a voice call is live, a slim strip above
 * the bar so the guest can keep browsing and ordering while Kabir listens.
 */
export function MobileOrderingUI({ persona, session }: { persona: Persona; session: ChatSession }) {
  const [sheet, setSheet] = useState<Sheet>(null);
  const call = useRealtimeCall({
    persona,
    sessionId: session.sessionId,
    restaurant: session.restaurant,
    tableNo: session.tableNo,
    language: session.language,
    onCartSync: session.refreshCart,
  });

  // A brief "Added ..." note whenever the cart grows, however it grew (a tap, the chat, or the call).
  const [seenCart, setSeenCart] = useState(session.cart);
  const [toast, setToast] = useState<{ id: number; text: string } | null>(null);
  if (session.cart !== seenCart) {
    const text = describeAddition(seenCart, session.cart);
    setSeenCart(session.cart);
    if (text) setToast((previous) => ({ id: (previous?.id ?? 0) + 1, text }));
  }
  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(null), 2600);
    return () => clearTimeout(timer);
  }, [toast]);

  const count = session.cart.reduce((sum, line) => sum + line.quantity, 0);
  const total = session.cart.reduce((sum, line) => sum + line.price * line.quantity, 0);
  const live = call.connection !== null;

  async function beginCall() {
    if (await call.start()) setSheet(null); // the strip takes over; the guest is back at the menu
  }

  return (
    <>
      <div className="pointer-events-none fixed inset-x-0 bottom-0 z-40 flex flex-col gap-2 px-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] lg:hidden">
        <div className="pointer-events-auto flex flex-col gap-2">
          {call.error && !live && (
            <div className="flex items-center justify-between gap-2 rounded-xl border border-destructive/40 bg-background px-3 py-2 text-xs text-destructive shadow-lg">
              <span>{call.error}</span>
              <button type="button" onClick={call.clearError} aria-label="Dismiss" className="shrink-0">
                <X className="size-3.5" />
              </button>
            </div>
          )}
          {toast && (
            <p key={toast.id} className="animate-in fade-in slide-in-from-bottom-2 mx-auto w-fit rounded-full bg-foreground px-4 py-2 text-xs font-medium text-background shadow-lg">
              {toast.text}
            </p>
          )}
          {live && call.connection && (
            <CallStrip agentName={persona.agentName} connection={call.connection} onEnd={call.end} onFail={call.fail} />
          )}
          <div className="flex items-center gap-2 rounded-2xl border bg-background/95 p-2 shadow-lg backdrop-blur">
            <button
              type="button"
              onClick={() => setSheet("cart")}
              className="flex min-w-0 flex-1 items-center gap-3 rounded-xl px-2 py-1.5 text-left active:bg-muted"
              aria-label="View your order"
            >
              <span className="relative flex size-9 shrink-0 items-center justify-center rounded-full bg-muted">
                <ShoppingBag className="size-4" />
                {count > 0 && (
                  <span className="absolute -top-1 -right-1 flex size-4 items-center justify-center rounded-full bg-primary text-[10px] font-semibold text-primary-foreground">
                    {count}
                  </span>
                )}
              </span>
              <span className="flex min-w-0 flex-col leading-tight">
                <span className="text-sm font-semibold">{count > 0 ? `${count} ${count === 1 ? "item" : "items"}` : "Your order"}</span>
                <span className="truncate text-xs text-muted-foreground">{count > 0 ? `${formatPrice(total)} · View` : "Nothing yet"}</span>
              </span>
            </button>
            <Button className="h-11 shrink-0 gap-2 rounded-xl px-4" onClick={() => setSheet("chat")}>
              <Mic className="size-4" />
              Ask {persona.agentName}
            </Button>
          </div>
        </div>
      </div>

      {sheet === "chat" && (
        <BottomSheet title={persona.agentName} subtitle={persona.vertical} onClose={() => setSheet(null)}>
          <ChatPanel
            persona={persona}
            session={session}
            placeholder={persona.placeholder}
            scrollHeight="100%"
            onRequestCall={() => setSheet("call")}
            callBusy={live}
          />
        </BottomSheet>
      )}

      {sheet === "cart" && (
        <BottomSheet title="Your order" subtitle={count > 0 ? `${count} ${count === 1 ? "item" : "items"} · ${formatPrice(total)}` : undefined} onClose={() => setSheet(null)}>
          <div className="min-h-0 flex-1 overflow-y-auto pb-2">
            <OrderPanel
              cart={session.cart}
              serviceLog={session.serviceLog}
              serviceLogLabel={persona.hasServiceLog ? persona.serviceLogLabel : null}
            />
          </div>
        </BottomSheet>
      )}

      {sheet === "call" && (
        <BottomSheet title={`Call ${persona.agentName}`} subtitle="You can keep browsing the menu during the call" onClose={() => setSheet(null)}>
          <div className="flex flex-1 flex-col items-center justify-center gap-4 overflow-y-auto p-4">
            <AgentOrb className="size-28" state={call.isConnecting ? "connecting" : "idle"} />
            <LanguageToggle value={session.language} onChange={session.setLanguage} disabled={call.isConnecting} />
            <Button onClick={() => void beginCall()} disabled={call.isConnecting || !session.sessionId} className="h-11 gap-2 px-6">
              <Phone className="size-4" />
              {call.isConnecting ? "Connecting…" : `Call ${persona.agentName}`}
            </Button>
            {call.error && <p className="text-center text-xs text-destructive">{call.error}</p>}
            <button type="button" onClick={() => setSheet("chat")} className="text-xs text-muted-foreground underline-offset-4 hover:underline">
              Back to text chat
            </button>
          </div>
        </BottomSheet>
      )}
    </>
  );
}
