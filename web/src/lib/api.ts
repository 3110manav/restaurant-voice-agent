export interface CartLine {
  id: string;
  name: string;
  price: number;
  quantity: number;
  /** Size/portion (e.g. "Large", "Half") for dishes that come in several. */
  variant?: string;
}

export interface ServiceLogEntry {
  type: string;
  details: string;
  notes: string;
}

export interface ChatResponse {
  reply: string;
  cart: CartLine[];
  service_log: ServiceLogEntry[];
}

export interface VoiceChatResponse extends ChatResponse {
  transcript: string;
  reply_audio_wav_base64: string | null;
}

export interface MenuVariant {
  name: string;
  price: number;
}

export interface MenuItem {
  id: string;
  name: string;
  category: string;
  /** For dishes with sizes this is the cheapest size's price. */
  price: number;
  description: string;
  // Food-only fields (restaurant menu).
  veg?: boolean;
  spice_level?: string | null;
  ingredients?: string[];
  // Grocery-only field (quick-commerce catalog).
  brand?: string;
  // Multi-restaurant menus.
  variants?: MenuVariant[];
  long_description?: string;
  allergens?: string[];
  tags?: string[];
  is_available?: boolean;
  image_url?: string | null;
  knowledge_status?: "missing" | "ai_draft" | "approved";
}

export interface CartMutationResponse {
  cart: CartLine[];
  message: string;
}

export interface AdminOrder {
  id: string;
  session_id: string;
  persona: string;
  items: CartLine[];
  total: number;
  status: string;
  created_at: string;
  table_no?: string | null;
}

export interface AdminRequest {
  id: string;
  session_id: string;
  persona: string;
  type: string;
  details: string;
  notes: string;
  status: string;
  created_at: string;
  resolved_at: string | null;
  table_no?: string | null;
}

export interface RestaurantInfo {
  slug: string;
  name: string;
  cuisine: string | null;
  tagline: string | null;
  agent_name: string;
  currency: string;
  accent_color: string | null;
  logo_url: string | null;
}

/** Which restaurant (and table) a conversation belongs to; absent for the four legacy personas. */
export interface RestaurantContext {
  restaurant?: string;
  tableNo?: string | null;
  /** The English / हिन्दी toggle; the backend defaults to English when absent. */
  language?: Language;
}

export type Language = "en" | "hi";

async function parseOrThrow<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const message =
      body.error ?? (typeof body.detail === "string" ? body.detail : undefined) ?? undefined;
    throw new Error(message ?? `Request failed with status ${res.status}`);
  }
  return res.json();
}

export async function sendChatMessage(
  sessionId: string,
  persona: string,
  message: string,
  ctx: RestaurantContext = {}
): Promise<ChatResponse> {
  const res = await fetch("/api/chat", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      session_id: sessionId,
      persona,
      message,
      restaurant: ctx.restaurant,
      table_no: ctx.tableNo,
      language: ctx.language,
    }),
  });
  return parseOrThrow(res);
}

export async function sendVoiceMessage(
  sessionId: string,
  persona: string,
  audio: Blob,
  ctx: RestaurantContext = {}
): Promise<VoiceChatResponse> {
  const formData = new FormData();
  formData.append("audio", audio, "recording.webm");

  const params = new URLSearchParams({ session_id: sessionId, persona });
  if (ctx.restaurant) params.set("restaurant", ctx.restaurant);
  if (ctx.tableNo) params.set("table_no", ctx.tableNo);
  if (ctx.language) params.set("language", ctx.language);
  const res = await fetch(`/api/chat/voice?${params.toString()}`, {
    method: "POST",
    body: formData,
  });
  return parseOrThrow(res);
}

export async function fetchMenu(persona: string, restaurant?: string): Promise<MenuItem[]> {
  const params = new URLSearchParams({ persona });
  if (restaurant) params.set("restaurant", restaurant);
  const res = await fetch(`/api/menu?${params.toString()}`, { cache: "no-store" });
  const data = await parseOrThrow<{ items: MenuItem[] }>(res);
  return data.items;
}

export async function fetchRestaurant(slug: string): Promise<RestaurantInfo> {
  const res = await fetch(`/api/restaurants/${encodeURIComponent(slug)}`, { cache: "no-store" });
  return parseOrThrow(res);
}

export interface PhotoCredit {
  dish: string;
  credit: string;
  license: string | null;
  license_url: string | null;
  page: string | null;
}

export async function fetchPhotoCredits(slug: string): Promise<PhotoCredit[]> {
  const res = await fetch(`/api/restaurants/${encodeURIComponent(slug)}/credits`, { cache: "no-store" });
  return (await parseOrThrow<{ credits: PhotoCredit[] }>(res)).credits;
}

export async function addToCart(
  sessionId: string,
  persona: string,
  itemId: string,
  quantity = 1,
  opts: { restaurant?: string; variant?: string } = {}
): Promise<CartMutationResponse> {
  const res = await fetch("/api/cart/add", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      session_id: sessionId,
      persona,
      item_id: itemId,
      quantity,
      restaurant: opts.restaurant,
      variant: opts.variant,
    }),
  });
  return parseOrThrow(res);
}

export async function removeFromCart(
  sessionId: string,
  persona: string,
  itemId: string,
  quantity = 1,
  opts: { restaurant?: string; variant?: string } = {}
): Promise<CartMutationResponse> {
  const res = await fetch("/api/cart/remove", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      session_id: sessionId,
      persona,
      item_id: itemId,
      quantity,
      restaurant: opts.restaurant,
      variant: opts.variant,
    }),
  });
  return parseOrThrow(res);
}

export interface SessionStateResponse {
  cart: CartLine[];
  service_log: ServiceLogEntry[];
}

export async function fetchCart(
  sessionId: string,
  persona: string,
  restaurant?: string
): Promise<SessionStateResponse> {
  const params = new URLSearchParams({ session_id: sessionId, persona });
  if (restaurant) params.set("restaurant", restaurant);
  const res = await fetch(`/api/cart?${params.toString()}`, { cache: "no-store" });
  return parseOrThrow(res);
}

export async function fetchAdminOrders(): Promise<{ configured: boolean; orders: AdminOrder[] }> {
  const res = await fetch("/api/admin/orders", { cache: "no-store" });
  return parseOrThrow(res);
}

export async function fetchAdminRequests(): Promise<{
  configured: boolean;
  requests: AdminRequest[];
}> {
  const res = await fetch("/api/admin/requests", { cache: "no-store" });
  return parseOrThrow(res);
}

export async function resolveAdminRequest(id: string): Promise<AdminRequest> {
  const res = await fetch(`/api/admin/requests/${encodeURIComponent(id)}/resolve`, {
    method: "POST",
  });
  return parseOrThrow(res);
}

export interface LiveKitTokenResponse {
  configured: boolean;
  url: string | null;
  token: string | null;
  room: string | null;
}

export async function fetchLiveKitToken(
  sessionId: string,
  persona: string,
  ctx: RestaurantContext = {}
): Promise<LiveKitTokenResponse> {
  const res = await fetch("/api/livekit/token", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      session_id: sessionId,
      persona,
      restaurant: ctx.restaurant,
      table_no: ctx.tableNo,
      language: ctx.language,
    }),
  });
  return parseOrThrow(res);
}
