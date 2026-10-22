import { NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

// Render's free tier can take ~50s to wake from sleep; the default Vercel timeout would cut that off.
export const maxDuration = 60;

export async function POST(request: Request) {
  const { searchParams } = new URL(request.url);
  const sessionId = searchParams.get("session_id");
  const persona = searchParams.get("persona");

  if (!sessionId || !persona) {
    return NextResponse.json(
      { error: "session_id and persona query params are required" },
      { status: 400 }
    );
  }

  let formData: FormData;
  try {
    formData = await request.formData();
  } catch {
    return NextResponse.json({ error: "Expected multipart/form-data body" }, { status: 400 });
  }

  const backendParams = new URLSearchParams({ session_id: sessionId, persona });
  try {
    const backendResponse = await fetch(`${BACKEND_URL}/chat/voice?${backendParams.toString()}`, {
      method: "POST",
      body: formData,
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
