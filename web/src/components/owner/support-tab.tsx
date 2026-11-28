"use client";

import { useCallback, useState } from "react";

import { usePolling } from "@/components/owner/activity-tabs";
import { CallTranscript } from "@/components/owner/call-transcript";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import {
  actOnTicket,
  fetchCallbackPhone,
  fetchTicket,
  fetchTickets,
  TICKET_CATEGORIES,
  type CallbackTicket,
  type TicketAction,
  type TicketCategory,
  type TicketDetail,
  type TicketEvent,
  type TicketsPage,
  type TicketStatusFilter,
} from "@/lib/owner-api";
import { formatPrice, formatTime } from "@/lib/utils";

function minutesSince(since: string): number {
  return Math.max(0, Math.round((Date.now() - new Date(since).getTime()) / 60000));
}

function waited(since: string): string {
  const minutes = minutesSince(since);
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  return hours < 24 ? `${hours} h ${minutes % 60} min` : `${Math.floor(hours / 24)} d`;
}

const isWaiting = (t: CallbackTicket) => t.status !== "resolved";

const STATUS_LABEL: Record<CallbackTicket["status"], string> = {
  open: "New",
  in_progress: "In progress",
  resolved: "Resolved",
};

const EVENT_LABEL: Record<TicketEvent["kind"], string> = {
  opened: "Ticket raised",
  started: "Picked up",
  no_answer: "Called, no answer",
  note: "Note",
  resolved: "Resolved",
  reopened: "Reopened",
  priority: "Priority changed",
  category: "Category changed",
};

function StatusBadge({ ticket }: { ticket: CallbackTicket }) {
  if (ticket.status === "resolved") return <Badge variant="outline">Resolved</Badge>;
  return <Badge variant={ticket.status === "open" ? "destructive" : "secondary"}>{STATUS_LABEL[ticket.status]}</Badge>;
}

function Stat({ label, value, tone }: { label: string; value: number; tone?: "alert" }) {
  return (
    <div className="flex flex-col gap-0.5 rounded-lg border bg-background px-4 py-3">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className={`text-2xl font-semibold tabular-nums ${tone === "alert" && value > 0 ? "text-destructive" : ""}`}>
        {value}
      </span>
    </div>
  );
}

/** Support tickets: callers who need a person at the restaurant. Filters and paging run in the backend. */
export function SupportTab({ restaurantId }: { restaurantId: string }) {
  const [status, setStatus] = useState<TicketStatusFilter>("waiting");
  const [category, setCategory] = useState<TicketCategory | null>(null);
  const [page, setPage] = useState(1);
  const load = useCallback(() => fetchTickets(restaurantId, status, category, page), [restaurantId, status, category, page]);
  const { data, error, refresh } = usePolling<TicketsPage>(load);
  const [busy, setBusy] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);
  const [detail, setDetail] = useState<TicketDetail | null>(null);

  const loadDetail = useCallback(
    async (id: string) => {
      try {
        setDetail(await fetchTicket(restaurantId, id));
      } catch (err) {
        setActionError((err as Error).message);
      }
    },
    [restaurantId]
  );

  async function call(ticket: CallbackTicket) {
    setBusy(ticket.id);
    setActionError(null);
    try {
      const phone = await fetchCallbackPhone(restaurantId, ticket.id);
      if (ticket.status === "open") await actOnTicket(restaurantId, ticket.id, { action: "start", note: "Calling the customer" });
      window.location.href = `tel:${phone}`;
      await refresh();
      if (openId === ticket.id) await loadDetail(ticket.id);
    } catch (err) {
      setActionError((err as Error).message);
    } finally {
      setBusy(null);
    }
  }

  async function act(ticket: CallbackTicket, body: Parameters<typeof actOnTicket>[2]): Promise<boolean> {
    setBusy(ticket.id);
    setActionError(null);
    try {
      await actOnTicket(restaurantId, ticket.id, body);
      await Promise.all([refresh(), loadDetail(ticket.id)]);
      return true;
    } catch (err) {
      setActionError((err as Error).message);
      return false;
    } finally {
      setBusy(null);
    }
  }

  function open(ticket: CallbackTicket) {
    setActionError(null);
    setDetail(null);
    setOpenId(ticket.id);
    void loadDetail(ticket.id);
  }

  return (
    <>
      <SupportView
        data={data}
        error={error ?? (openId ? null : actionError)}
        busy={busy}
        status={status}
        category={category}
        onStatus={(next) => {
          setStatus(next);
          setPage(1);
        }}
        onCategory={(next) => {
          setCategory(next);
          setPage(1);
        }}
        onPage={setPage}
        onCall={call}
        onOpen={open}
      />
      <TicketSheet
        open={openId !== null}
        ticket={detail && detail.id === openId ? detail : null}
        busy={busy === openId}
        error={actionError}
        onClose={() => setOpenId(null)}
        onCall={call}
        onAct={act}
      />
    </>
  );
}

export function SupportView({
  data,
  error,
  busy,
  status,
  category,
  onStatus,
  onCategory,
  onPage,
  onCall,
  onOpen,
}: {
  data: TicketsPage | null;
  error: string | null;
  busy: string | null;
  status: TicketStatusFilter;
  category: TicketCategory | null;
  onStatus: (status: TicketStatusFilter) => void;
  onCategory: (category: TicketCategory | null) => void;
  onPage: (page: number) => void;
  onCall: (ticket: CallbackTicket) => void;
  onOpen: (ticket: CallbackTicket) => void;
}) {
  const counts = data?.counts;
  const tickets = data?.tickets ?? [];
  const overdueAfter = counts?.overdue_minutes ?? 15;

  return (
    <div className="flex flex-col gap-4">
      {error && <p className="text-sm text-destructive">{error}</p>}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Waiting" value={counts?.waiting ?? 0} tone="alert" />
        <Stat label="Urgent" value={counts?.urgent ?? 0} tone="alert" />
        <Stat label={`Waiting over ${overdueAfter} min`} value={counts?.overdue ?? 0} tone="alert" />
        <Stat label="Resolved today" value={counts?.resolved_today ?? 0} />
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {(["waiting", "resolved", "all"] as TicketStatusFilter[]).map((f) => (
          <Button key={f} size="sm" variant={status === f ? "default" : "outline"} onClick={() => onStatus(f)}>
            {f === "waiting" ? `Waiting (${counts?.waiting ?? 0})` : f === "resolved" ? "Resolved" : "All"}
          </Button>
        ))}
        <select
          aria-label="Filter by category"
          className="h-8 rounded-md border bg-background px-2 text-sm"
          value={category ?? "any"}
          onChange={(e) => onCategory(e.target.value === "any" ? null : (e.target.value as TicketCategory))}
        >
          <option value="any">All categories</option>
          {Object.entries(TICKET_CATEGORIES).map(([key, label]) => (
            <option key={key} value={key}>
              {label}
            </option>
          ))}
        </select>
        <span className="text-xs text-muted-foreground">Urgent first, then the longest wait. Raised against the number the call came from.</span>
      </div>

      <div className="rounded-lg border bg-background">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Raised</TableHead>
              <TableHead>Customer</TableHead>
              <TableHead>Issue</TableHead>
              <TableHead>Waiting</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="text-right">Action</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {tickets.length === 0 ? (
              <TableRow>
                <TableCell colSpan={6} className="text-center text-muted-foreground">
                  {data
                    ? status === "waiting"
                      ? "Nothing waiting. Tickets appear here when a caller needs a person."
                      : "No tickets here."
                    : "Loading…"}
                </TableCell>
              </TableRow>
            ) : (
              tickets.map((t) => {
                const overdue = isWaiting(t) && minutesSince(t.created_at) > overdueAfter;
                return (
                  <TableRow key={t.id} className="cursor-pointer align-top" onClick={() => onOpen(t)}>
                    <TableCell className="text-xs whitespace-nowrap text-muted-foreground">
                      {formatTime(t.created_at)}
                      {t.order_ref && <span className="block font-mono">{t.order_ref}</span>}
                    </TableCell>
                    <TableCell>
                      <div className="flex flex-col gap-0.5">
                        <span className="font-medium">{t.customer.name ?? "Caller"}</span>
                        <span className="text-xs text-muted-foreground">{t.customer.phone ?? "No number"}</span>
                      </div>
                    </TableCell>
                    <TableCell className="max-w-80">
                      <div className="mb-1 flex flex-wrap gap-1">
                        {t.priority === "urgent" && <Badge variant="destructive">Urgent</Badge>}
                        <Badge variant="outline">{t.category_label}</Badge>
                      </div>
                      <span className="text-sm font-medium text-amber-700 dark:text-amber-400">{t.reason || "—"}</span>
                    </TableCell>
                    <TableCell className={`text-sm whitespace-nowrap ${overdue ? "font-semibold text-destructive" : ""}`}>
                      {isWaiting(t) ? waited(t.created_at) : <span className="text-muted-foreground">—</span>}
                      {t.attempts > 0 && (
                        <span className="block text-xs font-normal text-muted-foreground">
                          {t.attempts} unanswered call{t.attempts > 1 ? "s" : ""}
                        </span>
                      )}
                    </TableCell>
                    <TableCell>
                      <StatusBadge ticket={t} />
                      {t.resolved_at && <span className="mt-1 block text-xs text-muted-foreground">{formatTime(t.resolved_at)}</span>}
                    </TableCell>
                    <TableCell className="text-right" onClick={(e) => e.stopPropagation()}>
                      <div className="flex justify-end gap-2">
                        {isWaiting(t) && (
                          <Button size="sm" disabled={!t.can_call || busy === t.id} onClick={() => onCall(t)}>
                            Call
                          </Button>
                        )}
                        <Button size="sm" variant="outline" onClick={() => onOpen(t)}>
                          Open
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                );
              })
            )}
          </TableBody>
        </Table>
      </div>
      <Pager page={data?.page ?? 1} hasMore={data?.has_more ?? false} onPage={onPage} />
    </div>
  );
}

/** Previous / next page, when there is more than one page. */
export function Pager({ page, hasMore, onPage }: { page: number; hasMore: boolean; onPage: (page: number) => void }) {
  if (page === 1 && !hasMore) return null;
  return (
    <div className="flex items-center justify-end gap-2 text-sm">
      <Button size="sm" variant="outline" disabled={page <= 1} onClick={() => onPage(page - 1)}>
        ‹ Newer
      </Button>
      <span className="text-muted-foreground">Page {page}</span>
      <Button size="sm" variant="outline" disabled={!hasMore} onClick={() => onPage(page + 1)}>
        Older ›
      </Button>
    </div>
  );
}

function TicketSheet({
  open,
  ticket,
  busy,
  error,
  onClose,
  onCall,
  onAct,
}: {
  open: boolean;
  ticket: TicketDetail | null;
  busy: boolean;
  error: string | null;
  onClose: () => void;
  onCall: (ticket: CallbackTicket) => void;
  onAct: (ticket: CallbackTicket, body: Parameters<typeof actOnTicket>[2]) => Promise<boolean>;
}) {
  const [note, setNote] = useState("");
  const [notify, setNotify] = useState(true);

  async function run(action: TicketAction, extra: { category?: TicketCategory; needsNote?: boolean } = {}) {
    if (!ticket) return;
    const ok = await onAct(ticket, {
      action,
      note: note.trim() || undefined,
      category: extra.category,
      notify_customer: (action === "resolve" || action === "no_answer") && notify,
    });
    if (ok) setNote("");
  }

  return (
    <Sheet open={open} onOpenChange={(next) => !next && onClose()}>
      <SheetContent side="right" className="w-full overflow-y-auto sm:max-w-lg">
        {!ticket && (
          <div className="p-6">
            {error ? <p className="text-sm text-destructive">{error}</p> : <Skeleton className="h-64" />}
          </div>
        )}
        {ticket && (
          <>
            <SheetHeader>
              <SheetTitle className="flex flex-wrap items-center gap-2">
                {ticket.category_label}
                {ticket.priority === "urgent" && <Badge variant="destructive">Urgent</Badge>}
                <StatusBadge ticket={ticket} />
              </SheetTitle>
              <SheetDescription>
                {ticket.customer.name ?? "Caller"} · {ticket.customer.phone ?? "no number"} · raised {formatTime(ticket.created_at)}
                {isWaiting(ticket) && ` · waiting ${waited(ticket.created_at)}`}
              </SheetDescription>
            </SheetHeader>

            <div className="flex flex-col gap-5 px-4 pb-6">
              <section className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm font-medium text-amber-900 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-200">
                {ticket.reason || "No reason given"}
              </section>

              {error && <p className="text-sm text-destructive">{error}</p>}

              {isWaiting(ticket) ? (
                <section className="flex flex-col gap-3">
                  <div className="flex flex-wrap gap-2">
                    <Button disabled={!ticket.can_call || busy} onClick={() => onCall(ticket)}>
                      Call customer
                    </Button>
                    {ticket.status === "open" && (
                      <Button variant="outline" disabled={busy} onClick={() => run("start")}>
                        I&apos;m on it
                      </Button>
                    )}
                    <Button variant="outline" disabled={busy} onClick={() => run("no_answer")}>
                      No answer
                    </Button>
                  </div>
                  <Textarea
                    placeholder="Note: what the customer said, or what was done (saved on the ticket)"
                    value={note}
                    onChange={(e) => setNote(e.target.value)}
                    rows={3}
                  />
                  <label className="flex items-center gap-2 text-sm">
                    <input type="checkbox" checked={notify} onChange={(e) => setNotify(e.target.checked)} />
                    Tell the customer on WhatsApp (when resolving, or after an unanswered call)
                  </label>
                  <div className="flex flex-wrap gap-2">
                    <Button disabled={busy} onClick={() => run("resolve")}>
                      Resolve
                    </Button>
                    <Button variant="outline" disabled={busy || !note.trim()} onClick={() => run("note")}>
                      Add note
                    </Button>
                  </div>
                </section>
              ) : (
                <section className="flex flex-col gap-2 text-sm">
                  {ticket.resolution && (
                    <p>
                      <span className="text-muted-foreground">Resolution: </span>
                      {ticket.resolution}
                    </p>
                  )}
                  <Button variant="outline" className="w-fit" disabled={busy} onClick={() => run("reopen")}>
                    Reopen
                  </Button>
                </section>
              )}

              <section className="flex flex-wrap items-center gap-2 text-sm">
                <span className="text-muted-foreground">Category</span>
                <select
                  aria-label="Change category"
                  className="h-8 rounded-md border bg-background px-2"
                  value={ticket.category}
                  disabled={busy}
                  onChange={(e) => run("category", { category: e.target.value as TicketCategory })}
                >
                  {Object.entries(TICKET_CATEGORIES).map(([key, label]) => (
                    <option key={key} value={key}>
                      {label}
                    </option>
                  ))}
                </select>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={busy}
                  onClick={() => run(ticket.priority === "urgent" ? "normal" : "urgent")}
                >
                  {ticket.priority === "urgent" ? "Mark normal" : "Mark urgent"}
                </Button>
              </section>

              {ticket.order && (
                <section className="flex flex-col gap-1 text-sm">
                  <h3 className="font-semibold">
                    Order {ticket.order_ref}
                    {ticket.order.status && <span className="font-normal text-muted-foreground"> · {ticket.order.status}</span>}
                  </h3>
                  <ul>
                    {ticket.order.items.map((line, i) => (
                      <li key={`${line.id}-${i}`}>
                        {line.quantity}× {line.name}
                        {line.variant ? ` (${line.variant})` : ""}
                      </li>
                    ))}
                  </ul>
                  {ticket.order.total != null && <span className="font-medium">{formatPrice(ticket.order.total)}</span>}
                </section>
              )}

              <section className="flex flex-col gap-2 text-sm">
                <h3 className="font-semibold">History</h3>
                <ol className="flex flex-col gap-2 border-l pl-3">
                  {(ticket.activity.length ? ticket.activity : [{ at: ticket.created_at, kind: "opened", text: ticket.reason, by: "Kabir" } as TicketEvent]).map(
                    (e, i) => (
                      <li key={i}>
                        <span className="font-medium">{EVENT_LABEL[e.kind] ?? e.kind}</span>
                        <span className="text-xs text-muted-foreground">
                          {" "}
                          · {formatTime(e.at)}
                          {e.by ? ` · ${e.by}` : ""}
                        </span>
                        {e.text && <span className="block text-muted-foreground">{e.text}</span>}
                      </li>
                    )
                  )}
                </ol>
              </section>

              <section className="flex flex-col gap-2 text-sm">
                <h3 className="font-semibold">Call transcript</h3>
                <CallTranscript
                  lines={ticket.transcript}
                  empty="Not available for this call: Sarvam sends it when the call ends."
                />
              </section>
            </div>
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}
