import { NextRequest, NextResponse } from "next/server";

const API_URL = process.env.BACKEND_URL || "http://localhost:8001";

export async function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ user: string }> }
) {
  // Логируем, что маршрут был вызван
  console.log(`[Delete User API] Маршрут вызван для удаления пользователя`);
  
  try {
    const { user } = await params;
    // Next.js автоматически декодирует параметры маршрута, поэтому используем user как есть
    // Но для безопасности проверяем, что это строка
    const decodedUser = typeof user === 'string' ? user.trim() : String(user).trim();
    
    // Логируем информацию о пользователе для отладки
    const userBytes = new TextEncoder().encode(decodedUser);
    console.log(`[Delete User API] Попытка удаления: "${decodedUser}" (length: ${decodedUser.length}, bytes: ${Array.from(userBytes).map(b => b.toString(16).padStart(2, '0')).join(' ')})`);
    
    if (!decodedUser) {
      return NextResponse.json(
        { error: "Имя пользователя не может быть пустым" },
        { status: 400 }
      );
    }
    
    // Запрещаем удаление системных пользователей "Stats" и "Влад"
    const lowerUserName = decodedUser.toLowerCase();
    if (lowerUserName === "stats" || lowerUserName === "влад") {
      return NextResponse.json(
        { error: `Нельзя удалить системного пользователя '${decodedUser}'` },
        { status: 403 }
      );
    }
    
    const encodedUser = encodeURIComponent(decodedUser);
    const backendUrl = `${API_URL}/api/users/${encodedUser}`;
    console.log(`[Delete User API] Отправка запроса на backend:`);
    console.log(`  - API_URL из env: ${API_URL}`);
    console.log(`  - Полный URL: ${backendUrl}`);
    console.log(`  - Имя пользователя (encoded): ${encodedUser}`);
    
    const res = await fetch(backendUrl, {
      method: "DELETE",
    });
    
    console.log(`[Delete User API] Ответ от backend: status=${res.status}, ok=${res.ok}`);
    
    // Если ошибка, логируем больше информации
    if (!res.ok) {
      console.error(`[Delete User API] Ошибка подключения к backend:`);
      console.error(`  - URL: ${backendUrl}`);
      console.error(`  - Status: ${res.status}`);
      console.error(`  - StatusText: ${res.statusText}`);
    }
    
    // Проверяем статус ответа
    if (!res.ok) {
      let errorData;
      try {
        errorData = await res.json();
        console.log(`[Delete User API] Ошибка от backend:`, errorData);
      } catch {
        const errorText = await res.text().catch(() => "");
        errorData = { detail: `Backend returned status ${res.status}${errorText ? `: ${errorText}` : ""}` };
        console.log(`[Delete User API] Не удалось распарсить JSON ответ. Текст: ${errorText}`);
      }
      return NextResponse.json(
        { error: errorData.detail || errorData.error || `Failed to delete user: ${res.status}` },
        { status: res.status }
      );
    }
    
    const data = await res.json();
    console.log(`[Delete User API] Успешное удаление:`, data);
    return NextResponse.json(data);
  } catch (error) {
    console.error("[Delete User API] Ошибка при удалении пользователя:", error);
    const errorMessage = error instanceof Error ? error.message : "Unknown error";
    
    // Проверяем, является ли ошибка проблемой подключения
    if (error instanceof Error && (error.message.includes("ECONNREFUSED") || error.message.includes("fetch failed"))) {
      console.error(`[Delete User API] Не удалось подключиться к backend на ${API_URL}`);
      return NextResponse.json(
        { error: `Не удалось подключиться к backend серверу. Проверьте, что backend запущен на ${API_URL}` },
        { status: 503 }
      );
    }
    
    return NextResponse.json(
      { error: `Failed to delete user: ${errorMessage}` },
      { status: 500 }
    );
  }
}

