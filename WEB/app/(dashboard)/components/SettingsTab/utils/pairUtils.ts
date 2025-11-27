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
    return ["BTC", "ETH", "USDT", "BNB", "USD", "TUSD", "BRL", "USDC", "TRX", "EUR", "DOGE", "FDUSD"];
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

/**
 * Получает базовую валюту для биржи и рынка (если только одна пара)
 * @param exchange - название биржи
 * @param market - тип рынка
 * @returns название валюты или null, если пар несколько
 */
export const getQuoteCurrencyForExchange = (exchange: string, market: "spot" | "futures"): string | null => {
  const pairs = getPairsForExchange(exchange, market);
  if (pairs.length === 1) {
    return pairs[0];
  }
  return null;
};

/**
 * Определяет, нужно ли показывать все пары сразу в таблице
 * @param exchange - название биржи
 * @param market - тип рынка
 * @returns true, если нужно показывать все пары в таблице
 */
export const shouldShowPairsImmediately = (exchange: string, market: "spot" | "futures"): boolean => {
  return (exchange === "binance" && (market === "spot" || market === "futures")) ||
         (exchange === "bybit" && market === "spot");
};

