"use client";

import { FloatingChatWidget } from "@/components/chat/floating-chat-widget";
import { MobileOrderingUI } from "@/components/mobile/mobile-ordering-ui";
import { OrderPanel } from "@/components/chat/order-panel";
import { ProductGrid } from "@/components/menu/product-grid";
import { useChatSession } from "@/hooks/use-chat-session";
import { useIsMobile } from "@/hooks/use-is-mobile";
import type { Persona } from "@/lib/personas";

/**
 * Layout for the three "browse and order" personas (online, quick commerce,
 * waiter): a product grid you tap to add to cart, like an e-commerce app,
 * plus a floating chat/voice bubble for anything that's easier to just ask
 * for. Both act on the same cart, held here so the grid's quantity steppers
 * and the chat's own replies always agree.
 */
export function OrderingPage({
  persona,
  restaurant,
  tableNo,
}: {
  persona: Persona;
  /** A restaurant slug: everything (menu, cart, chat, calls) is then scoped to that restaurant. */
  restaurant?: string;
  tableNo?: string | null;
}) {
  const session = useChatSession(persona, { restaurant, tableNo });
  const isMobile = useIsMobile();

  return (
    // The bottom padding on phones keeps the last dishes clear of the pinned bottom bar.
    <div className="flex flex-1 flex-col pb-32 lg:flex-row lg:pb-0">
      <ProductGrid
        persona={persona}
        restaurant={restaurant}
        cart={session.cart}
        onAdd={(itemId, variant) => session.addItemDirect(itemId, 1, variant)}
        onRemove={(itemId, variant) => session.removeItemDirect(itemId, 1, variant)}
      />
      <div className="hidden border-t p-4 lg:block lg:w-[280px] lg:border-t-0 lg:border-l">
        <OrderPanel
          cart={session.cart}
          serviceLog={session.serviceLog}
          serviceLogLabel={persona.hasServiceLog ? persona.serviceLogLabel : null}
        />
      </div>
      {isMobile ? (
        <MobileOrderingUI persona={persona} session={session} />
      ) : (
        <FloatingChatWidget persona={persona} session={session} />
      )}
    </div>
  );
}
