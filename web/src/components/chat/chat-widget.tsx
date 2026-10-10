"use client";

import { ChatPanel } from "@/components/chat/chat-panel";
import { OrderPanel } from "@/components/chat/order-panel";
import { useChatSession } from "@/hooks/use-chat-session";
import type { Persona } from "@/lib/personas";

export function ChatWidget({ persona }: { persona: Persona }) {
  const session = useChatSession(persona);

  return (
    <div className="grid flex-1 grid-cols-1 gap-4 p-4 lg:grid-cols-[1fr_280px]">
      <ChatPanel session={session} placeholder={persona.placeholder} />
      <OrderPanel
        cart={session.cart}
        serviceLog={session.serviceLog}
        serviceLogLabel={persona.hasServiceLog ? persona.serviceLogLabel : null}
      />
    </div>
  );
}
