import { notFound } from "next/navigation";

import { ChatWidget } from "@/components/chat/chat-widget";
import { OrderingPage } from "@/components/ordering-page";
import { PERSONAS, getPersonaBySlug } from "@/lib/personas";

export function generateStaticParams() {
  return PERSONAS.map((persona) => ({ slug: persona.slug }));
}

// All four slugs are already enumerated above and prerendered statically,
// so there's no per-request URL data to make "instant": this just silences
// Next's instant-navigation advisory for that known case.
export const instant = false;

export default async function PersonaChatPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const persona = getPersonaBySlug(slug);
  if (!persona) notFound();

  return (
    <div className="flex flex-1 flex-col">
      <div className="border-b px-4 py-3">
        <h1 className="text-lg font-semibold">
          {persona.agentName}{" "}
          <span className="font-normal text-muted-foreground">
            — {persona.vertical}
          </span>
        </h1>
        <p className="text-sm text-muted-foreground">{persona.tagline}</p>
      </div>
      {persona.layout === "grid" ? (
        <OrderingPage persona={persona} />
      ) : (
        <ChatWidget persona={persona} />
      )}
    </div>
  );
}
