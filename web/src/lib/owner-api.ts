import type { AdminOrder, AdminRequest, MenuItem } from "@/lib/api";
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
