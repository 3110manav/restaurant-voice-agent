"use client";

import { useCallback, useEffect, useState } from "react";

import { usePolling } from "@/components/owner/activity-tabs";
import { CallTranscript } from "@/components/owner/call-transcript";
import { Pager } from "@/components/owner/support-tab";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  fetchCallDetail,
  fetchCallLog,
  fetchCallPhone,
  type CallCaller,
  type CallDetail,
  type CallLogDay,
  type CallLogRow,
  type CallOutcome,
} from "@/lib/owner-api";
import { cn, formatPrice } from "@/lib/utils";

const IST = "Asia/Kolkata";

const FILTERS: { key: CallOutcome | "all"; label: string }[] = [
  { key: "all", label: "All calls" },
  { key: "ordered", label: "Ordered" },
  { key: "callback", label: "Needs a call back" },
  { key: "abandoned", label: "No order" },
];

const OUTCOME_STYLE: Record<CallOutcome, string> = {
  ordered: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300",
  callback: "bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-300",
  abandoned: "bg-muted text-muted-foreground",
  in_progress: "bg-sky-100 text-sky-800 dark:bg-sky-950 dark:text-sky-300",
};

function shiftDay(day: string, by: number): string {
  const d = new Date(`${day}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() + by);
  return d.toISOString().slice(0, 10);
}

const clock = (iso: string) => new Date(iso).toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit", timeZone: IST });

const longDay = (day: string) =>
  new Date(`${day}T12:00:00Z`).toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "long", timeZone: IST });

function length(seconds: number | null): string {
  if (seconds == null) return "—";
  const s = Math.round(seconds);
  return s < 60 ? `${s} s` : `${Math.floor(s / 60)} min ${s % 60 ? `${s % 60} s` : ""}`.trim();
}

/** "Ritvik Doshi", or what kind of caller this was when there is no name. */
function callerName(caller: CallCaller): string {
  if (caller.name) return caller.name;
  if (caller.test_call) return "Test call";
  return "Unknown caller";
}

function callerNumber(caller: CallCaller): string {
  if (caller.source === "caller_id") return caller.phone ?? "";
  if (caller.source === "given") return `${caller.phone} (number given, no caller ID)`;
  return "No caller ID (browser test bed)";
}

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="flex flex-col gap-0.5 rounded-lg border bg-background px-4 py-3">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className="text-2xl font-semibold tabular-nums">{value}</span>
      {hint && <span className="text-xs text-muted-foreground">{hint}</span>}
    </div>
  );
}

/**
 * Every call to the restaurant, one day at a time (India time): the day's totals, a list of calls with who called
 * and what came of it, and the chosen call in full, with its order, its ticket and what was said.
 */
export function CallLogTab({ restaurantId }: { restaurantId: string }) {
  const [day, setDay] = useState<string | null>(null); // null: today, as the server counts it
  const [outcome, setOutcome] = useState<CallOutcome | "all">("all");
  const [picked, setPicked] = useState<string | null>(null);
  const [page, setPage] = useState(1);

  // Day, outcome and page are all filters the backend applies; the page shows what it sends.
  const load = useCallback(
    () => fetchCallLog(restaurantId, day ?? new Date().toLocaleDateString("en-CA", { timeZone: IST }), outcome, page),
    [restaurantId, day, outcome, page]
  );
  const { data, error } = usePolling<CallLogDay>(load);
  const shownDay = data?.day ?? day;
  const isToday = data ? data.day === data.today : day === null;
  const selected = picked && data?.calls.some((c) => c.id === picked) ? picked : (data?.calls[0]?.id ?? null);

  function goTo(next: string) {
    setPicked(null);
    setPage(1);
    setDay(data && next >= data.today ? null : next);
  }

  const totals = data?.totals;
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="mr-2 text-lg font-semibold">{shownDay ? longDay(shownDay) : "Today"}</h2>
        <Button size="sm" variant="outline" aria-label="Previous day" disabled={!shownDay} onClick={() => shownDay && goTo(shiftDay(shownDay, -1))}>
          ‹ Previous day
        </Button>
        <input
          type="date"
          aria-label="Pick a day"
          className="h-8 rounded-md border bg-background px-2 text-sm"
          value={shownDay ?? ""}
          max={data?.today}
          onChange={(e) => e.target.value && goTo(e.target.value)}
        />
        <Button size="sm" variant="outline" aria-label="Next day" disabled={isToday || !shownDay} onClick={() => shownDay && goTo(shiftDay(shownDay, 1))}>
          Next day ›
        </Button>
        {!isToday && (
          <Button size="sm" variant="ghost" onClick={() => goTo(data?.today ?? "")}>
            Today
          </Button>
        )}
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        <Stat
          label="Calls"
          value={totals ? String(totals.calls) : "—"}
          hint={totals?.test_calls ? `${totals.test_calls} test call${totals.test_calls > 1 ? "s" : ""} (no caller ID)` : "whole day"}
        />
        <Stat label="Ordered" value={totals ? String(totals.ordered) : "—"} hint={totals ? formatPrice(totals.order_value) : undefined} />
        <Stat label="Needs a call back" value={totals ? String(totals.callback) : "—"} hint="on the Support tab" />
        <Stat label="No order" value={totals ? String(totals.no_order) : "—"} />
        <Stat
          label="Average call"
          value={totals ? length(totals.average_seconds) : "—"}
          hint={totals ? `${totals.total_minutes} min in all` : undefined}
        />
      </div>

      <div className="flex flex-wrap gap-2">
        {FILTERS.map((f) => (
          <Button
            key={f.key}
            size="sm"
            variant={outcome === f.key ? "default" : "outline"}
            onClick={() => {
              setOutcome(f.key);
              setPicked(null);
              setPage(1);
            }}
          >
            {f.label}
          </Button>
        ))}
      </div>

      <div className="grid gap-4 lg:grid-cols-[380px_minmax(0,1fr)]">
        <ul className="flex max-h-[70vh] flex-col overflow-y-auto rounded-xl border bg-card">
          {data === null && <Skeleton className="m-3 h-20" />}
          {data?.calls.length === 0 && (
            <li className="p-4 text-sm text-muted-foreground">
              {outcome === "all" ? "No calls on this day." : "No calls of this kind on this day."}
            </li>
          )}
          {data?.calls.map((c) => (
            <li key={c.id} className="border-b last:border-b-0">
              <CallRow call={c} active={c.id === selected} onPick={() => setPicked(c.id)} />
            </li>
          ))}
          {data && (data.has_more || data.page > 1) && (
            <li className="p-3">
              <Pager
                page={data.page}
                hasMore={data.has_more}
                onPage={(next) => {
                  setPage(next);
                  setPicked(null);
                }}
              />
            </li>
          )}
        </ul>
        <CallPanel restaurantId={restaurantId} callId={selected} />
      </div>
    </div>
  );
}

function CallRow({ call, active, onPick }: { call: CallLogRow; active: boolean; onPick: () => void }) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onPick}
      className={cn("flex w-full flex-col gap-1 px-4 py-3 text-left hover:bg-muted", active && "bg-muted")}
    >
      <span className="flex items-center justify-between gap-2 text-xs text-muted-foreground">
        <span>
          {clock(call.started_at)} · {length(call.seconds)}
        </span>
        <span className={cn("rounded-full px-2 py-0.5 text-[11px] font-medium", OUTCOME_STYLE[call.outcome])}>{call.outcome_label}</span>
      </span>
      <span className="text-sm font-medium">
        {callerName(call.caller)}
        <span className="font-normal text-muted-foreground"> · {call.caller.phone ?? "no number"}</span>
      </span>
      {call.preview && <span className="line-clamp-2 text-sm text-muted-foreground">&ldquo;{call.preview}&rdquo;</span>}
      {(call.order || call.ticket) && (
        <span className="flex flex-wrap gap-1">
          {call.order && (
            <Badge variant="secondary">
              {call.order.ref} · {call.order.total != null ? formatPrice(call.order.total) : ""}
            </Badge>
          )}
          {call.ticket && (
            <Badge variant={call.ticket.urgent ? "destructive" : "outline"}>
              {call.ticket.category}
              {call.ticket.status === "resolved" ? " · resolved" : ""}
            </Badge>
          )}
        </span>
      )}
    </button>
  );
}

function CallPanel({ restaurantId, callId }: { restaurantId: string; callId: string | null }) {
  const [call, setCall] = useState<CallDetail | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  const [phone, setPhone] = useState<string | null>(null);

  useEffect(() => {
    if (!callId) return;
    let cancelled = false;
    fetchCallDetail(restaurantId, callId)
      .then((d) => {
        if (cancelled) return;
        setCall(d);
        setFailed(null);
        setPhone(null);
      })
      .catch((err: Error) => !cancelled && setFailed(err.message));
    return () => {
      cancelled = true;
    };
  }, [restaurantId, callId]);

  async function reveal(dial: boolean) {
    if (!call) return;
    try {
      const full = phone ?? (await fetchCallPhone(restaurantId, call.id));
      setPhone(full);
      if (dial) window.location.href = `tel:${full}`;
    } catch (err) {
      setFailed((err as Error).message);
    }
  }

  if (!callId) return <div className="rounded-xl border p-6 text-sm text-muted-foreground">Pick a call to read it.</div>;
  if (failed && !call) return <p className="rounded-xl border p-6 text-sm text-destructive">{failed}</p>;
  if (!call || call.id !== callId) return <Skeleton className="h-64" />;

  const hasNumber = call.caller.source !== "none";
  return (
    <section aria-label="Call" className="flex max-h-[70vh] flex-col gap-4 overflow-y-auto rounded-xl border bg-card p-4">
      <header className="flex flex-col gap-1">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="text-base font-semibold">{callerName(call.caller)}</h3>
          <span className={cn("rounded-full px-2 py-0.5 text-xs font-medium", OUTCOME_STYLE[call.outcome])}>{call.outcome_label}</span>
          <Badge variant="outline">
            {call.caller.source === "caller_id" ? "Caller ID" : call.caller.source === "given" ? "Number given" : "Test call"}
          </Badge>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="font-mono">{phone ?? callerNumber(call.caller)}</span>
          {hasNumber && !phone && (
            <Button size="sm" variant="outline" className="h-7" onClick={() => reveal(false)}>
              Show number
            </Button>
          )}
          {hasNumber && (
            <Button size="sm" className="h-7" onClick={() => reveal(true)}>
              Call
            </Button>
          )}
        </div>
        <p className="text-xs text-muted-foreground">
          {new Date(call.started_at).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit", timeZone: IST })}
          {" · "}
          {length(call.seconds)}
          {call.turns ? ` · the guest spoke ${call.turns} time${call.turns > 1 ? "s" : ""}` : ""}
        </p>
        {failed && <p className="text-sm text-destructive">{failed}</p>}
      </header>

      {call.order && (
        <div className="rounded-lg border p-3 text-sm">
          <p className="mb-1 font-semibold">
            Order {call.order.ref}
            <span className="font-normal text-muted-foreground">
              {call.order.fulfilment ? ` · ${call.order.fulfilment}` : ""}
              {call.order.status ? ` · ${call.order.status.replace(/_/g, " ")}` : ""}
            </span>
          </p>
          <ul>
            {call.order.items.map((line, i) => (
              <li key={`${line.id}-${i}`}>
                {line.quantity}× {line.name}
                {line.variant ? ` (${line.variant})` : ""}
              </li>
            ))}
          </ul>
          {call.order.address && <p className="mt-1 text-xs text-muted-foreground">{call.order.address}</p>}
          {call.order.total != null && <p className="mt-1 font-medium">{formatPrice(call.order.total)}</p>}
        </div>
      )}

      {call.ticket && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm dark:border-amber-900 dark:bg-amber-950">
          <p className="font-semibold">
            Support ticket · {call.ticket.category}
            {call.ticket.urgent ? " · urgent" : ""} · {call.ticket.status.replace(/_/g, " ")}
          </p>
          {call.ticket.reason && <p className="text-muted-foreground">{call.ticket.reason}</p>}
        </div>
      )}

      <div className="flex flex-col gap-2">
        <h4 className="text-sm font-semibold">What was said</h4>
        <CallTranscript lines={call.transcript} empty="No transcript for this call: Sarvam sends it when the call ends." />
      </div>
    </section>
  );
}
