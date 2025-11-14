import { NextRequest, NextResponse } from "next/server";

const API_URL = process.env.BACKEND_URL || process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8001";

export async function GET(request: NextRequest) {
  try {
    const res = await fetch(`${API_URL}/api/metrics`);
    
    if (!res.ok) {
      let errorDetail = `Backend returned status ${res.status}`;
      try {
        const errorData = await res.json();
        errorDetail = errorData.detail || errorData.error || errorDetail;
      } catch {
        // Если не удалось парсить JSON, используем текст ответа
        const errorText = await res.text().catch(() => errorDetail);
        errorDetail = errorText || errorDetail;
      }
      
      console.error(`Error fetching metrics from backend: ${res.status} - ${errorDetail}`);
      return NextResponse.json(
        { error: "Failed to fetch metrics", detail: errorDetail },
        { status: res.status }
      );
    }
    
    const data = await res.json();
    return NextResponse.json(data);
  } catch (error) {
    console.error("Error fetching metrics:", error);
    
    // Проверяем тип ошибки
    let errorMessage = "Unknown error";
    if (error instanceof Error) {
      const cause = (error as any).cause;
      if (cause?.code === "ECONNREFUSED") {
        errorMessage = `Не удалось подключиться к API серверу на ${API_URL}. Убедитесь, что FastAPI сервер запущен (python api_server.py)`;
      } else {
        errorMessage = error.message;
      }
    }
    
    return NextResponse.json(
      { 
        error: "Failed to fetch metrics",
        detail: errorMessage
      },
      { status: 500 }
    );
  }
}

