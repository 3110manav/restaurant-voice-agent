/**
 * A food emoji for a dish, from its name (most specific rule first) and then its menu section.
 * Used for the menu tile of a dish that has no photo, so every card still looks like food.
 */
const RULES: [RegExp, string][] = [
  [/ice cream|kulfi|gelato|sundae/, "🍨"],
  [/garlic bread|breadstick|baguette/, "🥖"],
  [/pizza/, "🍕"],
  [/burger/, "🍔"],
  [/sandwich|panini|\bsub\b|melt|toast/, "🥪"],
  [/wrap|roll up|burrito|shawarma|kathi|spring roll/, "🌯"],
  [/sushi|nigiri|sashimi|maki|\broll\b/, "🍣"],
  [/momo|dumpling|siu mai|har gow|potsticker|samosa|gyoza|ravioli/, "🥟"],
  [/\bbao\b|buns?\b/, "🥟"],
  [/puff|croissant|pie\b/, "🥐"],
  [/tofu/, "🍢"],
  [/noodle|chow ?mein|ramen|hakka|udon|lo mein/, "🍜"],
  [/pasta|spaghetti|penne|fettuccine|linguine|gnocchi|lasagn|ziti|mac and cheese|macaroni|carbonara/, "🍝"],
  [/biryani|pulao|pilaf|fried rice/, "🍛"],
  [/curry|masala|makhani|korma|rogan|dal\b|chana|saag|butter chicken|tikka masala|paneer butter|kadai|bhuna|vindaloo|chole|rajma|keema|matar|kofta|bharta/, "🍛"],
  [/rice|risotto|khichdi/, "🍚"],
  [/naan|roti|kulcha|paratha|bhatura|puri\b|chapati|phulka/, "🫓"],
  [/dosa|uttapam|pesarattu|pancake|crepe/, "🥞"],
  [/idli|vada|medu/, "🍘"],
  [/soup|rasam|miso|broth|shorba/, "🍲"],
  [/salad|raita|kachumber|slaw/, "🥗"],
  [/wings|nugget|chicken|drumstick/, "🍗"],
  [/kebab|kabab|skewer|tandoori|seekh|65\b|satay/, "🍢"],
  [/prawn|shrimp|fish|tuna|salmon|crab|seafood|calamari|eel/, "🍤"],
  [/egg|omelette|omelet|bhurji/, "🍳"],
  [/fries|wedges|potato|aloo/, "🍟"],
  [/paneer|cheese|mozzarella/, "🧀"],
  [/coffee|espresso|latte|cappuccino|mocha/, "☕"],
  [/chai|tea\b/, "🍵"],
  [/lassi|milk|shake|smoothie|buttermilk|chaas/, "🥛"],
  [/juice|cooler|lemon|soda|cola|drink|mojito|mocktail|lemonade|water|beverage/, "🥤"],
  [/cake|brownie|lava|pastry|cupcake|tiramisu|cheesecake/, "🍰"],
  [/donut|doughnut|dough bites|churro/, "🍩"],
  [/cookie|biscuit/, "🍪"],
  [/jamun|halwa|kheer|phirni|payasam|rasmalai|rabri|jalebi|barfi|ladoo|mithai|pudding|custard|sweet/, "🍮"],
  [/combo|meal|platter|thali|box|feast/, "🍱"],
];

const BY_SECTION: [RegExp, string][] = [
  [/beverage|drink|juice/, "🥤"],
  [/dessert|sweet/, "🍰"],
  [/bread/, "🫓"],
  [/starter|appetiz|snack|side/, "🍢"],
  [/soup/, "🍲"],
  [/combo/, "🍱"],
];

export function dishEmoji(name: string, category?: string): string {
  const lowered = name.toLowerCase();
  for (const [pattern, emoji] of RULES) if (pattern.test(lowered)) return emoji;
  const section = (category ?? "").toLowerCase();
  for (const [pattern, emoji] of RULES) if (pattern.test(section)) return emoji;
  for (const [pattern, emoji] of BY_SECTION) if (pattern.test(section)) return emoji;
  return "🍽️";
}
