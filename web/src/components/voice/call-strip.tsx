"use client";

import { LiveKitRoom, RoomAudioRenderer, useLocalParticipant, useRoomContext, useTranscriptions, useVoiceAssistant } from "@livekit/components-react";
import { MediaDeviceFailure } from "livekit-client";
import { Mic, MicOff, PhoneOff } from "lucide-react";

import { AgentOrb, orbStateFor, type OrbState } from "@/components/voice/agent-orb";
import type { CallConnection } from "@/hooks/use-realtime-call";
import { cn } from "@/lib/utils";

import "@livekit/components-styles";

const STATE_LABEL: Record<OrbState, string> = {
  connecting: "Connecting…",
  idle: "Ready",
  listening: "Listening…",
  thinking: "Thinking…",
  speaking: "Speaking…",
};

/** What a live call looks like on a phone: a slim strip above the bottom bar, so the menu stays usable. */
export function CallStripView({
  agentName,
  state,
  line,
  muted,
  onToggleMute,
  onEnd,
  agentTrack,
  userTrack,
}: {
  agentName: string;
  state: OrbState;
  /** The latest thing said, shown under the name. */
  line?: string;
  muted: boolean;
  onToggleMute: () => void;
  onEnd: () => void;
  agentTrack?: MediaStreamTrack | null;
  userTrack?: MediaStreamTrack | null;
}) {
  return (
    <div className="flex items-center gap-3 rounded-2xl border bg-background/95 p-2 pr-2.5 shadow-lg backdrop-blur">
      <AgentOrb className="size-11 shrink-0" state={state} agentTrack={agentTrack} userTrack={userTrack} />
      <div className="flex min-w-0 flex-1 flex-col leading-tight">
        <p className="text-sm font-semibold">
          {agentName} <span className={cn("font-normal", state === "speaking" ? "text-primary" : "text-muted-foreground")}>· {STATE_LABEL[state]}</span>
        </p>
        <p className="truncate text-xs text-muted-foreground">{line || "Go ahead, browse the menu while we talk."}</p>
      </div>
      <button
        type="button"
        onClick={onToggleMute}
        aria-label={muted ? "Unmute microphone" : "Mute microphone"}
        aria-pressed={muted}
        className={cn(
          "flex size-10 shrink-0 items-center justify-center rounded-full border transition-colors",
          muted ? "bg-muted text-muted-foreground" : "bg-background"
        )}
      >
        {muted ? <MicOff className="size-4" /> : <Mic className="size-4" />}
      </button>
      <button
        type="button"
        onClick={onEnd}
        aria-label="End call"
        className="flex size-10 shrink-0 items-center justify-center rounded-full bg-destructive text-white"
      >
        <PhoneOff className="size-4" />
      </button>
    </div>
  );
}

function ConnectedStrip({ agentName, onEnd }: { agentName: string; onEnd: () => void }) {
  const { state, audioTrack } = useVoiceAssistant();
  const { microphoneTrack, localParticipant, isMicrophoneEnabled } = useLocalParticipant();
  const transcriptions = useTranscriptions();
  const room = useRoomContext();

  return (
    <CallStripView
      agentName={agentName}
      state={orbStateFor(state)}
      line={transcriptions.at(-1)?.text}
      muted={!isMicrophoneEnabled}
      onToggleMute={() => void localParticipant.setMicrophoneEnabled(!isMicrophoneEnabled)}
      onEnd={() => {
        room.disconnect();
        onEnd();
      }}
      agentTrack={audioTrack?.publication?.track?.mediaStreamTrack}
      userTrack={microphoneTrack?.track?.mediaStreamTrack}
    />
  );
}

/** Joins the call and shows the strip. Stays mounted for as long as the call lasts. */
export function CallStrip({
  agentName,
  connection,
  onEnd,
  onFail,
}: {
  agentName: string;
  connection: CallConnection;
  onEnd: () => void;
  onFail: (message: string) => void;
}) {
  return (
    <LiveKitRoom
      serverUrl={connection.url}
      token={connection.token}
      audio
      connect
      className="contents"
      onDisconnected={onEnd}
      onError={() => onFail("The call ended unexpectedly.")}
      onMediaDeviceFailure={(failure) =>
        onFail(
          failure === MediaDeviceFailure.PermissionDenied
            ? "Microphone access was denied. Allow it in your browser and try again."
            : "Couldn't access your microphone."
        )
      }
    >
      <ConnectedStrip agentName={agentName} onEnd={onEnd} />
      <RoomAudioRenderer />
    </LiveKitRoom>
  );
}
