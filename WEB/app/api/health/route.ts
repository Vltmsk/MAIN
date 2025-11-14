import { NextRequest, NextResponse } from "next/server";

const API_URL = process.env.BACKEND_URL || "http://localhost:8001";

export async function GET(request: NextRequest) {
  try {
    const res = await fetch(`${API_URL}/api/health`);
    const data = await res.json();
    return NextResponse.json(data);
  } catch (error) {
    console.error("Error checking health:", error);
    return NextResponse.json(
      { ok: false, error: "Failed to check health" },
      { status: 500 }
    );
  }
}

