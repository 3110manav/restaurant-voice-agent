"use client";

import { FloatingChatWidget } from "@/components/chat/floating-chat-widget";
import { OrderPanel } from "@/components/chat/order-panel";
import { ProductGrid } from "@/components/menu/product-grid";
import { useChatSession } from "@/hooks/use-chat-session";
import type { Persona } from "@/lib/personas";

/**
 * Layout for the three "browse and order" personas (online, quick commerce,
 * waiter): a product grid you tap to add to cart, like an e-commerce app,
 * plus a floating chat/voice bubble for anything that's easier to just ask
 * for. Both act on the same cart, held here so the grid's quantity steppers
 * and the chat's own replies always agree.
 */
export function OrderingPage({ persona }: { persona: Persona }) {
  const session = useChatSession(persona);

  return (
    <div className="flex flex-1 flex-col lg:flex-row">
      <ProductGrid
        persona={persona}
        cart={session.cart}
        onAdd={(itemId) => session.addItemDirect(itemId)}
        onRemove={(itemId) => session.removeItemDirect(itemId)}
      />
      <div className="border-t p-4 lg:w-[280px] lg:border-t-0 lg:border-l">
        <OrderPanel
          cart={session.cart}
          serviceLog={session.serviceLog}
          serviceLogLabel={persona.hasServiceLog ? persona.serviceLogLabel : null}
        />
      </div>
      <FloatingChatWidget persona={persona} session={session} />
    </div>
  );
}
