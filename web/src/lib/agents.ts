import type { LucideIcon } from "lucide-react";
import { Pill, Scissors, ShoppingBasket, Sparkles, UtensilsCrossed } from "lucide-react";

import { DEMO_STORES, type DemoRestaurant } from "@/lib/demo";

/**
 * The bouquet of Sarthi agents: one per kind of local counter, each solving a different problem. The first three can
 * be tried now, on the demo stores in lib/demo.ts; the rest are shown as what is coming.
 */
export interface Agent {
  name: string;
  /** Who it works for: "Restaurants and cafés". */
  works: string;
  /** The problem that business has, in a sentence. */
  problem: string;
  does: string[];
  accent: string;
  icon: LucideIcon;
  /** Demo stores of this kind, in the order shown; empty for an agent that isn't built yet. */
  stores: DemoRestaurant[];
  status: "demo" | "soon";
}

const storesOf = (kind: DemoRestaurant["kind"]) => DEMO_STORES.filter((s) => s.kind === kind);

export const AGENTS: Agent[] = [
  {
    name: "Kabir",
    works: "Restaurants and cafés",
    problem: "Guests can't read a big menu, and staff can't be at every table.",
    does: [
      "Explains dishes and suggests what goes well together",
      "Takes the order by voice or text, with sizes and portions",
      "Handles water, the bill and calling a human over",
    ],
    accent: "#b45309",
    icon: UtensilsCrossed,
    stores: storesOf("restaurant"),
    status: "demo",
  },
  {
    name: "Shubh",
    works: "Kirana and general stores",
    problem: "Phone orders for everyday items keep someone tied to the counter.",
    does: [
      "Takes a shopping list and asks only which pack or brand",
      "Remembers returning customers and where they live",
      "Passes the order to the shop to deliver",
    ],
    accent: "#1d4ed8",
    icon: ShoppingBasket,
    stores: storesOf("kirana"),
    status: "demo",
  },
  {
    name: "Sehat",
    works: "Pharmacies",
    problem: "Customers describe symptoms, not medicine names, and prescriptions need a pharmacist.",
    does: [
      "Finds over-the-counter options from a symptom",
      "Never gives doses or diagnoses: that goes to the pharmacist",
      "Holds prescription medicines until the pharmacist has checked them",
    ],
    accent: "#0f766e",
    icon: Pill,
    stores: storesOf("pharmacy"),
    status: "demo",
  },
  {
    name: "Sakhi",
    works: "Salons and parlours",
    problem: "Appointments are booked by phone, between customers.",
    does: ["Books appointments by voice", "Rebooks regulars", "Fills empty slots"],
    accent: "#be185d",
    icon: Scissors,
    stores: [],
    status: "soon",
  },
  {
    name: "Arjun",
    works: "Any local business",
    problem: "Any small business that runs on phone calls has calls it can't pick up.",
    does: ["Answers in English or Hindi", "Remembers every customer", "Tells the owner what to do next"],
    accent: "#6d28d9",
    icon: Sparkles,
    stores: [],
    status: "soon",
  },
];

/** Where "Try Kabir" should go: the first demo store, opened the way a customer would (a restaurant at its table). */
export function tryLink(agent: Agent): string | null {
  const store = agent.stores[0];
  if (!store) return null;
  return store.table ? `/r/${store.slug}?table=${store.table}` : `/r/${store.slug}`;
}
