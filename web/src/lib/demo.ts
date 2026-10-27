/** The three pre-built restaurants shown on the landing page and printed as table QR codes. */
export interface DemoRestaurant {
  slug: string;
  name: string;
  cuisine: string;
  /** What kind of customer this restaurant stands in for, in the pitch. */
  pitch: string;
  accent: string;
  /** The table the demo QR code opens at. */
  table: string;
  dishes: string;
  highlights: string[];
  /** Things worth saying to the waiter in a demo. */
  tryAsking: string[];
}

export const DEMO_RESTAURANTS: DemoRestaurant[] = [
  {
    slug: "saffron-table",
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
    name: "Slice Station",
    cuisine: "Pizza chain",
    pitch: "Every pizza in three sizes, and a busy counter.",
    accent: "#dc2626",
    table: "12",
    dishes: "30 dishes",
    highlights: ["Regular / Medium / Large", "Asks which size", "Prices the size you pick"],
    tryAsking: ["I want a margherita", "Make that a large", "What's your spiciest pizza?"],
  },
];
