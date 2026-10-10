import { NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

interface ChatRequestBody {
  session_id: string;
  message: string;
  persona: string;
}

export async function POST(request: Request) {
  let body: ChatRequestBody;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  if (!body.session_id || !body.message || !body.persona) {
    return NextResponse.json(
      { error: "session_id, message, and persona are required" },
      { status: 400 }
    );
  }

  try {
    const backendResponse = await fetch(`${BACKEND_URL}/chat`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
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
