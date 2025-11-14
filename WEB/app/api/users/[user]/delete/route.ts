import { NextRequest, NextResponse } from "next/server";

const API_URL = process.env.BACKEND_URL || "http://localhost:8001";

export async function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ user: string }> }
) {
  try {
    const { user } = await params;
    // Декодируем имя пользователя из URL (может быть закодировано)
    const decodedUser = decodeURIComponent(user);
    
    // Запрещаем удаление системных пользователей "Stats" и "Влад"
    const lowerUserName = decodedUser.toLowerCase();
    if (lowerUserName === "stats" || lowerUserName === "влад") {
      return NextResponse.json(
        { error: `Нельзя удалить системного пользователя '${decodedUser}'` },
        { status: 403 }
      );
    }
    
    const encodedUser = encodeURIComponent(decodedUser);
    const res = await fetch(`${API_URL}/api/users/${encodedUser}`, {
      method: "DELETE",
    });
    
    // Проверяем статус ответа
    if (!res.ok) {
      let errorData;
      try {
        errorData = await res.json();
      } catch {
        errorData = { detail: `Backend returned status ${res.status}` };
      }
      return NextResponse.json(
        { error: errorData.detail || errorData.error || `Failed to delete user: ${res.status}` },
        { status: res.status }
      );
    }
    
    const data = await res.json();
    return NextResponse.json(data);
  } catch (error) {
    console.error("Error deleting user:", error);
    const errorMessage = error instanceof Error ? error.message : "Unknown error";
    return NextResponse.json(
      { error: `Failed to delete user: ${errorMessage}` },
      { status: 500 }
    );
  }
}

