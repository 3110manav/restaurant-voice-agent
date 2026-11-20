/** The pre-built demo stores shown on the landing page and printed as QR codes: a restaurant, a kirana and a pharmacy. */
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
    slug: "borivali-biryani-centre",
    kind: "restaurant",
    agent: "Kabir",
    name: "Borivali Biryani Centre",
    cuisine: "Biryani, Mughlai & Indo-Chinese",
    pitch: "A 300-dish menu of biryani, tandoor, handi gravies and Chinese, ordered by voice.",
    accent: "#a16207",
    table: "5",
    dishes: "300+ dishes",
    highlights: ["Small / Big / Large biryani", "Suggests the right raita or naan", "Plain or butter breads"],
    tryAsking: ["One chicken dum biryani, big", "Add a paneer tikka", "What goes with butter chicken?"],
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
