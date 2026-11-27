"use client";

import { type FormEvent, useCallback, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

type Restaurant = { id: string; name: string; slug: string; status: string };
type Integration = {
  id: string;
  restaurant_id: string;
  provider: string;
  environment: "sandbox" | "production";
  pos_restaurant_id: string;
  app_key_hint: string;
  app_secret_hint: string;
  access_token_hint: string;
  webhook_token_hint: string;
  status: "draft" | "menu_synced" | "live" | "paused";
  notes: string;
  last_menu_sync_at: string | null;
  last_error: string | null;
  credentials_updated_at: string;
  created_at: string;
  restaurants: { id: string; name: string; slug: string } | null;
};
type Webhook = { base_url: string | null; base_url_missing: boolean; client_authorization: string | null };
type Overview = {
  restaurants: Restaurant[];
  integrations: Integration[];
  encryption_ready: boolean;
  public_base_url_set: boolean;
};

const NEW = "__new__";
const STATUSES: Integration["status"][] = ["draft", "menu_synced", "live", "paused"];
const selectClass =
  "h-8 w-full rounded-lg border border-input bg-transparent px-2 text-sm outline-none focus-visible:border-ring dark:bg-input/30";

function errorText(data: { detail?: unknown; error?: string }, fallback: string): string {
  if (typeof data.detail === "string") return data.detail;
  // FastAPI validation errors: [{loc, msg}, ...]
  if (Array.isArray(data.detail)) {
    return data.detail
      .map((d: { loc?: string[]; msg?: string }) => `${(d.loc ?? []).slice(1).join(".")}: ${d.msg}`.replace(/^: /, ""))
      .join("; ");
  }
  return data.error ?? fallback;
}

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <label className="block space-y-1">
      <span className="text-sm font-medium">{label}</span>
      {children}
      {hint && <span className="block text-xs text-muted-foreground">{hint}</span>}
    </label>
  );
}

function Masked({ label, hint }: { label: string; hint: string }) {
  return (
    <span className="text-xs text-muted-foreground">
      {label} <span className="font-mono">{hint ? `••••${hint}` : "••••"}</span>
    </span>
  );
}

function CopyRow({ label, value }: { label: string; value: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="space-y-1">
      <p className="text-xs font-medium">{label}</p>
      <div className="flex gap-2">
        <code className="flex-1 break-all rounded-md bg-muted px-2 py-1.5 text-xs">{value}</code>
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={() => {
            navigator.clipboard.writeText(value).then(() => setCopied(true));
          }}
        >
          {copied ? "Copied" : "Copy"}
        </Button>
      </div>
    </div>
  );
}

function WebhookSetup({ webhook, onDone }: { webhook: Webhook; onDone: () => void }) {
  return (
    <Card className="border-primary">
      <CardHeader>
        <CardTitle className="text-base">Paste this into Petpooja → Configuration</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-sm text-muted-foreground">
          The token is shown <strong>only now</strong>. Only its hash is stored, so if it&apos;s lost, generate a new
          one.
        </p>
        {webhook.base_url ? (
          <CopyRow label="Base URL" value={webhook.base_url} />
        ) : (
          <p className="text-sm text-destructive">
            PUBLIC_BASE_URL isn&apos;t set on the API, so there&apos;s no base URL to give yet.
          </p>
        )}
        {webhook.client_authorization && (
          <CopyRow label="Client Authorization" value={webhook.client_authorization} />
        )}
        <Button type="button" onClick={onDone}>
          I&apos;ve saved it
        </Button>
      </CardContent>
    </Card>
  );
}

function OnboardForm({
  adminKey,
  restaurants,
  onSaved,
}: {
  adminKey: string;
  restaurants: Restaurant[];
  onSaved: (webhook: Webhook, note: string | null) => void;
}) {
  const [restaurantId, setRestaurantId] = useState(NEW);
  const [name, setName] = useState("");
  const [cuisine, setCuisine] = useState("");
  const [ownerEmail, setOwnerEmail] = useState("");
  const [environment, setEnvironment] = useState<"sandbox" | "production">("sandbox");
  const [posId, setPosId] = useState("");
  const [appKey, setAppKey] = useState("");
  const [appSecret, setAppSecret] = useState("");
  const [accessToken, setAccessToken] = useState("");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    const body = {
      ...(restaurantId === NEW
        ? { new_restaurant: { name, cuisine: cuisine || null, owner_email: ownerEmail || null } }
        : { restaurant_id: restaurantId }),
      provider: "petpooja",
      environment,
      pos_restaurant_id: posId,
      app_key: appKey,
      app_secret: appSecret,
      access_token: accessToken,
      notes,
    };
    try {
      const res = await fetch("/api/admin/pos/integrations", {
        method: "POST",
        headers: { "X-Admin-Key": adminKey, "content-type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (!res.ok) {
        setError(errorText(data, "Couldn't save"));
        return;
      }
      // Clear the secrets from memory as soon as they're stored.
      setAppKey("");
      setAppSecret("");
      setAccessToken("");
      setPosId("");
      setName("");
      setCuisine("");
      setOwnerEmail("");
      setNotes("");
      onSaved(data.webhook, data.owner_note);
    } catch {
      setError("Couldn't reach the server");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Onboard a restaurant</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} className="space-y-4" autoComplete="off">
          <Field label="Restaurant">
            <select className={selectClass} value={restaurantId} onChange={(e) => setRestaurantId(e.target.value)}>
              <option value={NEW}>+ New restaurant</option>
              {restaurants.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.name} ({r.slug}){r.status === "draft" ? " · draft" : ""}
                </option>
              ))}
            </select>
          </Field>

          {restaurantId === NEW && (
            <div className="grid gap-3 sm:grid-cols-3">
              <Field label="Name">
                <Input value={name} onChange={(e) => setName(e.target.value)} required placeholder="The Fusion Kitchen" />
              </Field>
              <Field label="Cuisine (optional)">
                <Input value={cuisine} onChange={(e) => setCuisine(e.target.value)} placeholder="Multi-cuisine" />
              </Field>
              <Field label="Owner email (optional)" hint="Must already have a Sarthi account">
                <Input type="email" value={ownerEmail} onChange={(e) => setOwnerEmail(e.target.value)} />
              </Field>
            </div>
          )}

          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Environment">
              <select
                className={selectClass}
                value={environment}
                onChange={(e) => setEnvironment(e.target.value as "sandbox" | "production")}
              >
                <option value="sandbox">Sandbox (testing)</option>
                <option value="production">Production (live orders)</option>
              </select>
            </Field>
            <Field label="restID / mapping code" hint="From Petpooja; sent with every order">
              <Input value={posId} onChange={(e) => setPosId(e.target.value)} required placeholder="f871uxkp" />
            </Field>
          </div>

          <div className="grid gap-3 sm:grid-cols-3">
            <Field label="App key">
              <Input type="password" value={appKey} onChange={(e) => setAppKey(e.target.value)} required autoComplete="off" />
            </Field>
            <Field label="App secret">
              <Input
                type="password"
                value={appSecret}
                onChange={(e) => setAppSecret(e.target.value)}
                required
                autoComplete="off"
              />
            </Field>
            <Field label="Access token">
              <Input
                type="password"
                value={accessToken}
                onChange={(e) => setAccessToken(e.target.value)}
                required
                autoComplete="off"
              />
            </Field>
          </div>
          <p className="text-xs text-muted-foreground">
            Petpooja → Configuration. They&apos;re encrypted before they&apos;re saved and are never shown again; to
            change one, paste a new value on the integration below.
          </p>

          <Field label="Notes (optional)">
            <Input value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Who sent these, when" />
          </Field>

          {error && <p className="text-sm text-destructive">{error}</p>}
          <Button type="submit" disabled={busy}>
            {busy ? "Saving…" : "Save and encrypt"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

function IntegrationCard({
  integration,
  adminKey,
  onChanged,
  onWebhook,
}: {
  integration: Integration;
  adminKey: string;
  onChanged: () => void;
  onWebhook: (webhook: Webhook) => void;
}) {
  const [rotating, setRotating] = useState(false);
  const [secrets, setSecrets] = useState({ app_key: "", app_secret: "", access_token: "" });
  const [error, setError] = useState<string | null>(null);

  async function call(path: string, method: string, body?: object) {
    setError(null);
    const res = await fetch(`/api/admin/pos/integrations/${integration.id}${path}`, {
      method,
      headers: { "X-Admin-Key": adminKey, "content-type": "application/json" },
      body: body ? JSON.stringify(body) : undefined,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      setError(errorText(data, "Couldn't save"));
      return null;
    }
    return data;
  }

  async function saveSecrets(event: FormEvent) {
    event.preventDefault();
    const changed = Object.fromEntries(Object.entries(secrets).filter(([, v]) => v.trim()));
    if (Object.keys(changed).length === 0) return;
    if (await call("", "PATCH", changed)) {
      setSecrets({ app_key: "", app_secret: "", access_token: "" });
      setRotating(false);
      onChanged();
    }
  }

  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
        <CardTitle className="text-base">
          {integration.restaurants?.name ?? "Unknown restaurant"}{" "}
          <span className="text-sm font-normal text-muted-foreground">· {integration.provider}</span>
        </CardTitle>
        <div className="flex gap-2">
          <Badge variant={integration.environment === "production" ? "default" : "secondary"}>
            {integration.environment}
          </Badge>
          <Badge variant={integration.status === "live" ? "default" : "outline"}>{integration.status}</Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex flex-wrap gap-x-4 gap-y-1">
          <span className="text-xs text-muted-foreground">
            restID <span className="font-mono text-foreground">{integration.pos_restaurant_id}</span>
          </span>
          <Masked label="app key" hint={integration.app_key_hint} />
          <Masked label="secret" hint={integration.app_secret_hint} />
          <Masked label="token" hint={integration.access_token_hint} />
          <Masked label="webhook token" hint={integration.webhook_token_hint} />
        </div>
        <p className="text-xs text-muted-foreground">
          Credentials saved {new Date(integration.credentials_updated_at).toLocaleString()} · menu{" "}
          {integration.last_menu_sync_at
            ? `synced ${new Date(integration.last_menu_sync_at).toLocaleString()}`
            : "not received yet"}
          {integration.notes ? ` · ${integration.notes}` : ""}
        </p>
        {integration.last_error && <p className="text-xs text-destructive">Last error: {integration.last_error}</p>}

        <div className="flex flex-wrap items-center gap-2">
          <select
            className={`${selectClass} w-auto`}
            value={integration.status}
            aria-label="Status"
            onChange={async (e) => {
              if (await call("", "PATCH", { status: e.target.value })) onChanged();
            }}
          >
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
          <Button size="sm" variant="outline" onClick={() => setRotating((v) => !v)}>
            Replace credentials
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={async () => {
              if (!window.confirm("The old webhook token stops working right away. Generate a new one?")) return;
              const data = await call("/webhook-token", "POST");
              if (data) {
                onWebhook(data.webhook);
                onChanged();
              }
            }}
          >
            New webhook token
          </Button>
        </div>

        {rotating && (
          <form onSubmit={saveSecrets} className="grid gap-2 sm:grid-cols-4" autoComplete="off">
            {(["app_key", "app_secret", "access_token"] as const).map((field) => (
              <Input
                key={field}
                type="password"
                placeholder={`New ${field.replace("_", " ")} (blank = keep)`}
                aria-label={field}
                value={secrets[field]}
                onChange={(e) => setSecrets({ ...secrets, [field]: e.target.value })}
                autoComplete="off"
              />
            ))}
            <Button type="submit" size="sm">
              Save
            </Button>
          </form>
        )}
        {error && <p className="text-sm text-destructive">{error}</p>}
      </CardContent>
    </Card>
  );
}

export default function OnboardingPage() {
  const [key, setKey] = useState("");
  const [draft, setDraft] = useState("");
  const [overview, setOverview] = useState<Overview | null>(null);
  const [webhook, setWebhook] = useState<Webhook | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (adminKey: string) => {
    try {
      const res = await fetch("/api/admin/pos/overview", { cache: "no-store", headers: { "X-Admin-Key": adminKey } });
      const data = await res.json();
      if (!res.ok) {
        setError(errorText(data, "Couldn't load"));
        setOverview(null);
        return;
      }
      setError(null);
      setOverview(data);
    } catch {
      setError("Couldn't reach the server");
    }
  }, []);

  function unlock(event: FormEvent) {
    event.preventDefault();
    setKey(draft);
    load(draft);
  }

  return (
    <div className="mx-auto w-full max-w-3xl space-y-4 p-4">
      <h1 className="text-lg font-semibold">Restaurant onboarding · POS</h1>
      {/* The admin key stays in memory only. */}
      <form onSubmit={unlock} className="flex gap-2">
        <Input
          type="password"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Admin key"
          aria-label="Admin key"
          autoComplete="off"
        />
        <Button type="submit">Open</Button>
      </form>
      {error && <p className="text-sm text-destructive">{error}</p>}

      {overview && !overview.encryption_ready && (
        <p className="rounded-lg border border-destructive p-3 text-sm text-destructive">
          POS_ENCRYPTION_KEY isn&apos;t set on the API, so credentials can&apos;t be saved yet. Generate one with{" "}
          <code>python -m app.pos.crypto</code> and add it to the API&apos;s environment.
        </p>
      )}

      {webhook && (
        <WebhookSetup
          webhook={webhook}
          onDone={() => {
            setWebhook(null);
            setNote(null);
          }}
        />
      )}
      {note && <p className="text-sm text-muted-foreground">{note}</p>}

      {overview && (
        <>
          <OnboardForm
            adminKey={key}
            restaurants={overview.restaurants}
            onSaved={(hook, ownerNote) => {
              setWebhook(hook);
              setNote(ownerNote);
              load(key);
            }}
          />
          <h2 className="pt-2 text-base font-semibold">Integrations</h2>
          {overview.integrations.length === 0 && (
            <p className="text-sm text-muted-foreground">No restaurants connected to a POS yet.</p>
          )}
          {overview.integrations.map((integration) => (
            <IntegrationCard
              key={integration.id}
              integration={integration}
              adminKey={key}
              onChanged={() => load(key)}
              onWebhook={setWebhook}
            />
          ))}
        </>
      )}
    </div>
  );
}
