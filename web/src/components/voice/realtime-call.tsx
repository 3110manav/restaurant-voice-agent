"use client";

import { useEffect, useState } from "react";
import { LiveKitRoom, RoomAudioRenderer } from "@livekit/components-react";
import { MediaDeviceFailure } from "livekit-client";
import { Phone } from "lucide-react";

import { Button } from "@/components/ui/button";
import { RealtimeCallPanel } from "@/components/voice/realtime-call-panel";
import { fetchLiveKitToken } from "@/lib/api";
import type { Persona } from "@/lib/personas";

import "@livekit/components-styles";

/**
 * Realtime, interruptible voice — speak naturally, barge in mid-sentence —
 * as an alternative to the push-to-talk mic in ChatPanel. Needs the
 * sarthi-voice LiveKit worker running separately (app/voice/livekit_worker.py);
 * if LIVEKIT_* isn't configured on the backend, starting a call just shows
 * an error rather than breaking anything else.
 */
export function RealtimeCall({
  persona,
  sessionId,
  onEnd,
  onCartSync,
}: {
  persona: Persona;
  sessionId: string | null;
  onEnd: () => void;
  /** Called periodically while connected, and once more on disconnect, so
   * the cart ordered by voice (via the separate LiveKit worker process —
   * see app/voice/cart_sync.py) shows up in the UI's own cart state. */
  onCartSync?: () => void;
}) {
  const [connection, setConnection] = useState<{ url: string; token: string } | null>(null);
  const [isConnecting, setIsConnecting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // The worker pushes its cart after every turn, so a few seconds of lag is
  // fine — poll gently rather than on every render.
  useEffect(() => {
    if (!connection || !onCartSync) return;
    const id = setInterval(onCartSync, 3000);
    return () => clearInterval(id);
  }, [connection, onCartSync]);

  async function startCall() {
    if (!sessionId) return;
    setIsConnecting(true);
    setError(null);
    try {
      const res = await fetchLiveKitToken(sessionId, persona.key);
      if (!res.configured || !res.url || !res.token) {
        setError("Realtime voice isn't available right now.");
        return;
      }
      setConnection({ url: res.url, token: res.token });
    } catch {
      setError("Couldn't start the call.");
    } finally {
      setIsConnecting(false);
    }
  }

  if (!connection) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-3 p-6">
        <Button onClick={startCall} disabled={isConnecting || !sessionId} className="gap-2">
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
      onDisconnected={() => {
        setConnection(null);
        onCartSync?.();
      }}
      onError={() => {
        setError("The call ended unexpectedly.");
        setConnection(null);
      }}
      onMediaDeviceFailure={(failure) => {
        setError(
          failure === MediaDeviceFailure.PermissionDenied
            ? "Microphone access was denied — allow it in your browser and try again."
            : "Couldn't access your microphone."
        );
        setConnection(null);
      }}
    >
      <RealtimeCallPanel persona={persona} onEnd={() => setConnection(null)} />
      <RoomAudioRenderer />
    </LiveKitRoom>
  );
}
