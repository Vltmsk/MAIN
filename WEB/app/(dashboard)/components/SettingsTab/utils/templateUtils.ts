/**
 * Утилиты для работы с шаблонами сообщений
 */

import { placeholderMap, reversePlaceholderMap } from "./placeholderMap";

/**
 * Преобразует понятные названия плейсхолдеров в технические ключи
 * @param template - шаблон с понятными названиями
 * @returns шаблон с техническими ключами
 */
export const convertToTechnicalKeys = (template: string): string => {
  let result = template;
  Object.entries(placeholderMap).forEach(([friendly, technical]) => {
    result = result.replace(new RegExp(friendly.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'g'), technical);
  });
  return result;
};

/**
 * Преобразует технические ключи в понятные названия плейсхолдеров
 * @param template - шаблон с техническими ключами
 * @returns шаблон с понятными названиями
 */
export const convertToFriendlyKeys = (template: string): string => {
  let result = template;
  Object.entries(reversePlaceholderMap).forEach(([technical, friendly]) => {
    result = result.replace(new RegExp(technical.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'g'), friendly);
  });
  return result;
};

/**
 * Генерирует превью сообщения с примерами значений
 * @param template - шаблон сообщения
 * @returns превью с подставленными примерами значений
 */
export const generateMessagePreview = (template: string): string => {
  if (!template || !template.trim()) {
    return "";
  }

  // Примеры значений для превью
  const exampleValues: Record<string, string> = {
    "{delta_formatted}": "5.23%",
    "{volume_formatted}": "1.5K$",
    "{wick_formatted}": "45.2%",
    "{timestamp}": "1699123456789",
    "{direction}": "⬆️",
    "{exchange_market}": "BINANCE | SPOT",
    "{exchange}": "BINANCE",
    "{symbol}": "BTC-USDT",
    "{market}": "SPOT",
    "{time}": "2024-01-15 14:30:25",
    // Friendly names (для поддержки вставок из редактора)
    "[[Дельта стрелы]]": "5.23%",
    "[[Объём стрелы]]": "1.5K$",
    "[[Тень свечи]]": "45.2%",
    "[[Временная метка]]": "1699123456789",
    "[[Направление]]": "⬆️",
    "[[Биржа и тип рынка]]": "BINANCE | SPOT",
    "[[Торговая пара]]": "BTC-USDT",
    "[[Время детекта]]": "2024-01-15 14:30:25",
  };

  // Конвертируем friendly names в technical keys для замены
  let preview = convertToTechnicalKeys(template);

  // Заменяем все плейсхолдеры на примеры значений
  // Важно: сначала заменяем технические ключи, затем friendly names
  Object.entries(exampleValues).forEach(([placeholder, value]) => {
    // Экранируем специальные символы для регулярного выражения
    const escapedPlaceholder = placeholder.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    // Заменяем все вхождения плейсхолдера на пример значения
    preview = preview.replace(new RegExp(escapedPlaceholder, 'g'), value);
  });

  // Очищаем лишние пробелы и переносы строк
  preview = preview.trim();

  return preview;
};

