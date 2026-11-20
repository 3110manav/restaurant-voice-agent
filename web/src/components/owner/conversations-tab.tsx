"use client";

import { useCallback, useState } from "react";

import { usePolled } from "@/components/owner/pilot-tabs";
import { Skeleton } from "@/components/ui/skeleton";
import {
  getConversation,
  listConversations,
  type ConversationSummary,
  type ConversationTurn,
  type OwnerRestaurant,
} from "@/lib/owner-api";
import { cn } from "@/lib/utils";

const CHANNEL: Record<string, string> = {
  chat: "Typed chat",
  "push-to-talk": "Voice message",
  "browser-call": "Voice call",
  phone: "Phone call",
  whatsapp: "WhatsApp",
};

const when = (iso: string) => new Date(iso).toLocaleString([], { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
const lastFour = (phone: string | null) => (phone ? `…${phone.slice(-4)}` : null);

/**
 * What guests and the agent said to each other, read back for the owner: a list of conversations, and the
 * turn-by-turn transcript of the one chosen. For a voice turn "heard" is what speech recognition made of the
 * guest's words, which is exactly what the agent acted on, so a mistake shows here. It refreshes while open, so a
 * live call can be followed. Only owners and managers see this tab (the API enforces it too).
 */
export function ConversationsTab({ restaurant }: { restaurant: OwnerRestaurant }) {
  const loadList = useCallback(() => listConversations(restaurant.id), [restaurant.id]);
  const { data: list, error } = usePolled<ConversationSummary[]>(loadList);
  const [picked, setPicked] = useState<string | null>(null);
  const selected = picked ?? list?.[0]?.session_id ?? null;

  return (
    <div className="flex flex-col gap-3">
      <div>
        <h2 className="text-lg font-semibold">Conversations</h2>
        <p className="text-sm text-muted-foreground">
          What your guests and the agent said, from typed chat, voice and phone. For a voice turn, &ldquo;heard&rdquo; is what
          speech recognition understood, so you can see where it mis-heard.
        </p>
      </div>
      {error && (
        <p className="text-sm text-destructive">
          {error} <span className="text-muted-foreground">If this keeps happening, check that supabase/migrations/005_conversation_turns.sql has been run.</span>
        </p>
      )}
      <div className="grid gap-4 lg:grid-cols-[340px_minmax(0,1fr)]">
        <ul className="flex max-h-[70vh] flex-col overflow-y-auto rounded-xl border bg-card">
          {list === null && <Skeleton className="m-3 h-20" />}
          {list?.length === 0 && (
            <li className="p-4 text-sm text-muted-foreground">
              No conversations yet. They appear here as guests chat or call.
            </li>
          )}
          {list?.map((c) => (
            <li key={c.session_id} className="border-b last:border-b-0">
              <button
                type="button"
                aria-pressed={c.session_id === selected}
                onClick={() => setPicked(c.session_id)}
                className={cn("flex w-full flex-col gap-1 px-4 py-3 text-left hover:bg-muted", c.session_id === selected && "bg-muted")}
              >
                <span className="flex items-center justify-between gap-2 text-xs text-muted-foreground">
                  <span>{when(c.last_at)}</span>
                  <span>
                    {c.turns} {c.turns === 1 ? "turn" : "turns"}
                    {c.table_no ? ` · table ${c.table_no}` : ""}
                    {lastFour(c.caller_phone) ? ` · ${lastFour(c.caller_phone)}` : ""}
                  </span>
                </span>
                <span className="line-clamp-2 text-sm font-medium">{c.preview}</span>
                <span className="text-xs text-muted-foreground">{c.channels.map((ch) => CHANNEL[ch] ?? ch).join(" · ")}</span>
              </button>
            </li>
          ))}
        </ul>
        <Transcript restaurantId={restaurant.id} sessionId={selected} />
      </div>
    </div>
  );
}

function Transcript({ restaurantId, sessionId }: { restaurantId: string; sessionId: string | null }) {
  const load = useCallback(
    () => (sessionId ? getConversation(restaurantId, sessionId) : Promise.resolve<ConversationTurn[]>([])),
    [restaurantId, sessionId]
  );
  const { data: turns } = usePolled<ConversationTurn[]>(load);

  if (!sessionId) return <div className="rounded-xl border p-6 text-sm text-muted-foreground">Pick a conversation to read it.</div>;
  if (turns === null) return <Skeleton className="h-64" />;

  return (
    <section aria-label="Transcript" className="flex max-h-[70vh] flex-col gap-4 overflow-y-auto rounded-xl border bg-card p-4">
      {turns.map((t) => {
        const voice = t.channel === "push-to-talk" || t.channel === "browser-call" || t.channel === "phone";
        return (
          <div key={t.id} className="flex flex-col gap-2">
            <p className="text-center text-xs text-muted-foreground">
              {when(t.created_at)} · {CHANNEL[t.channel] ?? t.channel}
              {t.speech ? ` · ${t.speech === "sarvam" ? "Sarvam" : "Groq"} voice` : ""}
              {t.language ? ` · ${t.language === "hi" ? "Hindi" : t.language === "hinglish" ? "Hinglish" : "English"}` : ""}
              {t.latency_ms ? ` · replied in ${(t.latency_ms / 1000).toFixed(1)}s` : ""}
            </p>
            <div className="ml-auto max-w-[85%] rounded-2xl rounded-br-sm bg-primary px-3.5 py-2 text-sm text-primary-foreground">
              {voice && <span className="mb-0.5 block text-[11px] opacity-80">Heard</span>}
              {t.customer_text}
            </div>
            <div className="max-w-[85%] rounded-2xl rounded-bl-sm bg-muted px-3.5 py-2 text-sm">{t.agent_text}</div>
          </div>
        );
      })}
    </section>
  );
}
