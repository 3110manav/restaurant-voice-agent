import type { AdminOrder, AdminRequest, CartLine, MenuItem } from "@/lib/api";
import type { CornerStyle, HeadingStyle, ThemeMode } from "@/lib/brand";
import { getSupabase } from "@/lib/supabase";

export interface OwnerRestaurant {
  id: string;
  slug: string;
  name: string;
  cuisine: string | null;
  tagline: string | null;
  agent_name: string;
  accent_color: string | null;
  status: "draft" | "live";
  role?: "owner" | "manager" | "staff";
  // Table QR pilot (supabase/migrations/003_table_pilot.sql); absent until that migration runs.
  logo_url?: string | null;
  theme_mode?: ThemeMode | null;
  corner_style?: CornerStyle | null;
  heading_style?: HeadingStyle | null;
  google_review_url?: string | null;
  upi_id?: string | null;
  upi_payee_name?: string | null;
  upi_is_merchant?: boolean | null;
  gst_rate?: number | null;
  baseline_turn_minutes?: number | null;
  // What the waiter may suggest (migration 007); all on until the owner turns one off.
  suggest_pairings?: boolean | null;
  promote_bestsellers?: boolean | null;
  promote_new_items?: boolean | null;
}

export interface OwnerMenu {
  restaurant: OwnerRestaurant;
  categories: string[];
  dishes: MenuItem[];
}

export interface DishInput {
  name?: string;
  category?: string;
  price?: number;
  is_veg?: boolean;
  spice_level?: string;
  is_available?: boolean;
  is_bestseller?: boolean;
  is_new?: boolean;
  promo_note?: string;
  short_description?: string;
  long_description?: string;
  ingredients?: string[];
  allergens?: string[];
  tags?: string[];
  variants?: { name: string; price: number }[];
}

export class AuthRequiredError extends Error {}

async function ownerFetch<T>(path: string, init: { method?: string; body?: unknown } = {}): Promise<T> {
  const supabase = getSupabase();
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  if (!token) throw new AuthRequiredError("Log in to continue");

  const res = await fetch(`/api/owner/${path}`, {
    method: init.method ?? "GET",
    headers: { authorization: `Bearer ${token}`, "content-type": "application/json" },
    body: init.body === undefined ? undefined : JSON.stringify(init.body),
    cache: "no-store",
  });
  const body = await res.json().catch(() => ({}));
  if (res.status === 401) {
    await supabase.auth.signOut();
    throw new AuthRequiredError(body.detail ?? "Your session has expired — log in again");
  }
  if (!res.ok) {
    throw new Error(typeof body.detail === "string" ? body.detail : `Request failed (${res.status})`);
  }
  return body as T;
}

export const listRestaurants = () =>
  ownerFetch<{ restaurants: OwnerRestaurant[] }>("restaurants").then((r) => r.restaurants);

export const createRestaurant = (input: { name: string; cuisine?: string; starter_menu: boolean }) =>
  ownerFetch<{ restaurant: OwnerRestaurant; imported: { written: number; embedded: number } | null }>(
    "restaurants",
    { method: "POST", body: input }
  );

export const updateRestaurant = (id: string, patch: Partial<OwnerRestaurant>) =>
  ownerFetch<{ restaurant: OwnerRestaurant }>(`restaurants/${id}`, { method: "PATCH", body: patch });

export const fetchOwnerMenu = (id: string) => ownerFetch<OwnerMenu>(`restaurants/${id}/menu`);

export const saveDish = (restaurantId: string, dishId: string | null, dish: DishInput) =>
  ownerFetch<{ dish: MenuItem; embedding_synced: boolean }>(
    dishId ? `restaurants/${restaurantId}/dishes/${dishId}` : `restaurants/${restaurantId}/dishes`,
    { method: dishId ? "PATCH" : "POST", body: dish }
  );

export const deleteDish = (restaurantId: string, dishId: string) =>
  ownerFetch<{ deleted: string }>(`restaurants/${restaurantId}/dishes/${dishId}`, { method: "DELETE" });

export const syncEmbeddings = (restaurantId: string) =>
  ownerFetch<{ embedded: number; unchanged: number }>(`restaurants/${restaurantId}/embeddings/sync`, {
    method: "POST",
  });

export const listOwnerOrders = (restaurantId: string) =>
  ownerFetch<{ orders: AdminOrder[] }>(`restaurants/${restaurantId}/orders`).then((r) => r.orders);

// ------------------------------------------------------ calls and orders board --

/** Who is on the other end. The phone number arrives already masked ("+91 ••••• 2828"); a full one is never sent. */
export interface BoardCustomer {
  name: string | null;
  phone: string | null;
  /** True when the number is the caller ID from the phone network, false when the guest only said it. */
  verified: boolean;
  /** Orders from this customer in the list shown; more than one means a returning customer. */
  orders: number;
}

export interface BoardOrder {
  id: string;
  created_at: string;
  status: string;
  payment_status?: string | null;
  payment_ref?: string | null;
  channel: "call" | "whatsapp" | "table" | "web";
  fulfilment: "delivery" | "pickup" | "dine_in" | null;
  address: string | null;
  items: CartLine[];
  total: number;
  /** A wish about the whole order ("deliver after 8"); changes to one dish are on that item's note. */
  special_requests?: string | null;
  requests: { id: string; type: string; details: string; status: string; created_at: string }[];
  customer: BoardCustomer;
  call: { outcome: string | null; started_at: string | null; ended_at: string | null } | null;
}

export interface DroppedCart {
  id: string;
  status: "abandoned" | "expired";
  opened_at: string;
  last_activity_at: string;
  items: CartLine[];
  total: number;
  fulfilment: string | null;
  address: string | null;
  special_requests: string | null;
  recovery_attempts: number;
  closed_reason: string | null;
  customer: BoardCustomer;
}

export interface FunnelDay {
  store_id: string;
  day: string;
  calls: number;
  ordered: number;
  callbacks: number;
  no_order: number;
  dropped_carts: number;
  dropped_value: number;
}

/** A support ticket: a caller who asked for a person, or whose order couldn't be saved. */
export interface CallbackTicket {
  id: string;
  status: "open" | "resolved";
  created_at: string;
  resolved_at: string | null;
  reason: string;
  /** Masked; the full number comes only from fetchCallbackPhone, when the owner presses Call. */
  customer: BoardCustomer;
  can_call: boolean;
  order_ref: string | null;
  call_outcome: string | null;
}

export interface CallsBoard {
  orders: BoardOrder[];
  dropped_carts: DroppedCart[];
  funnel: FunnelDay[];
  callbacks?: CallbackTicket[];
}

export const fetchCallbackPhone = (restaurantId: string, ticketId: string) =>
  ownerFetch<{ phone: string }>(`restaurants/${restaurantId}/callbacks/${ticketId}/phone`).then((r) => r.phone);

export const fetchCallsBoard = (restaurantId: string) => ownerFetch<CallsBoard>(`restaurants/${restaurantId}/board`);

export const listOwnerRequests = (restaurantId: string) =>
  ownerFetch<{ requests: AdminRequest[] }>(`restaurants/${restaurantId}/requests`).then((r) => r.requests);

export const resolveOwnerRequest = (restaurantId: string, requestId: string) =>
  ownerFetch<AdminRequest>(`restaurants/${restaurantId}/requests/${requestId}/resolve`, { method: "POST" });

// ------------------------------------------------------------- table QR pilot --

export type TableStatus = "ordering" | "food" | "long" | "eating" | "bill" | "paid";

export interface TonightTable {
  id: string;
  table_no: string | null;
  state: TableStatus;
  minutes: number | null;
  amount: number;
  rounds: number;
  payment_method: "upi" | "counter" | null;
}

export interface StageAverages {
  seated_to_ordered: number | null;
  ordered_to_food: number | null;
  food_to_bill: number | null;
  bill_to_paid: number | null;
  turn: number | null;
}

export interface Tonight {
  tables: TonightTable[];
  averages: StageAverages;
  sessions: number;
}

export interface Customer {
  id: string;
  phone: string;
  name: string | null;
  offers_opt_in: boolean;
  visits: number;
  first_seen_at: string;
  last_visit_at: string;
}

export interface MonthlyReport {
  month: string;
  tables_served: number;
  table_orders: number;
  upsell_total: number;
  averages: StageAverages;
  baseline_turn_minutes: number | null;
  turn_saved_minutes: number | null;
  new_customers: number;
  new_customers_opted_in: number;
  ratings: number;
  average_rating: number | null;
  complaints: number;
}

export const fetchTonight = (restaurantId: string) => ownerFetch<Tonight>(`restaurants/${restaurantId}/tonight`);

export const markTableServed = (restaurantId: string, rowId: string) =>
  ownerFetch<{ ok: boolean }>(`restaurants/${restaurantId}/tables/${rowId}/served`, { method: "POST" });

export const markTablePaid = (restaurantId: string, rowId: string) =>
  ownerFetch<{ ok: boolean }>(`restaurants/${restaurantId}/tables/${rowId}/paid`, { method: "POST" });

export const closeTable = (restaurantId: string, rowId: string) =>
  ownerFetch<{ ok: boolean }>(`restaurants/${restaurantId}/tables/${rowId}/close`, { method: "POST" });

export const listCustomers = (restaurantId: string) =>
  ownerFetch<{ customers: Customer[] }>(`restaurants/${restaurantId}/customers`).then((r) => r.customers);

export interface ConversationSummary {
  session_id: string;
  started_at: string;
  last_at: string;
  turns: number;
  channels: string[];
  table_no: string | null;
  caller_phone: string | null;
  /** How the conversation began: the guest's first words. */
  preview: string;
}

export interface ConversationTurn {
  id: string;
  channel: string;
  speech: string | null;
  language: string | null;
  table_no: string | null;
  /** What the guest typed, or what speech recognition heard. */
  customer_text: string;
  agent_text: string;
  latency_ms: number | null;
  created_at: string;
}

export const listConversations = (restaurantId: string) =>
  ownerFetch<{ conversations: ConversationSummary[] }>(`restaurants/${restaurantId}/conversations`).then((r) => r.conversations);

export const getConversation = (restaurantId: string, sessionId: string) =>
  ownerFetch<{ turns: ConversationTurn[] }>(
    `restaurants/${restaurantId}/conversations/${encodeURIComponent(sessionId)}`
  ).then((r) => r.turns);

export const fetchMonthlyReport = (restaurantId: string, month?: string) =>
  ownerFetch<MonthlyReport>(`restaurants/${restaurantId}/report${month ? `?month=${encodeURIComponent(month)}` : ""}`);

export interface CustomerVisit {
  seated_at: string;
  table_no: string | null;
  ordered: { id: string; name: string; quantity: number; variant?: string; note?: string | null }[];
  bill_total: number | null;
  rating: number | null;
}

export const fetchCustomerVisits = (restaurantId: string, customerId: string) =>
  ownerFetch<{ customer: Customer; visits: CustomerVisit[] }>(`restaurants/${restaurantId}/customers/${customerId}/visits`).then(
    (r) => r.visits
  );

// The voice agent's own settings for one restaurant: its rule book and its WhatsApp numbers (app/agent_config.py).
export type AgentSettings = {
  rules: string;
  rules_updated_at: string | null;
  rules_limit: number;
  calls: {
    answering: boolean;
    calls_number: string | null;
    agent_name: string | null;
    alert_whatsapp: string | null;
    upi_id: string | null;
    upi_payee_name: string | null;
  } | null;
  whatsapp_sender: { own_number: boolean; number: string | null };
};

export const fetchAgentSettings = (restaurantId: string) =>
  ownerFetch<AgentSettings>(`restaurants/${restaurantId}/agent`);

export const saveAgentSettings = (restaurantId: string, patch: { rules?: string; alert_whatsapp?: string; upi_id?: string; upi_payee_name?: string }) =>
  ownerFetch<AgentSettings>(`restaurants/${restaurantId}/agent`, { method: "PUT", body: patch });
