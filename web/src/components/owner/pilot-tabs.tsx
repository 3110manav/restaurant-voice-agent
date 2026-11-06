"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  closeTable,
  fetchMonthlyReport,
  fetchTonight,
  listCustomers,
  markTablePaid,
  markTableServed,
  fetchCustomerVisits,
  type Customer,
  type CustomerVisit,
  type MonthlyReport,
  type OwnerRestaurant,
  type StageAverages,
  type TableStatus,
  type Tonight,
  type TonightTable,
} from "@/lib/owner-api";
import { cn, formatPrice, formatTime } from "@/lib/utils";

const POLL_MS = 8000;
const MIGRATION_HINT = "If this keeps happening, check that supabase/migrations/003_table_pilot.sql has been run.";

/** Loads now and every `everyMs` (0: only on refresh). Keeps showing the last good data on errors. */
function usePolled<T>(load: () => Promise<T>, everyMs = POLL_MS) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    let cancelled = false;
    const pull = () =>
      load()
        .then((next) => {
          if (cancelled) return;
          setData(next);
          setError(null);
        })
        .catch((err: Error) => !cancelled && setError(err.message));
    void pull();
    const id = everyMs ? setInterval(pull, everyMs) : undefined;
    return () => {
      cancelled = true;
      if (id) clearInterval(id);
    };
  }, [everyMs, load, tick]);
  const refresh = useCallback(() => setTick((t) => t + 1), []);
  return { data, error, refresh };
}

function LoadError({ error }: { error: string | null }) {
  if (!error) return null;
  return (
    <p className="text-sm text-destructive">
      {error} <span className="text-muted-foreground">{MIGRATION_HINT}</span>
    </p>
  );
}

// ------------------------------------------------------------------- tonight --

const STATUS: Record<TableStatus, { label: string; tone: "plain" | "warn" | "quiet" }> = {
  ordering: { label: "Ordering", tone: "plain" },
  food: { label: "Waiting for food", tone: "plain" },
  long: { label: "Long wait for food", tone: "warn" },
  eating: { label: "Eating", tone: "plain" },
  bill: { label: "Asked for the bill", tone: "plain" },
  paid: { label: "Paid", tone: "quiet" },
};

const STAGES: { key: keyof StageAverages; label: string; className: string }[] = [
  { key: "seated_to_ordered", label: "Seated to ordered", className: "bg-foreground/80" },
  { key: "ordered_to_food", label: "Ordered to food", className: "bg-primary" },
  { key: "food_to_bill", label: "Food to asking for the bill", className: "bg-muted-foreground/30" },
  { key: "bill_to_paid", label: "Bill to paid", className: "bg-foreground/80" },
];

export function TonightTab({ restaurant }: { restaurant: OwnerRestaurant }) {
  const load = useCallback(() => fetchTonight(restaurant.id), [restaurant.id]);
  const { data, error, refresh } = usePolled<Tonight>(load);
  const [acting, setActing] = useState<string | null>(null);

  async function act(table: TonightTable, action: (rid: string, id: string) => Promise<unknown>) {
    setActing(table.id);
    try {
      await action(restaurant.id, table.id);
      refresh();
    } finally {
      setActing(null);
    }
  }

  const waiting = (data?.tables ?? []).filter((t) => t.state === "long");

  return (
    <div className="flex flex-col gap-5">
      <LoadError error={error} />
      {waiting.length > 0 && (
        <div role="alert" className="rounded-lg border border-amber-500 bg-amber-50 px-4 py-3 text-sm text-amber-900 dark:bg-amber-950/30 dark:text-amber-200">
          <strong className="font-semibold">
            {waiting.map((t) => `Table ${t.table_no ?? "?"}`).join(", ")} {waiting.length === 1 ? "has" : "have"} waited a long time for food.
          </strong>{" "}
          Check with the kitchen, then tap Food served.
        </div>
      )}
      <section className="flex flex-col gap-3">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="text-xl font-semibold">Tables right now</h2>
          <p className="text-sm text-muted-foreground">
            {data ? `${data.tables.length} open ${data.tables.length === 1 ? "table" : "tables"}` : "Loading…"}
          </p>
        </div>
        {data && data.tables.length === 0 && (
          <p className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground">
            No open tables. A table appears here when a guest scans its QR code.
          </p>
        )}
        <div className="grid grid-cols-[repeat(auto-fill,minmax(176px,1fr))] gap-3">
          {data?.tables.map((t) => {
            const status = STATUS[t.state];
            const waitingForFood = t.state === "food" || t.state === "long";
            return (
              <div
                key={t.id}
                className={cn(
                  "flex flex-col gap-1 rounded-xl border bg-background p-3.5",
                  status.tone === "warn" && "border-amber-500 bg-amber-50 dark:bg-amber-950/30"
                )}
              >
                <div className="flex items-baseline justify-between">
                  <span className="font-semibold">Table {t.table_no ?? "?"}</span>
                  {t.minutes !== null && <span className="font-mono text-xs text-muted-foreground">{t.minutes} min</span>}
                </div>
                <span className={cn("text-sm", status.tone === "warn" && "font-semibold text-amber-800 dark:text-amber-300")}>
                  {status.label}
                </span>
                <span className="text-xs text-muted-foreground">
                  {t.amount > 0 ? formatPrice(t.amount) : "Nothing ordered yet"}
                  {t.payment_method && ` · paying ${t.payment_method === "upi" ? "by UPI" : "at the counter"}`}
                </span>
                <div className="mt-2 flex flex-col gap-1.5">
                  {waitingForFood && (
                    <Button size="sm" variant="outline" className="h-9" disabled={acting === t.id} onClick={() => act(t, markTableServed)}>
                      Food served
                    </Button>
                  )}
                  {t.rounds > 0 && (
                    <Button size="sm" className="h-9" disabled={acting === t.id} onClick={() => act(t, markTablePaid)}>
                      Payment received
                    </Button>
                  )}
                  <Button size="sm" variant="ghost" className="h-9" disabled={acting === t.id} onClick={() => act(t, closeTable)}>
                    Clear table
                  </Button>
                </div>
              </div>
            );
          })}
        </div>
      </section>
      {data && <StageBreakdown averages={data.averages} baseline={restaurant.baseline_turn_minutes ?? null} title="Where tables wait tonight" />}
    </div>
  );
}

function StageBreakdown({ averages, baseline, title }: { averages: StageAverages; baseline: number | null; title: string }) {
  const known = STAGES.map((s) => averages[s.key] ?? 0);
  const sum = known.reduce((a, b) => a + b, 0);
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <CardDescription>
          {averages.turn !== null
            ? `Average table turn ${averages.turn} min${baseline ? `, ${baseline} min before Sarthi` : ""}.`
            : "Shows once tables have paid. Each wait is measured from the guest's and staff's taps."}
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {sum > 0 && (
          <div className="flex h-8 overflow-hidden rounded-md" aria-hidden="true">
            {STAGES.map((s, i) => (
              <div key={s.key} className={s.className} style={{ width: `${(known[i] / sum) * 100}%` }} />
            ))}
          </div>
        )}
        <div className="grid grid-cols-[repeat(auto-fit,minmax(150px,1fr))] gap-3">
          {STAGES.map((s) => (
            <div key={s.key}>
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <span aria-hidden="true" className={cn("size-2.5 rounded-sm", s.className)} />
                {s.label}
              </div>
              <div className="text-lg font-semibold tabular-nums">
                {averages[s.key] !== null ? `${averages[s.key]} min` : "—"}
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

// ----------------------------------------------------------------- customers --

function toCsv(rows: Customer[]): string {
  const cell = (value: string | number | boolean | null) => `"${String(value ?? "").replace(/"/g, '""')}"`;
  const header = ["Name", "Phone", "Visits", "First visit", "Last visit", "Offers on"];
  const lines = rows.map((c) =>
    [c.name, c.phone, c.visits, c.first_seen_at, c.last_visit_at, c.offers_opt_in ? "yes" : "no"].map(cell).join(",")
  );
  return [header.map(cell).join(","), ...lines].join("\n");
}

export function CustomersTab({ restaurant }: { restaurant: OwnerRestaurant }) {
  const load = useCallback(() => listCustomers(restaurant.id), [restaurant.id]);
  const { data, error } = usePolled<Customer[]>(load, 0);
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState<Customer | null>(null);
  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (data ?? []).filter((c) => !q || c.phone.includes(q) || (c.name ?? "").toLowerCase().includes(q));
  }, [data, query]);

  function exportCsv() {
    const blob = new Blob(["﻿" + toCsv(data ?? [])], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${restaurant.slug}-customers.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  const optedIn = (data ?? []).filter((c) => c.offers_opt_in).length;

  return (
    <div className="flex flex-col gap-3">
      <LoadError error={error} />
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">Your customers</h2>
          <p className="text-sm text-muted-foreground">
            Guests who shared their number at the bill. This list belongs to your restaurant
            {data ? `: ${data.length} customers, ${optedIn} with offers on.` : "."}
          </p>
        </div>
        <div className="flex gap-2">
          <Input
            aria-label="Search customers"
            placeholder="Search name or number"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="h-9 w-52"
          />
          <Button variant="outline" className="h-9" disabled={!data?.length} onClick={exportCsv}>
            Export CSV
          </Button>
        </div>
      </div>
      <div className="overflow-x-auto rounded-lg border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Customer</TableHead>
              <TableHead className="text-right">Visits</TableHead>
              <TableHead>Last visit</TableHead>
              <TableHead>Offers</TableHead>
              <TableHead>
                <span className="sr-only">Past visits</span>
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {shown.length === 0 ? (
              <TableRow>
                <TableCell colSpan={5} className="text-center text-muted-foreground">
                  {data ? "No customers yet." : "Loading…"}
                </TableCell>
              </TableRow>
            ) : (
              shown.map((c) => (
                <TableRow key={c.id}>
                  <TableCell>
                    <div className="font-medium">{c.name ?? "Name not given"}</div>
                    <div className="font-mono text-xs text-muted-foreground">{c.phone}</div>
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{c.visits}</TableCell>
                  <TableCell className="text-xs text-muted-foreground">{formatTime(c.last_visit_at)}</TableCell>
                  <TableCell className={c.offers_opt_in ? "text-green-700 dark:text-green-400" : "text-muted-foreground"}>
                    {c.offers_opt_in ? "On" : "Off"}
                  </TableCell>
                  <TableCell className="text-right">
                    <Button size="sm" variant="outline" className="h-9" onClick={() => setOpen(c)}>
                      Past visits
                    </Button>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>
      {open && <CustomerVisits key={open.id} restaurantId={restaurant.id} customer={open} onClose={() => setOpen(null)} />}
    </div>
  );
}

function CustomerVisits({ restaurantId, customer, onClose }: { restaurantId: string; customer: Customer; onClose: () => void }) {
  const load = useCallback(() => fetchCustomerVisits(restaurantId, customer.id), [customer.id, restaurantId]);
  const { data, error } = usePolled<CustomerVisit[]>(load, 0);
  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-3">
        <div>
          <CardTitle>{customer.name ?? customer.phone}: past visits</CardTitle>
          <CardDescription>
            {customer.visits} {customer.visits === 1 ? "visit" : "visits"}, first on {formatTime(customer.first_seen_at)}
          </CardDescription>
        </div>
        <Button size="sm" variant="ghost" className="h-9" onClick={onClose}>
          Close
        </Button>
      </CardHeader>
      <CardContent className="flex flex-col">
        {error && <p className="text-sm text-destructive">{error}</p>}
        {!data ? (
          <p className="text-sm text-muted-foreground">Loading…</p>
        ) : data.length === 0 ? (
          <p className="text-sm text-muted-foreground">No table visits recorded with this number.</p>
        ) : (
          data.map((v) => (
            <div key={v.seated_at} className="flex flex-wrap justify-between gap-2 border-t py-2.5 text-sm">
              <span>
                <span className="text-muted-foreground">
                  {formatTime(v.seated_at)}
                  {v.table_no ? ` · Table ${v.table_no}` : ""} ·{" "}
                </span>
                {v.ordered.map((l) => `${l.quantity} × ${l.name}${l.variant ? ` (${l.variant})` : ""}`).join(", ") || "Nothing ordered"}
              </span>
              <span className="font-medium">
                {v.bill_total ? formatPrice(v.bill_total) : "—"}
                {v.rating ? ` · ${v.rating}★` : ""}
              </span>
            </div>
          ))
        )}
      </CardContent>
    </Card>
  );
}

// -------------------------------------------------------------------- report --

function currentMonth(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}

export function ReportTab({ restaurant }: { restaurant: OwnerRestaurant }) {
  const [month, setMonth] = useState(currentMonth);
  const load = useCallback(() => fetchMonthlyReport(restaurant.id, month), [month, restaurant.id]);
  const { data, error } = usePolled<MonthlyReport>(load, 0);

  const cards = data
    ? [
        {
          label: "Average table turn",
          value: data.averages.turn !== null ? `${data.averages.turn} min` : "—",
          note: data.baseline_turn_minutes
            ? `${data.baseline_turn_minutes} min before Sarthi${data.turn_saved_minutes !== null ? `, ${data.turn_saved_minutes} min saved` : ""}`
            : "Add your time before Sarthi in Settings to compare",
        },
        { label: "Tables served", value: String(data.tables_served), note: `${data.table_orders} kitchen tickets` },
        { label: "New customers saved", value: String(data.new_customers), note: `${data.new_customers_opted_in} turned offers on` },
        {
          label: "Guest ratings",
          value: data.average_rating !== null ? `${data.average_rating} / 5` : "—",
          note: `${data.ratings} ratings, ${data.complaints} private complaints`,
        },
      ]
    : [];

  return (
    <div className="flex flex-col gap-4">
      <LoadError error={error} />
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">Monthly report</h2>
          <p className="text-sm text-muted-foreground">What Sarthi did for {restaurant.name}, from your tables&apos; own data.</p>
        </div>
        <label className="flex items-center gap-2 text-sm">
          Month
          <Input type="month" value={month} onChange={(e) => e.target.value && setMonth(e.target.value)} className="h-9 w-40" />
        </label>
      </div>
      {!data ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : (
        <>
          <div className="rounded-xl bg-foreground p-6 text-background">
            <p className="text-sm opacity-80">Extra earned from suggestions</p>
            <p className="text-5xl leading-tight font-bold tabular-nums">{formatPrice(data.upsell_total)}</p>
            <p className="text-sm opacity-80">
              Dishes guests added from {restaurant.agent_name}&apos;s suggestion card, across {data.table_orders} kitchen tickets.
            </p>
          </div>
          <div className="grid grid-cols-[repeat(auto-fit,minmax(200px,1fr))] gap-3">
            {cards.map((c) => (
              <Card key={c.label}>
                <CardContent className="flex flex-col gap-1">
                  <span className="text-sm text-muted-foreground">{c.label}</span>
                  <span className="text-2xl font-semibold tabular-nums">{c.value}</span>
                  <span className="text-xs text-muted-foreground">{c.note}</span>
                </CardContent>
              </Card>
            ))}
          </div>
          <StageBreakdown averages={data.averages} baseline={data.baseline_turn_minutes} title="Where tables waited this month" />
        </>
      )}
    </div>
  );
}
