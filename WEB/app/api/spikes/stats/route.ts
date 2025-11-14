import { NextRequest, NextResponse } from "next/server";

const API_URL = process.env.BACKEND_URL || "http://localhost:8001";

export async function GET(request: NextRequest) {
  try {
    const res = await fetch(`${API_URL}/api/spikes/stats`);
    if (!res.ok) {
      return NextResponse.json(
        { error: "Failed to fetch spikes stats" },
        { status: res.status }
      );
    }
    const data = await res.json();
    return NextResponse.json(data);
  } catch (error) {
    console.error("Error fetching spikes stats:", error);
    return NextResponse.json(
      { error: "Failed to fetch spikes stats" },
      { status: 500 }
    );
  }
}

