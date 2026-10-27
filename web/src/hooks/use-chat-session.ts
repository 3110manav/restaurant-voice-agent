"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  addToCart as apiAddToCart,
  removeFromCart as apiRemoveFromCart,
  fetchCart,
  sendChatMessage,
  sendVoiceMessage,
  type CartLine,
  type Language,
  type RestaurantContext,
  type ServiceLogEntry,
} from "@/lib/api";
import type { Persona } from "@/lib/personas";

export interface ChatMessage {
  role: "user" | "agent" | "error";
  text: string;
}

function getOrCreateSessionId(scope: string): string {
  const storageKey = `sarthi:session:${scope}`;
  let sessionId = window.sessionStorage.getItem(storageKey);
  if (!sessionId) {
    sessionId = crypto.randomUUID();
    window.sessionStorage.setItem(storageKey, sessionId);
  }
  return sessionId;
}

function playAudioBase64(base64Wav: string) {
  const audio = new Audio(`data:audio/wav;base64,${base64Wav}`);
  audio.play().catch(() => {
    // Autoplay can be blocked before the user has interacted with the page —
    // the reply text is already shown, so silently skipping playback is fine.
  });
}

/**
 * `ctx` puts the conversation inside one restaurant (and table): every call is
 * then scoped to that restaurant's menu, and the guest gets a separate session
 * and cart per restaurant. Without it this is one of the four legacy personas.
 */
export function useChatSession(persona: Persona, ctx: RestaurantContext = {}) {
  const { restaurant, tableNo } = ctx;
  const scope = restaurant ?? persona.slug;
  // crypto.randomUUID() / sessionStorage are only read after mount, so this
  // never runs during prerendering (Cache Components flags it as unstable
  // otherwise — see https://nextjs.org/docs/messages/blocking-prerender-crypto-client).
  const [sessionId, setSessionId] = useState<string | null>(null);
  useEffect(() => {
    setSessionId(getOrCreateSessionId(scope));
  }, [scope]);

  const [messages, setMessages] = useState<ChatMessage[]>([
    { role: "agent", text: `Namaste, I'm ${persona.agentName}. ${persona.tagline}` },
  ]);
  const [cart, setCart] = useState<CartLine[]>([]);
  const [serviceLog, setServiceLog] = useState<ServiceLogEntry[]>([]);
  const [isSending, setIsSending] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  // The English / हिन्दी toggle. It travels with every message and call, so the agent, the speech
  // recognition and the voice all follow it, instead of guessing from what was just said.
  const [language, setLanguageState] = useState<Language>("en");

  const setLanguage = useCallback(
    (next: Language) => {
      if (next === language) return;
      setLanguageState(next);
      setMessages((prev) => [
        ...prev,
        {
          role: "agent",
          text: next === "hi" ? "ठीक है, अब हिंदी में बात करते हैं।" : "Sure, let's continue in English.",
        },
      ]);
    },
    [language]
  );

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  const pushError = useCallback((err: unknown) => {
    setMessages((prev) => [
      ...prev,
      { role: "error", text: err instanceof Error ? err.message : "Something went wrong." },
    ]);
  }, []);

  const sendText = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || isSending || !sessionId) return;

      setMessages((prev) => [...prev, { role: "user", text: trimmed }]);
      setIsSending(true);
      try {
        const response = await sendChatMessage(sessionId, persona.key, trimmed, { restaurant, tableNo, language });
        setMessages((prev) => [...prev, { role: "agent", text: response.reply }]);
        setCart(response.cart);
        setServiceLog(response.service_log);
      } catch (err) {
        pushError(err);
      } finally {
        setIsSending(false);
      }
    },
    [isSending, language, persona.key, pushError, restaurant, sessionId, tableNo]
  );

  const sendVoice = useCallback(
    async (audio: Blob) => {
      if (isSending || !sessionId) return;
      setIsSending(true);
      try {
        const response = await sendVoiceMessage(sessionId, persona.key, audio, { restaurant, tableNo, language });
        if (!response.transcript) {
          setMessages((prev) => [
            ...prev,
            { role: "error", text: "Didn't catch that — try again." },
          ]);
          return;
        }
        setMessages((prev) => [
          ...prev,
          { role: "user", text: response.transcript },
          { role: "agent", text: response.reply },
        ]);
        setCart(response.cart);
        setServiceLog(response.service_log);
        if (response.reply_audio_wav_base64) {
          playAudioBase64(response.reply_audio_wav_base64);
        }
      } catch (err) {
        pushError(err);
      } finally {
        setIsSending(false);
      }
    },
    [isSending, language, persona.key, pushError, restaurant, sessionId, tableNo]
  );

  const startRecording = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      chunksRef.current = [];
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };
      recorder.onstop = () => {
        stream.getTracks().forEach((track) => track.stop());
        const blob = new Blob(chunksRef.current, { type: recorder.mimeType });
        void sendVoice(blob);
      };
      recorder.start();
      mediaRecorderRef.current = recorder;
      setIsRecording(true);
    } catch {
      pushError(new Error("Couldn't access the microphone — check browser permissions."));
    }
  }, [pushError, sendVoice]);

  const stopRecording = useCallback(() => {
    mediaRecorderRef.current?.stop();
    mediaRecorderRef.current = null;
    setIsRecording(false);
  }, []);

  const toggleRecording = useCallback(() => {
    if (isRecording) stopRecording();
    else void startRecording();
  }, [isRecording, startRecording, stopRecording]);

  // Direct, non-agentic cart mutation for UI actions (tapping "Add" on a
  // product card) — see app/main.py's /cart/add for why this bypasses chat.
  const addItemDirect = useCallback(
    async (itemId: string, quantity = 1, variant?: string) => {
      if (!sessionId) return;
      try {
        const response = await apiAddToCart(sessionId, persona.key, itemId, quantity, {
          restaurant,
          variant,
        });
        setCart(response.cart);
      } catch (err) {
        pushError(err);
      }
    },
    [persona.key, pushError, restaurant, sessionId]
  );

  const removeItemDirect = useCallback(
    async (itemId: string, quantity = 1, variant?: string) => {
      if (!sessionId) return;
      try {
        const response = await apiRemoveFromCart(sessionId, persona.key, itemId, quantity, {
          restaurant,
          variant,
        });
        setCart(response.cart);
      } catch (err) {
        pushError(err);
      }
    },
    [persona.key, pushError, restaurant, sessionId]
  );

  // Picks up cart/service_log changes made outside this hook's own calls —
  // namely a realtime voice call, which runs through the separate LiveKit
  // worker process and syncs its cart to the main API (see app/voice/
  // cart_sync.py) rather than through sendText/sendVoice here.
  const refreshCart = useCallback(async () => {
    if (!sessionId) return;
    try {
      const response = await fetchCart(sessionId, persona.key, restaurant);
      setCart(response.cart);
      setServiceLog(response.service_log);
    } catch {
      // best-effort poll; a transient failure just means we try again next tick
    }
  }, [persona.key, restaurant, sessionId]);

  return {
    sessionId,
    restaurant,
    tableNo,
    language,
    setLanguage,
    messages,
    cart,
    serviceLog,
    isSending,
    isRecording,
    sendText,
    toggleRecording,
    addItemDirect,
    removeItemDirect,
    refreshCart,
  };
}

export type ChatSession = ReturnType<typeof useChatSession>;
