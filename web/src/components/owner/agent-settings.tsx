"use client";

import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { AuthRequiredError, fetchAgentSettings, saveAgentSettings, type AgentSettings } from "@/lib/owner-api";

const EXAMPLE = `- Pasta comes in penne or spaghetti: always ask which, and put it in the dish's note.
- Every dish marked Jain-friendly can be made Jain: no onion, garlic or potato.
- Sizzlers take about 25 minutes. Say so when someone orders one.
- We deliver within 5 km of Andheri West. Further away, offer pickup.
- Last orders at 10:45 pm.`;

function when(iso: string | null): string | null {
  if (!iso) return null;
  return new Date(iso).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });
}

export function AgentSettingsTab({ restaurantId }: { restaurantId: string }) {
  const [settings, setSettings] = useState<AgentSettings | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let current = true;
    fetchAgentSettings(restaurantId)
      .then((next) => current && setSettings(next))
      .catch((err) => {
        if (current && !(err instanceof AuthRequiredError)) setError((err as Error).message);
      });
    return () => {
      current = false;
    };
  }, [restaurantId]);

  if (error) return <p className="text-sm text-destructive">{error}</p>;
  if (!settings) return <Skeleton className="h-64" />;
  return <AgentSettingsView restaurantId={restaurantId} settings={settings} onSaved={setSettings} />;
}

export function AgentSettingsView({
  restaurantId,
  settings,
  onSaved,
}: {
  restaurantId: string;
  settings: AgentSettings;
  onSaved: (s: AgentSettings) => void;
}) {
  return (
    <div className="grid gap-4 lg:grid-cols-[3fr_2fr]">
      <RuleBook restaurantId={restaurantId} settings={settings} onSaved={onSaved} />
      <WhatsAppNumbers restaurantId={restaurantId} settings={settings} onSaved={onSaved} />
    </div>
  );
}

function RuleBook({
  restaurantId,
  settings,
  onSaved,
}: {
  restaurantId: string;
  settings: AgentSettings;
  onSaved: (s: AgentSettings) => void;
}) {
  const [rules, setRules] = useState(settings.rules);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const changed = rules !== settings.rules;
  const tooLong = rules.length > settings.rules_limit;

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setMessage(null);
    try {
      const next = await saveAgentSettings(restaurantId, { rules });
      onSaved(next);
      setRules(next.rules);
      setMessage("Saved. Your agent follows it from the next call.");
    } catch (err) {
      setMessage((err as Error).message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Rule book</CardTitle>
        <CardDescription>
          What your agent should know that isn&apos;t on the menu: special cases, timings, delivery limits, how you like
          things done. It reads this at the start of every call.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={save} className="flex flex-col gap-3">
          <Textarea
            aria-label="Rule book"
            value={rules}
            onChange={(e) => setRules(e.target.value)}
            placeholder={EXAMPLE}
            rows={12}
            className="font-mono text-sm leading-relaxed"
          />
          <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
            <span className={tooLong ? "font-medium text-destructive" : undefined}>
              {rules.length} / {settings.rules_limit} characters
            </span>
            {settings.rules_updated_at && <span>Last saved {when(settings.rules_updated_at)}</span>}
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <Button type="submit" disabled={saving || !changed || tooLong}>
              {saving ? "Saving…" : "Save rule book"}
            </Button>
            {!rules && (
              <Button type="button" variant="outline" onClick={() => setRules(EXAMPLE)}>
                Start from the example
              </Button>
            )}
            {message && <span className="text-sm text-muted-foreground">{message}</span>}
          </div>
          <p className="text-xs text-muted-foreground">
            Write one rule per line, as you would tell a new waiter. Prices, the bill and confirming the order are worked
            out by Sarthi from your menu, so a rule can&apos;t change them: edit the dish in the Menu tab instead.
          </p>
        </form>
      </CardContent>
    </Card>
  );
}

const label = "text-xs font-medium tracking-wide text-muted-foreground uppercase";

function WhatsAppNumbers({
  restaurantId,
  settings,
  onSaved,
}: {
  restaurantId: string;
  settings: AgentSettings;
  onSaved: (s: AgentSettings) => void;
}) {
  const { calls, whatsapp_sender: sender } = settings;
  const [alertNumber, setAlertNumber] = useState(calls?.alert_whatsapp ?? "");
  const [upiId, setUpiId] = useState(calls?.upi_id ?? "");
  const [payee, setPayee] = useState(calls?.upi_payee_name ?? "");
  const [saving, setSaving] = useState<"alert" | "upi" | null>(null);
  const [message, setMessage] = useState<{ on: "alert" | "upi"; text: string } | null>(null);

  async function save(on: "alert" | "upi", patch: { alert_whatsapp?: string; upi_id?: string; upi_payee_name?: string }) {
    setSaving(on);
    setMessage(null);
    try {
      const next = await saveAgentSettings(restaurantId, patch);
      onSaved(next);
      setAlertNumber(next.calls?.alert_whatsapp ?? alertNumber);
      setUpiId(next.calls?.upi_id ?? "");
      setPayee(next.calls?.upi_payee_name ?? "");
      setMessage({
        on,
        text:
          on === "alert"
            ? "Saved. New orders go to this number."
            : next.calls?.upi_id
              ? "Saved. New bills show this UPI ID."
              : "UPI removed. Bills now say pay on delivery or at pickup.",
      });
    } catch (err) {
      setMessage({ on, text: (err as Error).message });
    } finally {
      setSaving(null);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Phone, WhatsApp & payment</CardTitle>
        <CardDescription>Where calls come in, where you hear about orders, and how guests pay.</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-5 text-sm">
        {calls && (
          <div className="flex flex-col gap-1">
            <span className={label}>Calls answered on</span>
            {calls.calls_numbers?.length ? (
              <ul className="flex flex-col gap-0.5 font-medium">
                {calls.calls_numbers.map((n) => (
                  <li key={n}>{n}</li>
                ))}
              </ul>
            ) : (
              <span className="font-medium">Not live yet: Sarthi will connect your number</span>
            )}
            <span className="text-xs text-muted-foreground">To add or change a number, contact Sarthi.</span>
            {calls.agent_name && <span className="text-xs text-muted-foreground">Your agent answers as {calls.agent_name}.</span>}
          </div>
        )}
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void save("alert", { alert_whatsapp: alertNumber });
          }}
          className="flex flex-col gap-2"
        >
          <label htmlFor="alert-number" className={label}>
            Order alerts go to
          </label>
          <div className="flex gap-2">
            <Input
              id="alert-number"
              inputMode="tel"
              value={alertNumber}
              onChange={(e) => setAlertNumber(e.target.value)}
              placeholder="10-digit WhatsApp number"
            />
            <Button type="submit" disabled={saving !== null || !alertNumber.trim() || alertNumber === calls?.alert_whatsapp}>
              {saving === "alert" ? "Saving…" : "Save"}
            </Button>
          </div>
          <span className="text-xs text-muted-foreground">
            New orders, callback requests and payment updates arrive here on WhatsApp. Use any phone that has WhatsApp.
          </span>
          {message?.on === "alert" && <span className="text-xs">{message.text}</span>}
        </form>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void save("upi", { upi_id: upiId, upi_payee_name: payee });
          }}
          className="flex flex-col gap-2"
        >
          <label htmlFor="upi-id" className={label}>
            UPI for payments
          </label>
          <Input id="upi-id" value={upiId} onChange={(e) => setUpiId(e.target.value)} placeholder="yourname@okhdfcbank" disabled={!calls} />
          <Input
            aria-label="Payee name"
            value={payee}
            onChange={(e) => setPayee(e.target.value)}
            placeholder="Name on the UPI account"
            disabled={!calls}
          />
          <div className="flex items-center gap-2">
            <Button
              type="submit"
              variant="outline"
              disabled={!calls || saving !== null || (upiId === (calls?.upi_id ?? "") && payee === (calls?.upi_payee_name ?? ""))}
            >
              {saving === "upi" ? "Saving…" : "Save UPI"}
            </Button>
          </div>
          <span className="text-xs text-muted-foreground">
            {calls
              ? "The WhatsApp bill shows this UPI ID so guests can pay from any UPI app. Leave it empty to take payment on delivery or at pickup."
              : "Save the number for order alerts first."}
          </span>
          {message?.on === "upi" && <span className="text-xs">{message.text}</span>}
        </form>
        <div className="flex flex-col gap-1">
          <span className={label}>Bills are sent from</span>
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-medium">{sender.number ?? "Sarthi's WhatsApp number"}</span>
            <Badge variant={sender.own_number ? "default" : "secondary"}>
              {sender.own_number ? "Your business number" : "Shared Sarthi number"}
            </Badge>
          </div>
          <span className="text-xs text-muted-foreground">
            {sender.own_number
              ? "Guests see your restaurant's WhatsApp Business number. To change it, contact Sarthi."
              : "To send bills from your own WhatsApp Business number, share it with Sarthi and we'll connect it."}
          </span>
        </div>
      </CardContent>
    </Card>
  );
}
