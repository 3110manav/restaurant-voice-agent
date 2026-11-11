"use client";

import { useCallback, useEffect, useState } from "react";

import { fetchLiveKitToken, type Language } from "@/lib/api";
import { callerDecided, callerPromptEnabled, setCallerPhone } from "@/lib/caller";
import type { Persona } from "@/lib/personas";

export interface CallConnection {
  url: string;
  token: string;
}

/** The "who's calling?" prompt a demo store shows before a call starts (see CallerNumberDialog). */
export interface NumberPrompt {
  open: boolean;
  /** Continue the call as this number (already validated and normalised). */
  submit: (number: string) => void;
  /** Continue the call without a number. */
  skip: () => void;
  /** Close the prompt and do not start the call. */
  cancel: () => void;
}

/**
 * The state of one realtime voice call, kept outside any panel so a call can carry on while the guest
 * browses the menu (the phone layout shows it as a small strip). While a call is live the cart is
 * refreshed every few seconds, because the voice agent runs in a separate process and syncs its cart
 * to the API (see app/voice/cart_sync.py).
 */
export function useRealtimeCall({
  persona,
  sessionId,
  restaurant,
  tableNo,
  language,
  onCartSync,
}: {
  persona: Persona;
  sessionId: string | null;
  restaurant?: string;
  tableNo?: string | null;
  language: Language;
  onCartSync?: () => void;
}) {
  const [connection, setConnection] = useState<CallConnection | null>(null);
  const [isConnecting, setIsConnecting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [waiting, setWaiting] = useState<((proceed: boolean) => void) | null>(null);

  const numberPrompt: NumberPrompt = {
    open: waiting !== null,
    submit: (number) => {
      setCallerPhone(number);
      waiting?.(true);
      setWaiting(null);
    },
    skip: () => {
      setCallerPhone(null);
      waiting?.(true);
      setWaiting(null);
    },
    cancel: () => {
      waiting?.(false);
      setWaiting(null);
    },
  };

  useEffect(() => {
    if (!connection || !onCartSync) return;
    const id = setInterval(onCartSync, 3000);
    return () => clearInterval(id);
  }, [connection, onCartSync]);

  /** Starts the call; resolves true once there is a connection to join. */
  const start = useCallback(async (): Promise<boolean> => {
    if (!sessionId) return false;
    // A demo store asks who is calling, once per browser tab, before the call begins.
    if (callerPromptEnabled() && !callerDecided()) {
      const proceed = await new Promise<boolean>((resolve) => setWaiting(() => resolve));
      if (!proceed) return false;
    }
    setIsConnecting(true);
    setError(null);
    try {
      const res = await fetchLiveKitToken(sessionId, persona.key, { restaurant, tableNo, language });
      if (!res.configured || !res.url || !res.token) {
        setError("Realtime voice isn't available right now.");
        return false;
      }
      setConnection({ url: res.url, token: res.token });
      return true;
    } catch {
      setError("Couldn't start the call.");
      return false;
    } finally {
      setIsConnecting(false);
    }
  }, [language, persona.key, restaurant, sessionId, tableNo]);

  const end = useCallback(() => {
    setConnection(null);
    onCartSync?.(); // one last refresh for anything ordered right at the end
  }, [onCartSync]);

  const fail = useCallback((message: string) => {
    setError(message);
    setConnection(null);
  }, []);

  const clearError = useCallback(() => setError(null), []);

  return { connection, isConnecting, error, start, end, fail, clearError, numberPrompt };
}

export type RealtimeCall = ReturnType<typeof useRealtimeCall>;
