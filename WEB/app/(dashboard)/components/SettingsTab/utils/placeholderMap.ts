/**
 * Маппинг между понятными названиями и техническими ключами для плейсхолдеров
 */

export const placeholderMap: Record<string, string> = {
  "[[Дельта стрелы]]": "{delta_formatted}",
  "[[Направление]]": "{direction}",
  "[[Биржа и тип рынка]]": "{exchange_market}",
  "[[Биржа и тип рынка (коротко)]]": "{exchange_market_short}",
  "[[Торговая пара]]": "{symbol}",
  "[[Объём стрелы]]": "{volume_formatted}",
  "[[Тень свечи]]": "{wick_formatted}",
  "[[Время детекта]]": "{time}",
  "[[Временная метка]]": "{timestamp}",
};

/**
 * Обратный маппинг (технические ключи -> понятные названия)
 */
export const reversePlaceholderMap: Record<string, string> = Object.fromEntries(
  Object.entries(placeholderMap).map(([key, value]) => [value, key])
);

