import { NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

// Render's free tier can take ~50s to wake from sleep; the default Vercel timeout would cut that off.
export const maxDuration = 60;

export async function GET(_request: Request, { params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  try {
    const backendResponse = await fetch(`${BACKEND_URL}/restaurants/${encodeURIComponent(slug)}`, {
      cache: "no-store",
    });
    const data = await backendResponse.json();
    return NextResponse.json(data, { status: backendResponse.status });
  } catch {
    return NextResponse.json(
      { error: "Couldn't reach the Sarthi backend. Is it running?" },
      { status: 502 }
    );
  }
}
