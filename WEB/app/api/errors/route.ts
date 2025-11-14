import { NextRequest, NextResponse } from "next/server";

const API_URL = process.env.BACKEND_URL || "http://localhost:8001";

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const exchange = searchParams.get("exchange");
    const error_type = searchParams.get("error_type");
    const limit = searchParams.get("limit");

    const params = new URLSearchParams();
    if (exchange) params.append("exchange", exchange);
    if (error_type) params.append("error_type", error_type);
    if (limit) params.append("limit", limit);

    const res = await fetch(`${API_URL}/api/errors?${params.toString()}`);
    const data = await res.json();
    return NextResponse.json(data);
  } catch (error) {
    console.error("Error fetching errors:", error);
    return NextResponse.json(
      { error: "Failed to fetch errors" },
      { status: 500 }
    );
  }
}

export async function DELETE(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const error_id = searchParams.get("error_id");
    const user = searchParams.get("user");

    // Проверяем, что пользователь указан и это "Влад"
    if (!user || user.toLowerCase() !== "влад") {
      return NextResponse.json(
        { error: "Удаление логов ошибок доступно только для пользователя 'Влад'" },
        { status: 403 }
      );
    }

    const params = new URLSearchParams();
    params.append("user", user);

    // Если указан error_id, удаляем конкретную ошибку
    if (error_id) {
      const res = await fetch(`${API_URL}/api/errors/${error_id}?${params.toString()}`, {
        method: "DELETE",
      });
      const data = await res.json();
      return NextResponse.json(data, { status: res.status });
    } else {
      // Иначе удаляем все ошибки
      const res = await fetch(`${API_URL}/api/errors?${params.toString()}`, {
        method: "DELETE",
      });
      const data = await res.json();
      return NextResponse.json(data, { status: res.status });
    }
  } catch (error) {
    console.error("Error deleting errors:", error);
    return NextResponse.json(
      { error: "Failed to delete errors" },
      { status: 500 }
    );
  }
}

