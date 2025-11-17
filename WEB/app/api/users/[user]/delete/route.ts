import { NextRequest, NextResponse } from "next/server";

const API_URL = process.env.BACKEND_URL || "http://localhost:8001";

export async function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ user: string }> }
) {
  try {
    const { user } = await params;
    // Безопасно декодируем имя пользователя из URL (может быть уже декодировано в Next.js 13+)
    // Если декодирование не требуется, просто вернём исходную строку
    let decodedUser: string;
    try {
      decodedUser = decodeURIComponent(user);
    } catch {
      // Если уже декодировано или ошибка декодирования, используем исходное значение
      decodedUser = user;
    }
    
    console.log(`[Delete User API] Попытка удаления: исходный параметр='${user}', декодированный='${decodedUser}', BACKEND_URL='${API_URL}'`);
    
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
    console.log(`[Delete User API] Отправка запроса на backend: ${backendUrl}`);
    
    const res = await fetch(backendUrl, {
      method: "DELETE",
    });
    
    console.log(`[Delete User API] Ответ от backend: status=${res.status}, ok=${res.ok}`);
    
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

