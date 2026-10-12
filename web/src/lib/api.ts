export interface CartLine {
  id: string;
  name: string;
  price: number;
  quantity: number;
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

export interface MenuItem {
  id: string;
  name: string;
  category: string;
  price: number;
  description: string;
  // Food-only fields (restaurant menu).
  veg?: boolean;
  spice_level?: string;
  ingredients?: string[];
  // Grocery-only field (quick-commerce catalog).
  brand?: string;
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
}

async function parseOrThrow<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.json().catch(() => ({ error: "Unknown error" }));
    throw new Error(body.error ?? `Request failed with status ${res.status}`);
  }
  return res.json();
}

export async function sendChatMessage(
  sessionId: string,
  persona: string,
  message: string
): Promise<ChatResponse> {
  const res = await fetch("/api/chat", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, persona, message }),
  });
  return parseOrThrow(res);
}

export async function sendVoiceMessage(
  sessionId: string,
  persona: string,
  audio: Blob
): Promise<VoiceChatResponse> {
  const formData = new FormData();
  formData.append("audio", audio, "recording.webm");

  const params = new URLSearchParams({ session_id: sessionId, persona });
  const res = await fetch(`/api/chat/voice?${params.toString()}`, {
    method: "POST",
    body: formData,
  });
  return parseOrThrow(res);
}

export async function fetchMenu(persona: string): Promise<MenuItem[]> {
  const res = await fetch(`/api/menu?persona=${encodeURIComponent(persona)}`);
  const data = await parseOrThrow<{ items: MenuItem[] }>(res);
  return data.items;
}

export async function addToCart(
  sessionId: string,
  persona: string,
  itemId: string,
  quantity = 1
): Promise<CartMutationResponse> {
  const res = await fetch("/api/cart/add", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, persona, item_id: itemId, quantity }),
  });
  return parseOrThrow(res);
}

export async function removeFromCart(
  sessionId: string,
  persona: string,
  itemId: string,
  quantity = 1
): Promise<CartMutationResponse> {
  const res = await fetch("/api/cart/remove", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, persona, item_id: itemId, quantity }),
  });
  return parseOrThrow(res);
}

export interface SessionStateResponse {
  cart: CartLine[];
  service_log: ServiceLogEntry[];
}

export async function fetchCart(sessionId: string, persona: string): Promise<SessionStateResponse> {
  const params = new URLSearchParams({ session_id: sessionId, persona });
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
  persona: string
): Promise<LiveKitTokenResponse> {
  const res = await fetch("/api/livekit/token", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, persona }),
  });
  return parseOrThrow(res);
}
