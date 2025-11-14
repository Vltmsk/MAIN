import { NextRequest, NextResponse } from "next/server";

const API_URL = process.env.BACKEND_URL || "http://localhost:8001";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ user: string; symbol: string }> }
) {
  try {
    const { user, symbol } = await params;
    // Декодируем имена из URL (могут быть закодированы)
    const decodedUser = decodeURIComponent(user);
    const decodedSymbol = decodeURIComponent(symbol);
    const searchParams = request.nextUrl.searchParams;
    const queryParams = new URLSearchParams();
    
    // Пробрасываем дополнительные параметры из запроса
    if (searchParams.get("exchange")) {
      queryParams.append("exchange", searchParams.get("exchange")!);
    }
    if (searchParams.get("market")) {
      queryParams.append("market", searchParams.get("market")!);
    }
    if (searchParams.get("ts_from")) {
      queryParams.append("ts_from", searchParams.get("ts_from")!);
    }
    if (searchParams.get("ts_to")) {
      queryParams.append("ts_to", searchParams.get("ts_to")!);
    }
    
    const queryString = queryParams.toString();
    const url = `${API_URL}/api/users/${encodeURIComponent(decodedUser)}/spikes/by-symbol/${encodeURIComponent(decodedSymbol)}${queryString ? `?${queryString}` : ''}`;
    
    const res = await fetch(url);
    if (!res.ok) {
      return NextResponse.json(
        { error: "Failed to fetch spikes by symbol" },
        { status: res.status }
      );
    }
    const data = await res.json();
    return NextResponse.json(data);
  } catch (error) {
    console.error("Error fetching spikes by symbol:", error);
    return NextResponse.json(
      { error: "Failed to fetch spikes by symbol" },
      { status: 500 }
    );
  }
}

