"use client";

import { useCallback, useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  fetchAdminOrders,
  fetchAdminRequests,
  resolveAdminRequest,
  type AdminOrder,
  type AdminRequest,
} from "@/lib/api";

const POLL_INTERVAL_MS = 8000;

function formatTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function formatRequestType(type: string): string {
  return type.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export default function AdminPage() {
  const [configured, setConfigured] = useState(true);
  const [orders, setOrders] = useState<AdminOrder[]>([]);
  const [requests, setRequests] = useState<AdminRequest[]>([]);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [resolvingId, setResolvingId] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [ordersRes, requestsRes] = await Promise.all([
        fetchAdminOrders(),
        fetchAdminRequests(),
      ]);
      setConfigured(ordersRes.configured && requestsRes.configured);
      setOrders(ordersRes.orders);
      setRequests(requestsRes.requests);
      setLastUpdated(new Date());
    } catch {
      // Keep showing the last good data rather than clearing the view on a
      // transient fetch failure.
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [refresh]);

  async function handleResolve(id: string) {
    setResolvingId(id);
    try {
      await resolveAdminRequest(id);
      await refresh();
    } finally {
      setResolvingId(null);
    }
  }

  const openRequests = requests.filter((r) => r.status === "open");
  const resolvedRequests = requests.filter((r) => r.status !== "open");

  return (
    <div className="mx-auto flex min-h-screen max-w-5xl flex-col gap-8 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Sarthi — Staff View</h1>
          <p className="text-sm text-muted-foreground">
            Live orders and service requests across all four assistants.
          </p>
        </div>
        <div className="flex items-center gap-3">
          {lastUpdated && (
            <span className="text-xs text-muted-foreground">
              Updated {lastUpdated.toLocaleTimeString()}
            </span>
          )}
          <Button size="sm" variant="outline" onClick={refresh}>
            <RefreshCw className="size-3.5" />
            Refresh
          </Button>
        </div>
      </div>

      {!configured && !isLoading && (
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
          Supabase isn&apos;t configured on the backend, so there&apos;s nothing to show
          here yet. See the README&apos;s &quot;Supabase (optional)&quot; section.
        </div>
      )}

      <section className="flex flex-col gap-3">
        <h2 className="text-sm font-semibold text-muted-foreground">
          Open requests ({openRequests.length})
        </h2>
        <div className="rounded-lg border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Time</TableHead>
                <TableHead>Persona</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>Details</TableHead>
                <TableHead className="text-right">Action</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {openRequests.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={5} className="text-center text-muted-foreground">
                    No open requests.
                  </TableCell>
                </TableRow>
              ) : (
                openRequests.map((r) => (
                  <TableRow key={r.id}>
                    <TableCell className="text-xs text-muted-foreground">
                      {formatTime(r.created_at)}
                    </TableCell>
                    <TableCell className="capitalize">{r.persona.replace("_", " ")}</TableCell>
                    <TableCell>{formatRequestType(r.type)}</TableCell>
                    <TableCell className="text-muted-foreground">
                      {[r.details, r.notes].filter(Boolean).join(" — ") || "—"}
                    </TableCell>
                    <TableCell className="text-right">
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={resolvingId === r.id}
                        onClick={() => handleResolve(r.id)}
                      >
                        Mark resolved
                      </Button>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </div>
      </section>

      <section className="flex flex-col gap-3">
        <h2 className="text-sm font-semibold text-muted-foreground">
          Recent orders ({orders.length})
        </h2>
        <div className="rounded-lg border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Time</TableHead>
                <TableHead>Persona</TableHead>
                <TableHead>Items</TableHead>
                <TableHead className="text-right">Total</TableHead>
                <TableHead>Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {orders.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={5} className="text-center text-muted-foreground">
                    No orders yet.
                  </TableCell>
                </TableRow>
              ) : (
                orders.map((o) => (
                  <TableRow key={o.id}>
                    <TableCell className="text-xs text-muted-foreground">
                      {formatTime(o.created_at)}
                    </TableCell>
                    <TableCell className="capitalize">{o.persona.replace("_", " ")}</TableCell>
                    <TableCell className="text-muted-foreground">
                      {o.items.map((i) => `${i.quantity}x ${i.name}`).join(", ")}
                    </TableCell>
                    <TableCell className="text-right font-medium">
                      ${o.total.toFixed(2)}
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline" className="capitalize">
                        {o.status}
                      </Badge>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </div>
      </section>

      {resolvedRequests.length > 0 && (
        <section className="flex flex-col gap-3">
          <h2 className="text-sm font-semibold text-muted-foreground">
            Resolved requests ({resolvedRequests.length})
          </h2>
          <div className="rounded-lg border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Time</TableHead>
                  <TableHead>Persona</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead>Details</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {resolvedRequests.map((r) => (
                  <TableRow key={r.id} className="opacity-60">
                    <TableCell className="text-xs text-muted-foreground">
                      {formatTime(r.created_at)}
                    </TableCell>
                    <TableCell className="capitalize">{r.persona.replace("_", " ")}</TableCell>
                    <TableCell>{formatRequestType(r.type)}</TableCell>
                    <TableCell className="text-muted-foreground">
                      {[r.details, r.notes].filter(Boolean).join(" — ") || "—"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </section>
      )}
    </div>
  );
}
