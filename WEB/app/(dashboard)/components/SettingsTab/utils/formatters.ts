/**
 * Утилиты форматирования
 */

/**
 * Форматирует число в компактном виде с разделителями тысяч
 * @param value - число в виде строки
 * @returns отформатированное число
 */
export const formatNumberCompact = (value: string): string => {
  if (!value) return "0";
  const num = Number(value);
  if (Number.isNaN(num)) return value;
  return new Intl.NumberFormat("ru-RU").format(num);
};

