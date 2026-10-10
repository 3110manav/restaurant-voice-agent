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
