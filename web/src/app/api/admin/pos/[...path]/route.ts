import { NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

// Render's free tier can take ~50s to wake from sleep; the default Vercel timeout would cut that off.
export const maxDuration = 60;

/**
 * Relays the restaurant-onboarding admin API (/admin/pos/*) with the admin's X-Admin-Key. The backend checks the
 * key; this layer only forwards. POS credentials pass through once, on their way to being encrypted, and are
 * never returned by the backend.
 */
async function relay(request: Request, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params;
  const target = `${BACKEND_URL}/admin/pos/${path.map(encodeURIComponent).join("/")}`;
  const headers: Record<string, string> = { "X-Admin-Key": request.headers.get("x-admin-key") ?? "" };
  const hasBody = !["GET", "HEAD", "DELETE"].includes(request.method);
  if (hasBody) headers["content-type"] = "application/json";
  try {
    const backendResponse = await fetch(target, {
      method: request.method,
      headers,
      body: hasBody ? await request.text() : undefined,
      cache: "no-store",
    });
    const data = await backendResponse.json().catch(() => ({}));
    return NextResponse.json(data, { status: backendResponse.status, headers: { "Cache-Control": "no-store" } });
  } catch {
    return NextResponse.json({ detail: "Couldn't reach the Sarthi backend. Is it running?" }, { status: 502 });
  }
}

export { relay as GET, relay as POST, relay as PATCH };
