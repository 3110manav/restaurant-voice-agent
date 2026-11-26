"use client";

import { useCallback, useState } from "react";

import { usePolling } from "@/components/owner/activity-tabs";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { CartLine } from "@/lib/api";
import {
  fetchCallbackPhone,
  fetchCallsBoard,
  resolveOwnerRequest,
  type BoardCustomer,
  type BoardOrder,
  type CallbackTicket,
  type CallsBoard,
  type FunnelDay,
} from "@/lib/owner-api";
import { formatPrice, formatRequestType, formatTime } from "@/lib/utils";

/** The table-QR pilot is parked: its orders only show when this is switched on for the build. */
const SHOW_TABLE_ORDERS = process.env.NEXT_PUBLIC_TABLE_PILOT === "1";

function todayInIndia(): string {
  return new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Kolkata" });
}

function Customer({ customer }: { customer: BoardCustomer }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="font-medium">{customer.name ?? "Name not given"}</span>
      <span className="text-xs text-muted-foreground">{customer.phone ?? "No number"}</span>
      <span className="flex flex-wrap gap-1">
        {customer.orders > 1 && <Badge variant="secondary">Returning · {customer.orders} orders</Badge>}
        {customer.phone && (
          <Badge variant="outline" className="text-[10px]">
            {customer.verified ? "Caller ID" : "Number given"}
          </Badge>
        )}
      </span>
    </div>
  );
}

/** One dish per line, and what the guest asked for on it right underneath, where the kitchen reads. */
function Dishes({ items }: { items: CartLine[] }) {
  return (
    <ul className="flex flex-col gap-1">
      {items.map((line, i) => (
        <li key={`${line.id}-${i}`}>
          {line.quantity}× {line.name}
          {line.variant ? ` (${line.variant})` : ""}
          {line.note && <span className="block text-xs font-medium text-amber-700 dark:text-amber-400">↳ {line.note}</span>}
        </li>
      ))}
    </ul>
  );
}

function Requests({ order }: { order: BoardOrder }) {
  const lines = [order.special_requests, ...order.requests.map((r) => `${formatRequestType(r.type)}: ${r.details}`)].filter(
    (text): text is string => Boolean(text)
  );
  if (lines.length === 0) return <span className="text-muted-foreground">—</span>;
  return (
    <ul className="flex flex-col gap-1 text-sm">
      {lines.map((text, i) => (
        <li key={i} className="font-medium text-amber-700 dark:text-amber-400">
          {text}
        </li>
      ))}
    </ul>
  );
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

function sum(days: FunnelDay[], key: "calls" | "ordered" | "dropped_carts" | "dropped_value"): number {
  return days.reduce((total, d) => total + Number(d[key] ?? 0), 0);
}

function Summary({ funnel }: { funnel: FunnelDay[] }) {
  const today = funnel.filter((d) => d.day === todayInIndia());
  const calls = sum(funnel, "calls");
  const conversion = calls ? Math.round((sum(funnel, "ordered") / calls) * 100) : 0;
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
      <Stat label="Calls today" value={String(sum(today, "calls"))} hint={`${sum(funnel, "calls")} in the last 30 days`} />
      <Stat label="Orders today" value={String(sum(today, "ordered"))} hint={`${sum(funnel, "ordered")} in the last 30 days`} />
      <Stat label="Calls that became orders" value={`${conversion}%`} hint="last 30 days" />
      <Stat
        label="Left without ordering"
        value={String(sum(funnel, "dropped_carts"))}
        hint={`${formatPrice(sum(funnel, "dropped_value"))} in their carts, last 30 days`}
      />
    </div>
  );
}

const CALL_OUTCOME: Record<string, string> = {
  ordered: "Ordered",
  callback: "Asked for a call back",
  abandoned: "Hung up",
  in_progress: "On the call",
};

export function CallsBoardTab({ restaurantId }: { restaurantId: string }) {
  const load = useCallback(() => fetchCallsBoard(restaurantId), [restaurantId]);
  const { data, error } = usePolling<CallsBoard>(load);
  return <CallsBoardView data={data} error={error} />;
}

export function CallsBoardView({ data, error }: { data: CallsBoard | null; error: string | null }) {
  const orders = (data?.orders ?? []).filter((o) => SHOW_TABLE_ORDERS || o.channel !== "table");

  return (
    <div className="flex flex-col gap-4">
      {error && <p className="text-sm text-destructive">{error}</p>}
      {data && <Summary funnel={data.funnel} />}
      <div className="rounded-lg border bg-background">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Time</TableHead>
              <TableHead>Customer</TableHead>
              <TableHead>Order</TableHead>
              <TableHead>Special requests</TableHead>
              <TableHead>Delivery</TableHead>
              <TableHead className="text-right">Total</TableHead>
              <TableHead>Status</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {orders.length === 0 ? (
              <TableRow>
                <TableCell colSpan={7} className="text-center text-muted-foreground">
                  {data ? "No orders yet. They appear here the moment a caller confirms one." : "Loading…"}
                </TableCell>
              </TableRow>
            ) : (
              orders.map((o) => (
                <TableRow key={o.id} className="align-top">
                  <TableCell className="text-xs whitespace-nowrap text-muted-foreground">
                    {formatTime(o.created_at)}
                    {o.payment_ref && <span className="block font-mono">{o.payment_ref}</span>}
                  </TableCell>
                  <TableCell>
                    <Customer customer={o.customer} />
                  </TableCell>
                  <TableCell>
                    <Dishes items={o.items} />
                  </TableCell>
                  <TableCell>
                    <Requests order={o} />
                  </TableCell>
                  <TableCell className="max-w-56 text-sm">
                    <Badge variant="outline" className="capitalize">
                      {o.fulfilment === "dine_in" ? "Dine in" : (o.fulfilment ?? "—")}
                    </Badge>
                    {o.fulfilment === "delivery" && o.address && (
                      <span className="mt-1 block text-xs text-muted-foreground">{o.address}</span>
                    )}
                  </TableCell>
                  <TableCell className="text-right font-medium whitespace-nowrap">{formatPrice(o.total)}</TableCell>
                  <TableCell>
                    <div className="flex flex-col items-start gap-1">
                      <Badge variant="outline" className="capitalize">
                        {o.status.replace(/_/g, " ")}
                      </Badge>
                      {o.payment_status && (
                        <span className="text-xs text-muted-foreground capitalize">{o.payment_status}</span>
                      )}
                      {o.call?.outcome && (
                        <span className="text-xs text-muted-foreground">Call: {CALL_OUTCOME[o.call.outcome] ?? o.call.outcome}</span>
                      )}
                    </div>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}

export function DroppedCartsTab({ restaurantId }: { restaurantId: string }) {
  const load = useCallback(() => fetchCallsBoard(restaurantId), [restaurantId]);
  const { data, error } = usePolling<CallsBoard>(load);
  return <DroppedCartsView data={data} error={error} />;
}

export function DroppedCartsView({ data, error }: { data: CallsBoard | null; error: string | null }) {
  const carts = data?.dropped_carts ?? [];
  const waiting = carts.filter((c) => c.status === "abandoned");

  return (
    <div className="flex flex-col gap-3">
      {error && <p className="text-sm text-destructive">{error}</p>}
      <p className="text-sm text-muted-foreground">
        Callers who put dishes in their cart and hung up.
        {data && ` ${waiting.length} still within the window to win back, worth ${formatPrice(waiting.reduce((t, c) => t + c.total, 0))}.`}
      </p>
      <div className="rounded-lg border bg-background">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Last active</TableHead>
              <TableHead>Customer</TableHead>
              <TableHead>Left in the cart</TableHead>
              <TableHead>Delivery</TableHead>
              <TableHead className="text-right">Value</TableHead>
              <TableHead>Status</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {carts.length === 0 ? (
              <TableRow>
                <TableCell colSpan={6} className="text-center text-muted-foreground">
                  {data ? "No dropped carts." : "Loading…"}
                </TableCell>
              </TableRow>
            ) : (
              carts.map((c) => (
                <TableRow key={c.id} className="align-top">
                  <TableCell className="text-xs whitespace-nowrap text-muted-foreground">{formatTime(c.last_activity_at)}</TableCell>
                  <TableCell>
                    <Customer customer={c.customer} />
                  </TableCell>
                  <TableCell>
                    <Dishes items={c.items} />
                    {c.special_requests && (
                      <span className="mt-1 block text-xs font-medium text-amber-700 dark:text-amber-400">{c.special_requests}</span>
                    )}
                  </TableCell>
                  <TableCell className="max-w-56 text-sm">
                    {c.fulfilment ? (
                      <Badge variant="outline" className="capitalize">
                        {c.fulfilment}
                      </Badge>
                    ) : (
                      <span className="text-muted-foreground">Not chosen yet</span>
                    )}
                    {c.address && <span className="mt-1 block text-xs text-muted-foreground">{c.address}</span>}
                  </TableCell>
                  <TableCell className="text-right font-medium whitespace-nowrap">{formatPrice(c.total)}</TableCell>
                  <TableCell>
                    <Badge variant={c.status === "abandoned" ? "secondary" : "outline"}>
                      {c.status === "abandoned" ? "Can be won back" : "Expired"}
                    </Badge>
                    {c.recovery_attempts > 0 && (
                      <span className="mt-1 block text-xs text-muted-foreground">{c.recovery_attempts} follow-up(s)</span>
                    )}
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}

function waited(since: string): string {
  const minutes = Math.max(0, Math.round((Date.now() - new Date(since).getTime()) / 60000));
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  return hours < 24 ? `${hours} h ${minutes % 60} min` : `${Math.floor(hours / 24)} d`;
}

/** Support tickets: callers waiting for the restaurant to call them back. */
export function CallbacksTab({ restaurantId }: { restaurantId: string }) {
  const load = useCallback(() => fetchCallsBoard(restaurantId), [restaurantId]);
  const { data, error, refresh } = usePolling<CallsBoard>(load);
  const [busy, setBusy] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  async function call(ticket: CallbackTicket) {
    setBusy(ticket.id);
    setActionError(null);
    try {
      const phone = await fetchCallbackPhone(restaurantId, ticket.id);
      window.location.href = `tel:${phone}`;
    } catch (err) {
      setActionError((err as Error).message);
    } finally {
      setBusy(null);
    }
  }

  async function resolve(ticket: CallbackTicket) {
    setBusy(ticket.id);
    setActionError(null);
    try {
      await resolveOwnerRequest(restaurantId, ticket.id);
      await refresh();
    } catch (err) {
      setActionError((err as Error).message);
    } finally {
      setBusy(null);
    }
  }

  return <CallbacksView data={data} error={error ?? actionError} busy={busy} onCall={call} onResolve={resolve} />;
}

export function CallbacksView({
  data,
  error,
  busy,
  onCall,
  onResolve,
}: {
  data: CallsBoard | null;
  error: string | null;
  busy: string | null;
  onCall: (ticket: CallbackTicket) => void;
  onResolve: (ticket: CallbackTicket) => void;
}) {
  const tickets = data?.callbacks ?? [];
  const open = tickets.filter((t) => t.status === "open");

  return (
    <div className="flex flex-col gap-3">
      {error && <p className="text-sm text-destructive">{error}</p>}
      <p className="text-sm text-muted-foreground">
        Callers who asked to speak to someone, or whose order couldn&apos;t be saved. Call them back, then mark it resolved.
        {data && ` ${open.length} waiting.`}
      </p>
      <div className="rounded-lg border bg-background">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Raised</TableHead>
              <TableHead>Customer</TableHead>
              <TableHead>Reason</TableHead>
              <TableHead>Waiting</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="text-right">Action</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {tickets.length === 0 ? (
              <TableRow>
                <TableCell colSpan={6} className="text-center text-muted-foreground">
                  {data ? "No callback requests. They appear here when a caller asks for a person." : "Loading…"}
                </TableCell>
              </TableRow>
            ) : (
              tickets.map((t) => (
                <TableRow key={t.id} className="align-top">
                  <TableCell className="text-xs whitespace-nowrap text-muted-foreground">
                    {formatTime(t.created_at)}
                    {t.order_ref && <span className="block font-mono">{t.order_ref}</span>}
                  </TableCell>
                  <TableCell>
                    <Customer customer={t.customer} />
                  </TableCell>
                  <TableCell className="max-w-72 text-sm font-medium text-amber-700 dark:text-amber-400">{t.reason || "—"}</TableCell>
                  <TableCell className="text-sm whitespace-nowrap">
                    {t.status === "open" ? waited(t.created_at) : <span className="text-muted-foreground">—</span>}
                  </TableCell>
                  <TableCell>
                    <Badge variant={t.status === "open" ? "destructive" : "outline"}>
                      {t.status === "open" ? "Call back" : "Resolved"}
                    </Badge>
                    {t.resolved_at && <span className="mt-1 block text-xs text-muted-foreground">{formatTime(t.resolved_at)}</span>}
                  </TableCell>
                  <TableCell className="text-right">
                    {t.status === "open" && (
                      <div className="flex justify-end gap-2">
                        <Button size="sm" disabled={!t.can_call || busy === t.id} onClick={() => onCall(t)}>
                          Call
                        </Button>
                        <Button size="sm" variant="outline" disabled={busy === t.id} onClick={() => onResolve(t)}>
                          Resolved
                        </Button>
                      </div>
                    )}
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
