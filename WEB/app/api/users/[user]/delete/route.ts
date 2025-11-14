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
    
    const res = await fetch(`${API_URL}/api/users/${encodeURIComponent(decodedUser)}`, {
      method: "DELETE",
    });
    const data = await res.json();
    return NextResponse.json(data);
  } catch (error) {
    console.error("Error deleting user:", error);
    return NextResponse.json(
      { error: "Failed to delete user" },
      { status: 500 }
    );
  }
}

