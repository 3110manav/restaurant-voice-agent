"use client";

import { useState } from "react";
import { MessageCircle, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ChatPanel } from "@/components/chat/chat-panel";
import type { ChatSession } from "@/hooks/use-chat-session";
import type { Persona } from "@/lib/personas";

export function FloatingChatWidget({
  persona,
  session,
}: {
  persona: Persona;
  session: ChatSession;
}) {
  const [open, setOpen] = useState(false);

  if (!open) {
    return (
      <Button
        onClick={() => setOpen(true)}
        className="fixed right-6 bottom-6 z-50 size-14 rounded-full shadow-lg"
        aria-label={`Chat with ${persona.agentName}`}
      >
        <MessageCircle className="size-6" />
      </Button>
    );
  }

  return (
    <div className="fixed right-6 bottom-6 z-50 flex h-[32rem] w-[22rem] max-w-[calc(100vw-3rem)] flex-col overflow-hidden rounded-xl border bg-background shadow-2xl">
      <div className="flex items-center justify-between border-b px-4 py-3">
        <div>
          <p className="text-sm font-semibold">{persona.agentName}</p>
          <p className="text-xs text-muted-foreground">{persona.vertical}</p>
        </div>
        <Button
          variant="ghost"
          size="icon"
          onClick={() => setOpen(false)}
          aria-label="Close chat"
        >
          <X className="size-4" />
        </Button>
      </div>
      <ChatPanel session={session} placeholder={persona.placeholder} scrollHeight="100%" />
    </div>
  );
}
