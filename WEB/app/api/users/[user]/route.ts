import { NextRequest, NextResponse } from "next/server";

const API_URL = process.env.BACKEND_URL || "http://localhost:8001";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ user: string }> }
) {
  try {
    const { user } = await params;
    // Next.js автоматически декодирует параметры маршрута, поэтому используем user как есть
    // Но для безопасности проверяем, что это строка
    const decodedUser = typeof user === 'string' ? user : String(user);
    
    // Логируем информацию о пользователе для отладки
    const userBytes = new TextEncoder().encode(decodedUser);
    console.log(`[API Route] Fetching user: "${decodedUser}" (length: ${decodedUser.length}, bytes: ${Array.from(userBytes).map(b => b.toString(16).padStart(2, '0')).join(' ')})`);
    
    // Кодируем для передачи в backend
    const encodedUser = encodeURIComponent(decodedUser);
    const url = `${API_URL}/api/users/${encodedUser}`;
    console.log(`[API Route] Backend URL: ${url}`);
    
    const res = await fetch(url);
    
    if (!res.ok) {
      // Если пользователь не найден, возвращаем 404
      if (res.status === 404) {
        console.log(`[API Route] User "${decodedUser}" not found in database`);
        return NextResponse.json(
          { error: "User not found" },
          { status: 404 }
        );
      }
      const errorText = await res.text().catch(() => "Unknown error");
      console.error(`[API Route] Error from backend: ${res.status} - ${errorText}`);
      return NextResponse.json(
        { error: errorText },
        { status: res.status }
      );
    }
    
    const data = await res.json();
    console.log(`[API Route] Successfully fetched user data for "${decodedUser}"`);
    return NextResponse.json(data);
  } catch (error) {
    console.error("[API Route] Error fetching user:", error);
    return NextResponse.json(
      { error: "Failed to fetch user" },
      { status: 500 }
    );
  }
}

