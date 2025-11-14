import { NextRequest, NextResponse } from "next/server";

const API_URL = process.env.BACKEND_URL || process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8001";

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ user: string }> }
) {
  try {
    const resolvedParams = await params;
    // Декодируем имя пользователя из URL (может быть закодировано)
    const user = decodeURIComponent(resolvedParams.user);
    
    if (!user) {
      return NextResponse.json(
        { error: "User parameter is required", detail: "User parameter is required" },
        { status: 400 }
      );
    }
    
    const res = await fetch(`${API_URL}/api/users/${encodeURIComponent(user)}/test`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
    });
    
    if (!res.ok) {
      let error;
      try {
        error = await res.json();
      } catch {
        error = { detail: `Backend returned status ${res.status}` };
      }
      return NextResponse.json(error, { status: res.status });
    }
    
    const data = await res.json();
    return NextResponse.json(data);
  } catch (error) {
    console.error("Error sending test message:", error);
    const errorMessage = error instanceof Error ? error.message : "Unknown error";
    return NextResponse.json(
      { error: "Failed to send test message", detail: errorMessage },
      { status: 500 }
    );
  }
}

