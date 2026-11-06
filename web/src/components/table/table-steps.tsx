"use client";

import { Minus, Plus, Star } from "lucide-react";
import { useEffect, useState } from "react";

import { Button, buttonVariants } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import { Textarea } from "@/components/ui/textarea";
import type { TableSession } from "@/hooks/use-table-session";
import { fetchTableBill, payForTable, sendTableFeedback, type TableBill } from "@/lib/api";
import { cn, formatPrice } from "@/lib/utils";

const lineLabel = (line: { name: string; variant?: string | null }) =>
  line.variant ? `${line.name} (${line.variant})` : line.name;

/** The bill: every round sent to the kitchen, GST, an equal split, and how the guest pays. */
export function BillStep({
  t,
  restaurantName,
  onBack,
  onPaid,
}: {
  t: TableSession;
  restaurantName: string;
  onBack: () => void;
  onPaid: () => void;
}) {
  const [people, setPeople] = useState(t.table?.people ?? 1);
  const [bill, setBill] = useState<TableBill | null>(null);
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [offers, setOffers] = useState(false);
  const { ctx, run } = t;

  useEffect(() => {
    if (!ctx) return;
    let cancelled = false;
    void run(() => fetchTableBill(ctx, people)).then((next) => !cancelled && next && setBill(next));
    return () => {
      cancelled = true;
    };
  }, [ctx, people, run]);

  async function pay(method: "upi" | "counter") {
    if (!ctx) return;
    const view = await run(() =>
      payForTable(ctx, { method, name: name.trim() || undefined, phone: phone.trim() || undefined, offers_opt_in: offers })
    );
    if (view) {
      t.setTable(view);
      onPaid();
    }
  }

  const unsentNote = t.unsent.length > 0;

  return (
    <>
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium">Bill{t.table?.table_no ? ` · Table ${t.table.table_no}` : ""}</h3>
        <button type="button" onClick={onBack} className="text-xs text-muted-foreground underline-offset-4 hover:underline">
          Back to order
        </button>
      </div>

      {unsentNote && (
        <p className="rounded-md bg-muted p-2 text-xs">Some dishes in your cart are not sent yet, so they are not on this bill.</p>
      )}

      {!bill ? (
        <p className="text-sm text-muted-foreground">Loading the bill…</p>
      ) : (
        <div className="flex flex-col gap-1 text-sm">
          {bill.lines.map((line) => (
            <div key={`${line.id}|${line.variant ?? ""}`} className="flex justify-between gap-2">
              <span>
                {line.quantity} × {lineLabel(line)}
              </span>
              <span>{formatPrice(line.line_total)}</span>
            </div>
          ))}
          <Separator className="my-1" />
          <div className="flex justify-between text-muted-foreground">
            <span>GST {bill.gst_rate}%</span>
            <span>{formatPrice(bill.gst)}</span>
          </div>
          <div className="flex justify-between text-base font-semibold">
            <span>Total</span>
            <span>{formatPrice(bill.total)}</span>
          </div>
        </div>
      )}

      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-sm font-medium">Split the bill</p>
          <p className="text-xs text-muted-foreground">
            {bill && people > 1 ? `${people} people, ${formatPrice(bill.share)} each` : "Tap + to split equally"}
          </p>
        </div>
        <div className="flex items-center rounded-lg border">
          <button type="button" aria-label="Fewer people" className="flex size-10 items-center justify-center" onClick={() => setPeople((p) => Math.max(1, p - 1))}>
            <Minus className="size-4" />
          </button>
          <span className="min-w-6 text-center text-sm font-medium">{people}</span>
          <button type="button" aria-label="More people" className="flex size-10 items-center justify-center" onClick={() => setPeople((p) => Math.min(20, p + 1))}>
            <Plus className="size-4" />
          </button>
        </div>
      </div>

      <div className="flex flex-col gap-2">
        <label className="flex flex-col gap-1 text-sm">
          <span className="font-medium">Your name (optional)</span>
          <Input value={name} autoComplete="name" onChange={(e) => setName(e.target.value)} />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          <span className="font-medium">Mobile number (optional)</span>
          <Input
            value={phone}
            type="tel"
            inputMode="numeric"
            autoComplete="tel"
            placeholder="10-digit number"
            onChange={(e) => setPhone(e.target.value)}
          />
          <span className="text-xs text-muted-foreground">Saved by {restaurantName} with this visit.</span>
        </label>
        <label className={cn("flex items-start gap-2 text-xs", !phone.trim() && "opacity-60")}>
          <input
            type="checkbox"
            className="mt-0.5 size-4"
            checked={offers && Boolean(phone.trim())}
            disabled={!phone.trim()}
            onChange={(e) => setOffers(e.target.checked)}
          />
          <span>Send me offers from {restaurantName} on WhatsApp. I can stop them any time.</span>
        </label>
      </div>

      {bill?.upi_link ? (
        <a
          href={bill.upi_link}
          onClick={() => void pay("upi")}
          className={cn(buttonVariants(), "h-11 w-full")}
        >
          Pay {formatPrice(bill.share)} with UPI
        </a>
      ) : (
        bill && <p className="text-xs text-muted-foreground">{restaurantName} takes payment at the counter.</p>
      )}
      <Button variant="outline" className="h-10" disabled={t.busy || !bill} onClick={() => void pay("counter")}>
        Pay at the counter
      </Button>
    </>
  );
}

/** After choosing how to pay: the rating, a private note to the owner, and the Google review link. */
export function DoneStep({ t, restaurantName }: { t: TableSession; restaurantName: string }) {
  const [rating, setRating] = useState(t.table?.rating ?? 0);
  const [message, setMessage] = useState("");
  const [reviewUrl, setReviewUrl] = useState<string | null>(null);
  const [sent, setSent] = useState(false);
  const { ctx, run } = t;
  const upi = t.table?.payment_method === "upi";

  async function rate(stars: number, note?: string) {
    if (!ctx) return;
    setRating(stars);
    const result = await run(() => sendTableFeedback(ctx, stars, note));
    if (result) {
      setReviewUrl(result.review_url);
      if (note) setSent(true);
    }
  }

  return (
    <>
      <div>
        <h3 className="text-base font-semibold">{upi ? "Thank you!" : "Please pay at the counter"}</h3>
        <p className="text-sm text-muted-foreground">
          {upi
            ? "Staff will confirm once your payment arrives."
            : `Your bill is ready there${t.table?.table_no ? `. Mention table ${t.table.table_no}` : ""}.`}
        </p>
      </div>

      <div>
        <p className="text-sm font-medium">How was your meal?</p>
        <div className="mt-1 flex gap-1" role="group" aria-label="Rate your meal">
          {[1, 2, 3, 4, 5].map((stars) => (
            <button
              key={stars}
              type="button"
              aria-label={`${stars} ${stars === 1 ? "star" : "stars"}`}
              aria-pressed={stars === rating}
              onClick={() => void rate(stars)}
              className="flex size-11 items-center justify-center"
            >
              <Star className={cn("size-7", stars <= rating ? "fill-primary text-primary" : "text-muted-foreground")} />
            </button>
          ))}
        </div>
      </div>

      {rating > 0 && rating < 4 && (
        <div className="flex flex-col gap-2">
          <label className="flex flex-col gap-1 text-sm">
            <span>Sorry about that. Tell the owner what went wrong; they see it right away.</span>
            <Textarea rows={3} value={message} disabled={sent} onChange={(e) => setMessage(e.target.value)} />
          </label>
          <Button
            className="h-10"
            disabled={sent || t.busy || !message.trim()}
            onClick={() => void rate(rating, message.trim())}
          >
            {sent ? "Sent. The owner has your message." : "Send to the owner"}
          </Button>
        </div>
      )}

      {rating > 0 && reviewUrl && (
        <a
          href={reviewUrl}
          target="_blank"
          rel="noreferrer"
          className={cn(buttonVariants({ variant: rating >= 4 ? "default" : "outline" }), "h-10 w-full")}
        >
          Review {restaurantName} on Google
        </a>
      )}

      <p className="text-center text-[11px] text-muted-foreground">Powered by Sarthi</p>
    </>
  );
}
