"use client";

import { useEffect, useRef, useState } from "react";
import { Mic, Phone, Send, Square } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { LanguageToggle } from "@/components/language-toggle";
import { RealtimeCall } from "@/components/voice/realtime-call";
import type { ChatSession } from "@/hooks/use-chat-session";
import type { Persona } from "@/lib/personas";
import { cn } from "@/lib/utils";

export function ChatPanel({
  persona,
  session,
  placeholder,
  scrollHeight = "60vh",
  onRequestCall,
  callBusy = false,
}: {
  persona: Persona;
  session: ChatSession;
  placeholder: string;
  scrollHeight?: string;
  /** When given, the phone button asks the parent to handle the call (the phone layout shows it as a
   * strip that outlives this panel) instead of showing the call inside the panel. */
  onRequestCall?: () => void;
  /** A call is already live, so the phone button is disabled. */
  callBusy?: boolean;
}) {
  const {
    sessionId,
    restaurant,
    tableNo,
    language,
    setLanguage,
    messages,
    isSending,
    isRecording,
    sendText,
    toggleRecording,
    refreshCart,
  } = session;
  const [input, setInput] = useState("");
  const [callActive, setCallActive] = useState(false);
  const scrollEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  function handleSend() {
    if (!input.trim()) return;
    void sendText(input);
    setInput("");
  }

  if (callActive) {
    return (
      <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-lg border bg-card">
        <RealtimeCall
          persona={persona}
          sessionId={sessionId}
          restaurant={restaurant}
          tableNo={tableNo}
          language={language}
          onLanguageChange={setLanguage}
          onEnd={() => setCallActive(false)}
          onCartSync={refreshCart}
        />
      </div>
    );
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-lg border bg-card">
      <div className="flex items-center justify-between gap-2 border-b px-3 py-2">
        <span className="text-xs text-muted-foreground">Talking to {persona.agentName}</span>
        <LanguageToggle value={language} onChange={setLanguage} />
      </div>
      <ScrollArea className="min-h-0 flex-1 p-4" style={{ height: scrollHeight }}>
        <div className="flex flex-col gap-3">
          {messages.map((m, i) => (
            <div
              key={i}
              className={cn(
                "max-w-[80%] rounded-lg px-3 py-2 text-sm",
                m.role === "user" && "ml-auto bg-primary text-primary-foreground",
                m.role === "agent" && "bg-muted",
                m.role === "error" &&
                  "border border-destructive/50 bg-destructive/10 text-destructive"
              )}
            >
              {m.text}
            </div>
          ))}
          <div ref={scrollEndRef} />
        </div>
      </ScrollArea>
      <div className="flex gap-2 border-t p-3">
        <Button
          type="button"
          variant="outline"
          size="icon"
          onClick={() => (onRequestCall ? onRequestCall() : setCallActive(true))}
          disabled={!sessionId || callBusy}
          aria-label={`Start a realtime call with ${persona.agentName}`}
          title="Realtime voice call"
        >
          <Phone className="size-4" />
        </Button>
        <Button
          type="button"
          variant={isRecording ? "destructive" : "outline"}
          size="icon"
          onClick={toggleRecording}
          disabled={!sessionId}
          aria-label={isRecording ? "Stop recording" : "Record a voice message"}
          title="Push-to-talk"
        >
          {isRecording ? <Square className="size-4" /> : <Mic className="size-4" />}
        </Button>
        <Input
          value={input}
          placeholder={isRecording ? "Listening..." : placeholder}
          disabled={isSending || !sessionId || isRecording}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") handleSend();
          }}
        />
        <Button onClick={handleSend} disabled={isSending || !sessionId || !input.trim()}>
          <Send className="size-4" />
        </Button>
      </div>
    </div>
  );
}
