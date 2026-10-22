"use client";

import { useEffect, useRef } from "react";
import { BarVisualizer, useRoomContext, useTranscriptions, useVoiceAssistant } from "@livekit/components-react";
import { PhoneOff } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { Persona } from "@/lib/personas";
import { cn } from "@/lib/utils";

const STATE_LABEL: Record<string, string> = {
  connecting: "Connecting…",
  "pre-connect-buffering": "Connecting…",
  initializing: "Connecting…",
  idle: "Ready",
  listening: "Listening…",
  thinking: "Thinking…",
  speaking: "Speaking…",
  disconnected: "Disconnected",
  failed: "Connection failed",
};

export function RealtimeCallPanel({
  persona,
  onEnd,
}: {
  persona: Persona;
  onEnd: () => void;
}) {
  const { state, audioTrack } = useVoiceAssistant();
  const transcriptions = useTranscriptions();
  const room = useRoomContext();
  const scrollEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [transcriptions]);

  function hangUp() {
    room.disconnect();
    onEnd();
  }

  const speaking = state === "speaking";
  const listening = state === "listening";

  return (
    <div className="flex min-h-0 flex-1 flex-col items-center justify-between gap-4 p-6">
      <div className="flex flex-col items-center gap-1">
        <p className="text-sm font-semibold">{persona.agentName}</p>
        <p
          className={cn(
            "text-xs transition-colors",
            speaking && "text-primary",
            listening && "text-muted-foreground",
            !speaking && !listening && "text-muted-foreground"
          )}
        >
          {STATE_LABEL[state] ?? state}
        </p>
      </div>

      <div
        className={cn(
          "relative flex size-32 shrink-0 items-center justify-center rounded-full border-2 transition-all duration-300",
          speaking && "border-primary shadow-[0_0_30px_var(--color-primary)]",
          listening && "border-primary/50",
          !speaking && !listening && "border-border"
        )}
      >
        <div
          style={
            {
              "--lk-fg": "var(--color-primary)",
              "--lk-va-bar-bg": "color-mix(in oklch, var(--color-primary) 20%, transparent)",
              "--lk-bg": "transparent",
            } as React.CSSProperties
          }
          className="flex h-16 w-24 items-center justify-center"
        >
          <BarVisualizer
            state={state}
            track={audioTrack}
            barCount={5}
            options={{ minHeight: 15, maxHeight: 100 }}
          />
        </div>
      </div>

      <div className="flex min-h-0 w-full flex-1 flex-col gap-1 overflow-y-auto text-xs">
        {transcriptions.map((t, i) => {
          const isLocal = t.participantInfo.identity === room.localParticipant.identity;
          return (
            <p
              key={`${t.streamInfo.id}-${i}`}
              className={cn(
                "max-w-[85%] rounded-lg px-2 py-1",
                isLocal ? "self-end bg-primary/10" : "self-start bg-muted"
              )}
            >
              {t.text}
            </p>
          );
        })}
        <div ref={scrollEndRef} />
      </div>

      <Button
        variant="destructive"
        size="icon"
        className="size-12 rounded-full"
        onClick={hangUp}
        aria-label="End call"
      >
        <PhoneOff className="size-5" />
      </Button>
    </div>
  );
}
