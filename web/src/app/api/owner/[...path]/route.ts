import { NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

// Render's free tier can take ~50s to wake from sleep; the default Vercel timeout would cut that off.
export const maxDuration = 60;

/**
 * One catch-all proxy for the whole owner API: forwards method, body and the
 * owner's `Authorization: Bearer <supabase token>` header to the backend's
 * /owner/* routes. The backend does the real authentication and per-restaurant
 * authorization — this layer only relays.
 */
async function relay(request: Request, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params;
  const target = `${BACKEND_URL}/owner/${path.map(encodeURIComponent).join("/")}${new URL(request.url).search}`;

  const headers: Record<string, string> = {};
  const auth = request.headers.get("authorization");
  if (auth) headers.authorization = auth;
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
    return NextResponse.json(data, { status: backendResponse.status });
  } catch {
    return NextResponse.json(
      { detail: "Couldn't reach the Sarthi backend. Is it running?" },
      { status: 502 }
    );
  }
}

export { relay as GET, relay as POST, relay as PATCH, relay as DELETE };
