import { NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

// Render's free tier can take ~50s to wake from sleep.
export const maxDuration = 60;

/**
 * The browser side of Sarvam Samvaad calls, passed to the backend's /samvaad/browser/* routes:
 *   config                                          which agent and restaurants the demo can call
 *   cart/{interaction_id}                           the live cart while a call is going
 *   orgs/{org}/workspaces/{ws}/apps/{app}/url       the web SDK's signed-URL request (the backend adds the
 *                                                   Sarvam API key, so it never reaches the browser)
 */
export async function GET(request: Request, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params;
  const query = new URL(request.url).search;
  const target = `${BACKEND_URL}/samvaad/browser/${path.map(encodeURIComponent).join("/")}${query}`;
  try {
    const backendResponse = await fetch(target, { cache: "no-store" });
    const data = await backendResponse.json().catch(() => ({ detail: "Bad reply from the backend" }));
    return NextResponse.json(data, { status: backendResponse.status });
  } catch {
    return NextResponse.json({ detail: "Couldn't reach the Sarthi backend. Is it running?" }, { status: 502 });
  }
}
