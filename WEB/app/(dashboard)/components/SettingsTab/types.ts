/**
 * Типы для SettingsTab
 */

export type ConditionalTemplate = {
  name?: string;
  description?: string;
  enabled?: boolean;
  useGlobalFilters?: boolean; // По умолчанию true, если отсутствует (обратная совместимость)
  conditions: Array<{
    type: "volume" | "delta" | "series" | "symbol" | "wick_pct" | "exchange_market" | "direction";
    value?: number;
    valueMin?: number;
    valueMax?: number | null;
    count?: number;
    timeWindowSeconds?: number;
    symbol?: string;
    exchange_market?: string; // Формат: "exchange_market" (например, "binance_spot", "bybit_futures")
    direction?: "up" | "down";
    // Старые поля для обратной совместимости (deprecated)
    exchange?: string;
    market?: "spot" | "futures" | "linear";
  }>;
  template: string;
  chatId?: string;
};

export interface SettingsTabProps {
  userLogin: string;
}

