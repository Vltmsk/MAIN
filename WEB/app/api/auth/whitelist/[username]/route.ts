import { NextRequest, NextResponse } from "next/server";

const API_URL = process.env.BACKEND_URL || "http://localhost:8001";

export async function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ username: string }> },
) {
  try {
    const { username } = await params;
    const decoded = typeof username === "string" ? username : String(username);

    const res = await fetch(
      `${API_URL}/api/auth/whitelist/${encodeURIComponent(decoded)}`,
      { method: "DELETE" },
    );

    const data = await res.json().catch(() => ({}));
    return NextResponse.json(data, { status: res.status });
  } catch (error) {
    console.error("Error removing login from whitelist:", error);
    return NextResponse.json(
      { error: "Failed to remove login from whitelist" },
      { status: 500 },
    );
  }
}


