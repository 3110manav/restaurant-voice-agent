import { NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const persona = searchParams.get("persona") ?? "online";

  try {
    const backendResponse = await fetch(
      `${BACKEND_URL}/menu?persona=${encodeURIComponent(persona)}`
    );
    const data = await backendResponse.json();
    return NextResponse.json(data, { status: backendResponse.status });
  } catch {
    return NextResponse.json(
      { error: "Couldn't reach the Sarthi backend. Is it running?" },
      { status: 502 }
    );
  }
}
