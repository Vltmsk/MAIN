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
    const res = await fetch(`${API_URL}/api/users/${encodeURIComponent(decodedUser)}/spikes`, {
      method: "DELETE",
    });
    
    if (!res.ok) {
      const errorData = await res.json().catch(() => ({ error: "Failed to delete user spikes" }));
      return NextResponse.json(
        { error: errorData.detail || errorData.error || "Failed to delete user spikes" },
        { status: res.status }
      );
    }
    
    const data = await res.json();
    return NextResponse.json(data);
  } catch (error) {
    console.error("Error deleting user spikes:", error);
    return NextResponse.json(
      { error: "Failed to delete user spikes" },
      { status: 500 }
    );
  }
}

