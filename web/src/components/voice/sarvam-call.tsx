"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Phone, PhoneOff, ShoppingBag } from "lucide-react";
import { AgentState, BrowserAudioInterface, ConversationAgent, InteractionType } from "sarvam-conv-ai-sdk/browser";

import { Button } from "@/components/ui/button";
import { AgentOrb, type OrbState } from "@/components/voice/agent-orb";

/**
 * A browser call to the restaurant agent running on Sarvam Samvaad. Sarvam hears, thinks and speaks; the menu,
 * cart and order live in our backend, which Samvaad calls through its API tools (app/samvaad). The page names
 * the restaurant in the `store_slug` agent variable, so one Samvaad agent serves every restaurant.
 *
 * The SDK's signed-URL request goes to /api/sarvam/... (our proxy adds the Sarvam key server-side), and the
 * live cart is read from /api/sarvam/cart/{interaction id} while the call is going.
 */

interface Store {
  slug: string;
  name: string;
  agent_name?: string | null;
}

interface SarvamConfig {
  enabled: boolean;
  org_id: string;
  workspace_id: string;
  app_id: string;
  version: string | null;
  stores: Store[];
}

interface CartLine {
  id: string;
  name: string;
  price: number;
  quantity: number;
  variant?: string;
}

interface LiveCart {
  active: boolean;
  cart: CartLine[];
  cart_total: string;
  order_placed: boolean;
}

interface Line {
  role: "user" | "bot";
  text: string;
}

const ORB: Record<string, OrbState> = {
  idle: "idle",
  connecting: "connecting",
  connected: "connecting",
  listening: "listening",
  speaking: "speaking",
  error: "idle",
};

const STATUS: Record<string, string> = {
  idle: "Ready",
  connecting: "Connecting…",
  connected: "Connected",
  listening: "Listening",
  speaking: "Speaking",
  error: "Something went wrong",
};

function micError(error: unknown): string {
  const name = error instanceof Error ? error.name : "";
  if (name === "NotAllowedError") return "Microphone access was blocked. Allow it in the browser and try again.";
  if (name === "NotFoundError") return "No microphone was found.";
  if (name === "NotReadableError") return "The microphone is being used by another app.";
  return error instanceof Error ? error.message : "Couldn't start the call.";
}

function rupees(amount: number): string {
  return `₹${amount.toLocaleString("en-IN")}`;
}

export function SarvamCall() {
  const [config, setConfig] = useState<SarvamConfig | null>(null);
  const [configError, setConfigError] = useState<string | null>(null);
  const [store, setStore] = useState<string>("");
  const [language, setLanguage] = useState<"Hindi" | "English">("Hindi");
  const [state, setState] = useState<string>(AgentState.IDLE);
  const [error, setError] = useState<string | null>(null);
  const [lines, setLines] = useState<Line[]>([]);
  const [cart, setCart] = useState<LiveCart | null>(null);
  const agentRef = useRef<ConversationAgent | null>(null);
  const transcriptRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    fetch("/api/sarvam/config")
      .then((r) => r.json())
      .then((data: SarvamConfig) => {
        setConfig(data);
        if (data.stores?.length) setStore(data.stores[0].slug);
      })
      .catch(() => setConfigError("Couldn't reach the backend."));
  }, []);

  // Hang up if the page goes away mid-call.
  useEffect(() => () => void agentRef.current?.stop().catch(() => {}), []);

  useEffect(() => {
    transcriptRef.current?.scrollTo({ top: transcriptRef.current.scrollHeight, behavior: "smooth" });
  }, [lines]);

  const inCall = state !== AgentState.IDLE && state !== AgentState.ERROR;

  // The cart Samvaad's tools are building, shown live while the guest talks.
  useEffect(() => {
    if (!inCall) return;
    const timer = setInterval(async () => {
      const id = agentRef.current?.getInteractionId();
      if (!id) return;
      try {
        const response = await fetch(`/api/sarvam/cart/${encodeURIComponent(id)}`, { cache: "no-store" });
        if (response.ok) setCart(await response.json());
      } catch {
        /* the next tick tries again */
      }
    }, 1500);
    return () => clearInterval(timer);
  }, [inCall]);

  const start = useCallback(async () => {
    if (!config?.enabled || !store) return;
    setError(null);
    setLines([]);
    setCart(null);
    setState(AgentState.CONNECTING);
    try {
      const agent = new ConversationAgent({
        apiKey: "", // the backend adds the key
        baseUrl: "/api/sarvam/",
        audioInterface: new BrowserAudioInterface(16000),
        config: {
          org_id: config.org_id,
          workspace_id: config.workspace_id,
          app_id: config.app_id,
          ...(config.version ? { version: Number(config.version) } : {}),
          user_identifier: `web-${crypto.randomUUID()}`,
          user_identifier_type: "custom",
          interaction_type: InteractionType.CALL,
          input_sample_rate: 16000,
          output_sample_rate: 16000,
          agent_variables: { store_slug: store, channel: "browser", language },
        },
        stateCallback: (next) => setState(next),
        transcriptCallback: async (msg) => {
          const role = String(msg.role) === "user" ? "user" : "bot";
          setLines((prev) => [...prev, { role, text: msg.content }]);
        },
        endCallback: async () => {
          agentRef.current = null;
          setState(AgentState.IDLE);
        },
      });
      agentRef.current = agent;
      await agent.start();
      if (!(await agent.waitForConnect(15))) throw new Error("Sarvam didn't answer in time. Try again.");
    } catch (e) {
      await agentRef.current?.stop().catch(() => {});
      agentRef.current = null;
      setState(AgentState.IDLE);
      setError(micError(e));
    }
  }, [config, store, language]);

  const stop = useCallback(async () => {
    await agentRef.current?.stop().catch(() => {});
    agentRef.current = null;
    setState(AgentState.IDLE);
  }, []);

  const current = config?.stores.find((s) => s.slug === store);
  const total = cart?.cart.reduce((sum, line) => sum + line.price * line.quantity, 0) ?? 0;

  if (configError) return <p className="p-8 text-center text-destructive">{configError}</p>;
  if (!config) return <p className="p-8 text-center text-muted-foreground">Loading…</p>;
  if (!config.enabled) {
    return (
      <p className="mx-auto max-w-md p-8 text-center text-muted-foreground">
        Sarvam calling isn&apos;t set up on the backend yet. Set SARVAM_API_KEY, SARVAM_ORG_ID, SARVAM_WORKSPACE_ID and
        SARVAM_APP_ID (see SARVAM_SETUP.md).
      </p>
    );
  }

  return (
    <div className="mx-auto grid w-full max-w-5xl gap-6 px-4 py-8 md:grid-cols-[1.2fr_1fr]">
      <section className="flex flex-col items-center gap-5 rounded-2xl border bg-card p-6">
        <div className="text-center">
          <p className="text-xs uppercase tracking-widest text-muted-foreground">Powered by Sarthi</p>
          <h1 className="mt-1 text-2xl font-semibold">{current ? `Call ${current.name}` : "Pick a restaurant"}</h1>
        </div>

        <div className="flex flex-wrap justify-center gap-2">
          {config.stores.map((s) => (
            <Button
              key={s.slug}
              size="sm"
              variant={s.slug === store ? "default" : "outline"}
              disabled={inCall}
              onClick={() => setStore(s.slug)}
            >
              {s.name}
            </Button>
          ))}
          {!config.stores.length && (
            <p className="text-sm text-muted-foreground">No restaurants with a phone store yet.</p>
          )}
        </div>

        <AgentOrb className="size-40" state={ORB[state] ?? "idle"} />
        <p className="text-sm text-muted-foreground" aria-live="polite">{STATUS[state] ?? state}</p>

        <div className="flex gap-2">
          {(["Hindi", "English"] as const).map((l) => (
            <Button key={l} size="sm" variant={l === language ? "secondary" : "ghost"} disabled={inCall} onClick={() => setLanguage(l)}>
              {l}
            </Button>
          ))}
        </div>

        {inCall ? (
          <Button size="lg" variant="destructive" className="gap-2" onClick={() => void stop()}>
            <PhoneOff className="size-4" /> End call
          </Button>
        ) : (
          <Button size="lg" className="gap-2" disabled={!store} onClick={() => void start()}>
            <Phone className="size-4" /> Start call
          </Button>
        )}
        {error && <p className="max-w-sm text-center text-sm text-destructive">{error}</p>}

        <div ref={transcriptRef} className="h-56 w-full overflow-y-auto rounded-xl bg-muted/40 p-3 text-sm">
          {lines.length === 0 ? (
            <p className="text-center text-muted-foreground">The conversation shows up here.</p>
          ) : (
            lines.map((line, i) => (
              <p key={i} className={line.role === "user" ? "mb-2 text-right" : "mb-2"}>
                <span
                  className={
                    line.role === "user"
                      ? "inline-block rounded-2xl bg-primary px-3 py-1.5 text-primary-foreground"
                      : "inline-block rounded-2xl bg-background px-3 py-1.5"
                  }
                >
                  {line.text}
                </span>
              </p>
            ))
          )}
        </div>
      </section>

      <aside className="flex flex-col gap-3 rounded-2xl border bg-card p-6">
        <h2 className="flex items-center gap-2 font-semibold">
          <ShoppingBag className="size-4" /> Live order
        </h2>
        {!cart?.cart.length ? (
          <p className="text-sm text-muted-foreground">Items the agent adds appear here as you talk.</p>
        ) : (
          <ul className="flex flex-col gap-2 text-sm">
            {cart.cart.map((line) => (
              <li key={`${line.id}-${line.variant ?? ""}`} className="flex justify-between gap-3">
                <span>
                  {line.quantity} × {line.name}
                  {line.variant ? <span className="text-muted-foreground"> ({line.variant})</span> : null}
                </span>
                <span className="tabular-nums">{rupees(line.price * line.quantity)}</span>
              </li>
            ))}
            <li className="mt-2 flex justify-between border-t pt-2 font-semibold">
              <span>Total</span>
              <span className="tabular-nums">{rupees(total)}</span>
            </li>
          </ul>
        )}
        {cart?.order_placed && (
          <p className="rounded-lg bg-emerald-500/10 p-3 text-sm text-emerald-700 dark:text-emerald-400">
            Order placed. The restaurant and the guest get it on WhatsApp.
          </p>
        )}
      </aside>
    </div>
  );
}
