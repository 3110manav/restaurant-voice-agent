"use client";

import { useEffect, useState, useSyncExternalStore } from "react";

/**
 * Which speech engine the guest talks to: Groq (Whisper hears, Orpheus speaks English) or Sarvam (Saaras hears,
 * Bulbul speaks). Kept in this browser, sent with push-to-talk and with the call request, and offered only when
 * the API allows it (SARTHI_SPEECH_CHOICE, read from /api/health), so a public site can't spend Sarvam credits.
 * Without a pick, the deployment's own default (SARTHI_SPEECH) applies.
 */
export type SpeechStack = "groq" | "sarvam";

const KEY = "sarthi.speech";
const CHANGED = "sarthi:speech";

function isStack(value: unknown): value is SpeechStack {
  return value === "groq" || value === "sarvam";
}

/** The guest's pick, or undefined to leave it to the deployment. */
export function getSpeechChoice(): SpeechStack | undefined {
  if (typeof window === "undefined") return undefined;
  try {
    const value = window.localStorage.getItem(KEY);
    return isStack(value) ? value : undefined;
  } catch {
    return undefined;
  }
}

export function setSpeechChoice(stack: SpeechStack) {
  try {
    window.localStorage.setItem(KEY, stack);
  } catch {
    // private mode: the pick lasts until the page is reloaded
    memory = stack;
  }
  window.dispatchEvent(new Event(CHANGED));
}

let memory: SpeechStack | undefined;

function current(): SpeechStack | undefined {
  return getSpeechChoice() ?? memory;
}

function subscribe(callback: () => void) {
  window.addEventListener(CHANGED, callback);
  window.addEventListener("storage", callback);
  return () => {
    window.removeEventListener(CHANGED, callback);
    window.removeEventListener("storage", callback);
  };
}

interface Availability {
  choice: boolean;
  fallback: SpeechStack;
}

let availability: Promise<Availability> | null = null;

/** Asks the API once whether choosing is allowed and what its default is. */
function loadAvailability(): Promise<Availability> {
  availability ??= fetch("/api/health", { cache: "no-store" })
    .then((res) => res.json())
    .then((data) => ({ choice: data?.speech_choice === true, fallback: isStack(data?.speech) ? data.speech : "groq" }) as Availability)
    .catch(() => ({ choice: false, fallback: "groq" }) as Availability);
  return availability;
}

/** The engine in use, whether the switch should be shown, and how to change it. */
export function useSpeechChoice() {
  const picked = useSyncExternalStore(subscribe, current, () => undefined);
  const [info, setInfo] = useState<Availability | null>(null);

  useEffect(() => {
    let cancelled = false;
    void loadAvailability().then((a) => !cancelled && setInfo(a));
    return () => {
      cancelled = true;
    };
  }, []);

  return {
    available: info?.choice === true,
    value: picked ?? info?.fallback ?? "groq",
    set: setSpeechChoice,
  };
}
