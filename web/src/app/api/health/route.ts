import { NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

// Render's free tier can take ~50s to wake from sleep; the default Vercel timeout would cut that off.
export const maxDuration = 60;

/** Wakes the backend (and says whether it is up). The site calls it as soon as it opens, so a sleeping
 * backend is already waking while the guest reads the page. */
export async function GET() {
  try {
    const response = await fetch(`${BACKEND_URL}/health`, { cache: "no-store" });
    return NextResponse.json({ ok: response.ok }, { status: response.ok ? 200 : 502 });
  } catch {
    return NextResponse.json({ ok: false }, { status: 502 });
  }
}
