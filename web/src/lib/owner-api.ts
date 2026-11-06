import type { AdminOrder, AdminRequest, MenuItem } from "@/lib/api";
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

export const fetchMonthlyReport = (restaurantId: string, month?: string) =>
  ownerFetch<MonthlyReport>(`restaurants/${restaurantId}/report${month ? `?month=${encodeURIComponent(month)}` : ""}`);

export interface CustomerVisit {
  seated_at: string;
  table_no: string | null;
  ordered: { id: string; name: string; quantity: number; variant?: string }[];
  bill_total: number | null;
  rating: number | null;
}

export const fetchCustomerVisits = (restaurantId: string, customerId: string) =>
  ownerFetch<{ customer: Customer; visits: CustomerVisit[] }>(`restaurants/${restaurantId}/customers/${customerId}/visits`).then(
    (r) => r.visits
  );
