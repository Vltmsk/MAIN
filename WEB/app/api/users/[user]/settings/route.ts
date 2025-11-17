import { NextRequest, NextResponse } from "next/server";

const API_URL = process.env.BACKEND_URL || "http://localhost:8001";

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ user: string }> }
) {
  try {
    const { user } = await params;
    // Next.js автоматически декодирует параметры маршрута, поэтому используем user как есть
    // Но для безопасности проверяем, что это строка
    const decodedUser = typeof user === 'string' ? user.trim() : String(user).trim();
    
    if (!decodedUser) {
      return NextResponse.json(
        { error: "Имя пользователя не может быть пустым" },
        { status: 400 }
      );
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

