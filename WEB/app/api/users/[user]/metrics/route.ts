import { NextRequest, NextResponse } from "next/server";

const API_URL = process.env.BACKEND_URL || "http://localhost:8001";

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ user: string }> }
) {
  try {
    const { user } = await params;
    const decodedUser = typeof user === 'string' ? user : String(user);
    const encodedUser = encodeURIComponent(decodedUser);
    
    const body = await request.json();
    const { enabled } = body;
    
    if (typeof enabled !== 'boolean') {
      return NextResponse.json(
        { error: "enabled must be a boolean" },
        { status: 400 }
      );
    }
    
    const res = await fetch(`${API_URL}/api/users/${encodedUser}/metrics`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ enabled }),
    });
    
    if (!res.ok) {
      const errorData = await res.json().catch(() => ({ detail: "Unknown error" }));
      return NextResponse.json(
        { error: errorData.detail || "Failed to update metrics settings" },
        { status: res.status }
      );
    }
    
    const data = await res.json();
    return NextResponse.json(data);
  } catch (error) {
    console.error("Error updating metrics settings:", error);
    return NextResponse.json(
      { error: "Failed to update metrics settings" },
      { status: 500 }
    );
  }
}

