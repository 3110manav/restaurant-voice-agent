"use client";

import { type FormEvent, useCallback, useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

const POLL_INTERVAL_MS = 5000;

type Turn = { caller: string; agent: string; language: string; agent_ms: number };
type Timing = { role: string; [stage: string]: string | number };
type Message = {
  id: string;
  kind: string;
  recipient: string;
  status: string;
  attempts: number;
  delivery_status: string | null;
  last_error: string | null;
  body: { text?: string; caption?: string };
};
type Order = {
  payment_ref: string;
  total: number;
  status: string;
  payment_status: string;
  order_type: string;
  address: string | null;
  customer_phone: string | null;
  items: { name: string; variant?: string; quantity: number; price: number }[];
};
type Call = {
  id: string;
  store_name: string;
  caller: string | null;
  outcome: string;
  started_at: string;
  ended_at: string | null;
  turns: Turn[];
  metrics: Timing[];
  order: Order | null;
  messages: Message[];
};

function median(values: number[]): number | null {
  if (!values.length) return null;
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[Math.floor(sorted.length / 2)];
}

function CallCard({ call }: { call: Call }) {
  const replyTimes = call.turns.map((turn) => turn.agent_ms);
  const typical = median(replyTimes);
  const slowest = replyTimes.length ? Math.max(...replyTimes) : null;
  const heard = median(
    call.metrics
      .map((metric) => metric.transcription_delay)
      .filter((value): value is number => typeof value === "number")
  );
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center gap-2 text-base">
          {call.store_name}
          <Badge variant={call.outcome === "ordered" ? "default" : "secondary"}>
            {call.outcome.replace("_", " ")}
          </Badge>
          <span className="text-sm font-normal text-muted-foreground">
            {call.caller ?? "unknown caller"} · {new Date(call.started_at).toLocaleString()}
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        <section>
          <h3 className="mb-1 font-medium">Response times</h3>
          <p className="text-muted-foreground">
            Agent: typically {typical ?? "–"} ms, slowest {slowest ?? "–"} ms. Speech-to-text:{" "}
            {heard ?? "–"} ms.
          </p>
        </section>

        <section>
          <h3 className="mb-1 font-medium">Transcript</h3>
          {call.turns.length === 0 && <p className="text-muted-foreground">Nothing said yet.</p>}
          <ul className="space-y-2">
            {call.turns.map((turn, index) => (
              <li key={index}>
                <div>
                  <span className="font-medium">Caller:</span> {turn.caller}
                </div>
                <div>
                  <span className="font-medium">Agent:</span> {turn.agent}{" "}
                  <span className="text-muted-foreground">({turn.agent_ms} ms)</span>
                </div>
              </li>
            ))}
          </ul>
        </section>

        {call.order && (
          <section>
            <h3 className="mb-1 font-medium">
              Order {call.order.payment_ref}: ₹{call.order.total} · {call.order.status.replace(/_/g, " ")} ·{" "}
              {call.order.payment_status}
            </h3>
            <ul>
              {call.order.items.map((item, index) => (
                <li key={index}>
                  {item.quantity} x {item.name}
                  {item.variant ? ` (${item.variant})` : ""} at ₹{item.price}
                </li>
              ))}
            </ul>
            <p className="text-muted-foreground">
              {call.order.order_type === "pickup" ? "Pickup" : `Deliver to: ${call.order.address}`}
            </p>
          </section>
        )}

        {call.messages.length > 0 && (
          <section>
            <h3 className="mb-1 font-medium">WhatsApp messages</h3>
            <ul className="space-y-2">
              {call.messages.map((message) => (
                <li key={message.id}>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium">{message.kind.replace(/_/g, " ")}</span>
                    <Badge variant={message.status === "failed" ? "destructive" : "secondary"}>
                      {message.delivery_status ?? message.status}
                    </Badge>
                    <span className="text-muted-foreground">
                      to {message.recipient}, {message.attempts} attempt(s)
                    </span>
                  </div>
                  {message.last_error && <p className="text-destructive">{message.last_error}</p>}
                  <p className="whitespace-pre-wrap text-muted-foreground">
                    {message.body.text ?? message.body.caption}
                  </p>
                </li>
              ))}
            </ul>
          </section>
        )}
      </CardContent>
    </Card>
  );
}

export default function AdminCallsPage() {
  const [key, setKey] = useState("");
  const [draft, setDraft] = useState("");
  const [calls, setCalls] = useState<Call[]>([]);
  const [whatsappReady, setWhatsappReady] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (adminKey: string) => {
    try {
      const res = await fetch("/api/admin/calls", {
        cache: "no-store",
        headers: { "X-Admin-Key": adminKey },
      });
      const data = await res.json();
      if (!res.ok) {
        setError(data.detail ?? data.error ?? "Couldn't load calls");
        return;
      }
      setError(null);
      setCalls(data.calls);
      setWhatsappReady(data.whatsapp_configured);
    } catch {
      setError("Couldn't reach the server");
    }
  }, []);

  useEffect(() => {
    if (!key) return;
    const interval = setInterval(() => load(key), POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [key, load]);

  function submit(event: FormEvent) {
    event.preventDefault();
    setKey(draft);
    load(draft);
  }

  return (
    <div className="mx-auto w-full max-w-3xl space-y-4 p-4">
      <h1 className="text-lg font-semibold">Phone calls</h1>
      {/* The key stays in memory only: this page shows customers' numbers and addresses. */}
      <form onSubmit={submit} className="flex gap-2">
        <Input
          type="password"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="Admin key"
          aria-label="Admin key"
          autoComplete="off"
        />
        <Button type="submit">Show calls</Button>
      </form>
      {error && <p className="text-sm text-destructive">{error}</p>}
      {key && !error && !whatsappReady && (
        <p className="text-sm text-muted-foreground">
          WhatsApp isn&apos;t configured yet, so messages wait in the queue and go out once it is.
        </p>
      )}
      {key && !error && calls.length === 0 && <p className="text-sm text-muted-foreground">No calls yet.</p>}
      {calls.map((call) => (
        <CallCard key={call.id} call={call} />
      ))}
    </div>
  );
}
