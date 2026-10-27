"use client";

import { useCallback, useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { AdminOrder, AdminRequest } from "@/lib/api";
import { listOwnerOrders, listOwnerRequests, resolveOwnerRequest } from "@/lib/owner-api";
import { formatPrice, formatRequestType, formatTime } from "@/lib/utils";

const POLL_MS = 8000;

/** Re-runs `load` every few seconds (staff leave this tab open on a counter screen). */
function usePolling<T>(load: () => Promise<T>) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const refresh = useCallback(async () => {
    try {
      setData(await load());
      setError(null);
    } catch (err) {
      setError((err as Error).message); // keep showing the last good data
    }
  }, [load]);
  useEffect(() => {
    void refresh();
    const id = setInterval(refresh, POLL_MS);
    return () => clearInterval(id);
  }, [refresh]);
  return { data, error, refresh };
}

export function OrdersTab({ restaurantId }: { restaurantId: string }) {
  const load = useCallback(() => listOwnerOrders(restaurantId), [restaurantId]);
  const { data: orders, error } = usePolling<AdminOrder[]>(load);

  return (
    <div className="flex flex-col gap-2">
      {error && <p className="text-sm text-destructive">{error}</p>}
      <div className="rounded-lg border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Time</TableHead>
              <TableHead>Table</TableHead>
              <TableHead>Items</TableHead>
              <TableHead className="text-right">Total</TableHead>
              <TableHead>Status</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {!orders || orders.length === 0 ? (
              <TableRow>
                <TableCell colSpan={5} className="text-center text-muted-foreground">
                  {orders ? "No orders yet — they appear here the moment a guest checks out." : "Loading…"}
                </TableCell>
              </TableRow>
            ) : (
              orders.map((o) => (
                <TableRow key={o.id}>
                  <TableCell className="text-xs text-muted-foreground">{formatTime(o.created_at)}</TableCell>
                  <TableCell>{o.table_no ?? "—"}</TableCell>
                  <TableCell className="text-muted-foreground">
                    {o.items.map((i) => `${i.quantity}x ${i.name}${i.variant ? ` (${i.variant})` : ""}`).join(", ")}
                  </TableCell>
                  <TableCell className="text-right font-medium">{formatPrice(o.total)}</TableCell>
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
    </div>
  );
}

export function RequestsTab({ restaurantId }: { restaurantId: string }) {
  const load = useCallback(() => listOwnerRequests(restaurantId), [restaurantId]);
  const { data: requests, error, refresh } = usePolling<AdminRequest[]>(load);
  const [resolving, setResolving] = useState<string | null>(null);

  async function resolve(id: string) {
    setResolving(id);
    try {
      await resolveOwnerRequest(restaurantId, id);
      await refresh();
    } finally {
      setResolving(null);
    }
  }

  const open = (requests ?? []).filter((r) => r.status === "open");
  const done = (requests ?? []).filter((r) => r.status !== "open");

  return (
    <div className="flex flex-col gap-4">
      {error && <p className="text-sm text-destructive">{error}</p>}
      <div className="rounded-lg border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Time</TableHead>
              <TableHead>Table</TableHead>
              <TableHead>Request</TableHead>
              <TableHead>Details</TableHead>
              <TableHead className="text-right">Action</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {open.length === 0 ? (
              <TableRow>
                <TableCell colSpan={5} className="text-center text-muted-foreground">
                  {requests ? "No open requests." : "Loading…"}
                </TableCell>
              </TableRow>
            ) : (
              open.map((r) => (
                <TableRow key={r.id}>
                  <TableCell className="text-xs text-muted-foreground">{formatTime(r.created_at)}</TableCell>
                  <TableCell>{r.table_no ?? "—"}</TableCell>
                  <TableCell>{formatRequestType(r.type)}</TableCell>
                  <TableCell className="text-muted-foreground">
                    {[r.details, r.notes].filter(Boolean).join(" — ") || "—"}
                  </TableCell>
                  <TableCell className="text-right">
                    <Button size="sm" variant="outline" disabled={resolving === r.id} onClick={() => resolve(r.id)}>
                      Mark resolved
                    </Button>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>
      {done.length > 0 && (
        <p className="text-xs text-muted-foreground">{done.length} resolved request(s) not shown.</p>
      )}
    </div>
  );
}
