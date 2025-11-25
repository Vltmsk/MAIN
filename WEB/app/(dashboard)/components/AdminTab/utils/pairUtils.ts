/**
 * Утилиты для работы с парами бирж
 */

/**
 * Получает список пар для указанной биржи и рынка
 * @param exchange - название биржи (binance, bybit, bitget, gate, hyperliquid)
 * @param market - тип рынка (spot или futures)
 * @returns массив строк с названиями пар
 */
export const getPairsForExchange = (exchange: string, market: "spot" | "futures"): string[] => {
  if (exchange === "binance" && market === "spot") {
    return ["BTC", "ETH", "USDT", "BNB", "AUD", "TUSD", "BRL", "GBP", "USDC", "TRX", "EUR", "BIDR", "DOGE", "TRY", "FDUSD", "AEUR"];
  }
  if (exchange === "binance" && market === "futures") {
    return ["USDT", "USDC", "BTC"];
  }
  if (exchange === "bybit" && market === "spot") {
    return ["USDT", "ETH", "BTC", "USDC", "EUR"];
  }
  if (exchange === "bybit" && market === "futures") {
    return ["USDT"];
  }
  if (exchange === "bitget" && market === "spot") {
    return ["USDT"];
  }
  if (exchange === "bitget" && market === "futures") {
    return ["USDT"];
  }
  if (exchange === "gate" && market === "spot") {
    return ["USDT"];
  }
  if (exchange === "gate" && market === "futures") {
    return ["USDT"];
  }
  if (exchange === "hyperliquid" && market === "spot") {
    return ["USDC"];
  }
  if (exchange === "hyperliquid" && market === "futures") {
    return ["USDC"];
  }
  return [];
};

