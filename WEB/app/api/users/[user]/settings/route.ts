import { NextRequest, NextResponse } from "next/server";

const API_URL = process.env.BACKEND_URL || "http://localhost:8001";

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ user: string }> }
) {
  try {
    const { user } = await params;
    // Безопасно декодируем имя пользователя из URL (может быть уже декодировано в Next.js 13+)
    let decodedUser: string;
    try {
      decodedUser = decodeURIComponent(user);
    } catch {
      decodedUser = user;
    }
    const body = await request.json();
    const res = await fetch(`${API_URL}/api/users/${encodeURIComponent(decodedUser)}/settings`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    
    if (!res.ok) {
      const errorText = await res.text().catch(() => "Unknown error");
      return NextResponse.json(
        { error: errorText },
        { status: res.status }
      );
    }
    
    const data = await res.json();
    return NextResponse.json(data);
  } catch (error) {
    console.error("Error updating user settings:", error);
    return NextResponse.json(
      { error: "Failed to update user settings" },
      { status: 500 }
    );
  }
}

