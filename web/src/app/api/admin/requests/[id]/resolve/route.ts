import { NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

export async function POST(
  _request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  try {
    const backendResponse = await fetch(
      `${BACKEND_URL}/admin/requests/${encodeURIComponent(id)}/resolve`,
      { method: "POST" }
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
