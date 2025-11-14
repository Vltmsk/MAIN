import { NextRequest, NextResponse } from "next/server";

const API_URL = process.env.BACKEND_URL || "http://localhost:8001";

export async function GET(request: NextRequest) {
  const searchParams = request.nextUrl.searchParams;
  const params = new URLSearchParams(searchParams);
  
  try {
    const res = await fetch(`${API_URL}/api/spikes?${params}`);
    const data = await res.json();
    return NextResponse.json(data);
  } catch (error) {
    console.error("Error fetching spikes:", error);
    return NextResponse.json(
      { error: "Failed to fetch spikes" },
      { status: 500 }
    );
  }
}

