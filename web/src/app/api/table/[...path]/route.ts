import { NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

// Render's free tier can take ~50s to wake from sleep; the default Vercel timeout would cut that off.
export const maxDuration = 60;

/** Relays the guest's table session calls (send to kitchen, bill, pay, rating) to the backend's /table/* routes. */
async function relay(request: Request, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params;
  const target = `${BACKEND_URL}/table/${path.map(encodeURIComponent).join("/")}${new URL(request.url).search}`;
  const hasBody = request.method === "POST";

  try {
    const backendResponse = await fetch(target, {
      method: request.method,
      headers: hasBody ? { "content-type": "application/json" } : undefined,
      body: hasBody ? await request.text() : undefined,
      cache: "no-store",
    });
    const data = await backendResponse.json().catch(() => ({}));
    return NextResponse.json(data, { status: backendResponse.status });
  } catch {
    return NextResponse.json({ error: "Couldn't reach the Sarthi backend. Is it running?" }, { status: 502 });
  }
}

export { relay as GET, relay as POST };
