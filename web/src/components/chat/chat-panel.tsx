"use client";

import { useEffect, useRef, useState } from "react";
import { Mic, Send, Square } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import type { ChatSession } from "@/hooks/use-chat-session";
import { cn } from "@/lib/utils";

export function ChatPanel({
  session,
  placeholder,
  scrollHeight = "60vh",
}: {
  session: ChatSession;
  placeholder: string;
  scrollHeight?: string;
}) {
  const { sessionId, messages, isSending, isRecording, sendText, toggleRecording } = session;
  const [input, setInput] = useState("");
  const scrollEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  function handleSend() {
    if (!input.trim()) return;
    void sendText(input);
    setInput("");
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-lg border bg-card">
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
          variant={isRecording ? "destructive" : "outline"}
          size="icon"
          onClick={toggleRecording}
          disabled={!sessionId}
          aria-label={isRecording ? "Stop recording" : "Record a voice message"}
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
