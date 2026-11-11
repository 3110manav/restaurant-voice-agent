/** The pre-built demo stores shown on the landing page and printed as QR codes: three restaurants, a kirana and a pharmacy. */
export interface DemoRestaurant {
  slug: string;
  name: string;
  /** "restaurant" (dine-in, opens at a table), or a store that delivers: "kirana" (general store) or "pharmacy". */
  kind: "restaurant" | "kirana" | "pharmacy";
  /** The assistant's name: Kabir for restaurants, Shubh for the kirana, Sehat for the pharmacy. */
  agent: string;
  /** What the store is, shown above its name: a cuisine, or "General store". */
  cuisine: string;
  /** What kind of customer this restaurant stands in for, in the pitch. */
  pitch: string;
  accent: string;
  /** The table the demo QR code opens at (restaurants only; a store has none). */
  table?: string;
  dishes: string;
  highlights: string[];
  /** Things worth saying to the assistant in a demo. */
  tryAsking: string[];
}

export const DEMO_STORES: DemoRestaurant[] = [
  {
    slug: "saffron-table",
    kind: "restaurant",
    agent: "Kabir",
    name: "The Saffron Table",
    cuisine: "Multi-cuisine fine dine",
    pitch: "A big menu a guest can't read end to end.",
    accent: "#b45309",
    table: "9",
    dishes: "105 dishes",
    highlights: ["Indian, Chinese, Japanese, Italian", "Guests ask what to order", "Explains every dish"],
    tryAsking: ["Something creamy and mild", "Is the dragon roll spicy?", "Bring water and the bill"],
  },
  {
    slug: "sarson-da-khet",
    kind: "restaurant",
    agent: "Kabir",
    name: "Sarson Da Khet",
    cuisine: "Punjabi dhaba",
    pitch: "Half and Full portions, and guests who say it their own way.",
    accent: "#d97706",
    table: "3",
    dishes: "38 dishes",
    highlights: ["Half / Full portions", "Understands misspellings", "Suggests what pairs well"],
    tryAsking: ["What is Dal Makhani?", "Add a full buter chiken", "Something cooling for spicy food"],
  },
  {
    slug: "slice-station",
    kind: "restaurant",
    agent: "Kabir",
    name: "Slice Station",
    cuisine: "Pizza chain",
    pitch: "Every pizza in three sizes, and a busy counter.",
    accent: "#dc2626",
    table: "12",
    dishes: "30 dishes",
    highlights: ["Regular / Medium / Large", "Asks which size", "Prices the size you pick"],
    tryAsking: ["I want a margherita", "Make that a large", "What's your spiciest pizza?"],
  },
  {
    slug: "gupta-general-store",
    kind: "kirana",
    agent: "Shubh",
    name: "Gupta General Store",
    cuisine: "General store",
    pitch: "Everyday essentials by phone or chat, delivered to the door.",
    accent: "#1d4ed8",
    dishes: "100 items",
    highlights: ["Asks which pack or brand", "Recognises returning customers", "Takes the address once"],
    tryAsking: ["Two moisturizing soap bars and AA batteries", "Do you have face masks?", "That's all, place the order"],
  },
  {
    slug: "care-plus-medicals",
    kind: "pharmacy",
    agent: "Sehat",
    name: "Care Plus Medicals",
    cuisine: "Pharmacy",
    pitch: "Finds the right medicine from a symptom, and hands prescriptions to the pharmacist.",
    accent: "#0f766e",
    dishes: "44 medicines",
    highlights: ["Searches by symptom", "Flags prescription medicines", "Never gives doses or diagnoses"],
    tryAsking: ["I have a fever and body ache", "Add a Dolo 650 and an ORS", "Add an Azithral 500"],
  },
];
