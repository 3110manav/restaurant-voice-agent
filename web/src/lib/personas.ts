export type PersonaKey = "online" | "quick_commerce" | "waiter" | "hotel";

export interface Persona {
  /** URL segment under /chat/[slug] */
  slug: string;
  /** Value sent to the backend's `persona` field. */
  key: PersonaKey;
  /** The agent's own name, as it introduces itself. */
  agentName: string;
  /** Short vertical label shown in the sidebar/nav. */
  vertical: string;
  tagline: string;
  placeholder: string;
  /** Whether this persona raises ambient service requests (not just cart orders). */
  hasServiceLog: boolean;
  serviceLogLabel: string;
  /**
   * "grid" — browse a product grid (like a delivery/e-commerce app) with a
   * floating chat/voice bubble for anything else.
   * "direct-chat" — chat/voice is the whole page, no browsable catalog.
   */
  layout: "grid" | "direct-chat";
}

export const PERSONAS: Persona[] = [
  {
    slug: "online",
    key: "online",
    agentName: "Zaika",
    vertical: "Online ordering",
    tagline: "Delivery-app style ordering, like Swiggy or Zomato.",
    placeholder: "Add two paneer tikka and a garlic naan...",
    hasServiceLog: false,
    serviceLogLabel: "",
    layout: "grid",
  },
  {
    slug: "quick-commerce",
    key: "quick_commerce",
    agentName: "Fatafat",
    vertical: "Quick commerce",
    tagline: "Everyday essentials in minutes, like Instamart or Blinkit.",
    placeholder: "Add shampoo and a pack of batteries, quick...",
    hasServiceLog: false,
    serviceLogLabel: "",
    layout: "grid",
  },
  {
    slug: "waiter",
    key: "waiter",
    agentName: "Khidmat",
    vertical: "Restaurant",
    tagline: "A voice waiter at your table — order, and ask for anything else.",
    placeholder: "Can you bring me a glass of water?",
    hasServiceLog: true,
    serviceLogLabel: "Service requests",
    layout: "grid",
  },
  {
    slug: "hotel",
    key: "hotel",
    agentName: "Swagat",
    vertical: "Hotel reception",
    tagline: "Room service, housekeeping, and front-desk requests.",
    placeholder: "Can I get extra towels for room 204?",
    hasServiceLog: true,
    serviceLogLabel: "Front-desk requests",
    layout: "direct-chat",
  },
];

export function getPersonaBySlug(slug: string): Persona | undefined {
  return PERSONAS.find((p) => p.slug === slug);
}
