import { NextRequest, NextResponse } from "next/server";

const API_URL = process.env.BACKEND_URL || "http://localhost:8001";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ user: string }> }
) {
  try {
    const { user } = await params;
    // Декодируем имя пользователя из URL (может быть закодировано)
    const decodedUser = decodeURIComponent(user);
    const res = await fetch(`${API_URL}/api/users/${encodeURIComponent(decodedUser)}/spikes/stats`);
    if (!res.ok) {
      return NextResponse.json(
        { error: "Failed to fetch user spikes stats" },
        { status: res.status }
      );
    }
    const data = await res.json();
    return NextResponse.json(data);
  } catch (error) {
    console.error("Error fetching user spikes stats:", error);
    return NextResponse.json(
      { error: "Failed to fetch user spikes stats" },
      { status: 500 }
    );
  }
}

