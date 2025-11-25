import { NextRequest, NextResponse } from "next/server";

const API_URL = process.env.BACKEND_URL || "http://localhost:8001";

export async function GET(request: NextRequest) {
  try {
    const res = await fetch(`${API_URL}/api/users/metrics`);
    const data = await res.json();
    return NextResponse.json(data);
  } catch (error) {
    console.error("Error fetching metrics settings:", error);
    return NextResponse.json(
      { error: "Failed to fetch metrics settings" },
      { status: 500 }
    );
  }
}

