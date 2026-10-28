"use client";

import { LiveKitRoom, RoomAudioRenderer } from "@livekit/components-react";
import { MediaDeviceFailure } from "livekit-client";
import { Phone } from "lucide-react";

import { LanguageToggle } from "@/components/language-toggle";
import { Button } from "@/components/ui/button";
import { AgentOrb } from "@/components/voice/agent-orb";
import { RealtimeCallPanel } from "@/components/voice/realtime-call-panel";
import { useRealtimeCall } from "@/hooks/use-realtime-call";
import type { Language } from "@/lib/api";
import type { Persona } from "@/lib/personas";

import "@livekit/components-styles";

/**
 * Realtime, interruptible voice — speak naturally, barge in mid-sentence — as an alternative to the
 * push-to-talk mic in ChatPanel (the desktop layout; phones use the call strip instead). Needs the
 * sarthi-voice LiveKit worker running separately (app/voice/livekit_worker.py); if LIVEKIT_* isn't
 * configured on the backend, starting a call just shows an error rather than breaking anything else.
 */
export function RealtimeCall({
  persona,
  sessionId,
  restaurant,
  tableNo,
  language,
  onLanguageChange,
  onEnd,
  onCartSync,
}: {
  persona: Persona;
  sessionId: string | null;
  /** Which restaurant (and table) the call is for; absent for the legacy personas. */
  restaurant?: string;
  tableNo?: string | null;
  /** The call's language is fixed when it starts; to change it, end the call and pick again. */
  language: Language;
  onLanguageChange: (next: Language) => void;
  onEnd: () => void;
  /** Called periodically while connected, and once more on disconnect, so the cart ordered by voice
   * shows up in the UI's own cart state. */
  onCartSync?: () => void;
}) {
  const call = useRealtimeCall({ persona, sessionId, restaurant, tableNo, language, onCartSync });
  const { connection, isConnecting, error } = call;

  if (!connection) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-4 p-6">
        <AgentOrb className="size-28" state={isConnecting ? "connecting" : "idle"} />
        <LanguageToggle value={language} onChange={onLanguageChange} disabled={isConnecting} />
        <Button onClick={() => void call.start()} disabled={isConnecting || !sessionId} className="gap-2">
          <Phone className="size-4" />
          {isConnecting ? "Connecting…" : `Call ${persona.agentName}`}
        </Button>
        {error && <p className="text-xs text-destructive">{error}</p>}
        <button
          type="button"
          onClick={onEnd}
          className="text-xs text-muted-foreground underline-offset-4 hover:underline"
        >
          Back to text chat
        </button>
      </div>
    );
  }

  return (
    <LiveKitRoom
      serverUrl={connection.url}
      token={connection.token}
      audio
      connect
      className="flex min-h-0 flex-1 flex-col"
      onDisconnected={call.end}
      onError={() => call.fail("The call ended unexpectedly.")}
      onMediaDeviceFailure={(failure) =>
        call.fail(
          failure === MediaDeviceFailure.PermissionDenied
            ? "Microphone access was denied — allow it in your browser and try again."
            : "Couldn't access your microphone."
        )
      }
    >
      <RealtimeCallPanel persona={persona} onEnd={call.end} />
      <RoomAudioRenderer />
    </LiveKitRoom>
  );
}
