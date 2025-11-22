import { NextRequest, NextResponse } from "next/server";

const API_URL = process.env.BACKEND_URL || "http://localhost:8001";

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ user: string }> }
) {
  try {
    const { user } = await params;
    // Next.js автоматически декодирует параметры маршрута
    const decodedUser = typeof user === 'string' ? user : String(user);
    
    // Проверяем, что параметр user не является строкой 'login' (это может быть ошибка маршрутизации)
    if (decodedUser.toLowerCase() === 'login') {
      console.error(`[Login API Route] Обнаружена попытка входа с параметром 'login' вместо имени пользователя. URL: ${request.url}`);
      return NextResponse.json(
        { error: "Некорректный параметр пользователя", detail: "Убедитесь, что имя пользователя указано правильно в URL." },
        { status: 400 }
      );
    }
    
    console.log(`[Login API Route] Попытка входа для пользователя: '${decodedUser}' (URL: ${request.url})`);
    
    const body = await request.json();
    
    const res = await fetch(`${API_URL}/api/auth/login/${encodeURIComponent(decodedUser)}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    
    if (!res.ok) {
      const errorText = await res.text().catch(() => "Unknown error");
      let errorData;
      try {
        errorData = JSON.parse(errorText);
      } catch {
        errorData = { detail: errorText };
      }
      return NextResponse.json(
        errorData,
        { status: res.status }
      );
    }
    
    const data = await res.json();
    return NextResponse.json(data);
  } catch (error) {
    console.error("Error logging in user:", error);
    return NextResponse.json(
      { error: "Failed to login user", detail: error instanceof Error ? error.message : "Unknown error" },
      { status: 500 }
    );
  }
}

