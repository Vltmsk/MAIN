/**
 * Утилиты для работы со статусами пользователей
 */

import { AdminUser } from "../types";

/**
 * Проверяет, является ли числовое значение ненулевым
 */
const hasNonZeroNumericValue = (value: unknown): boolean => {
  if (typeof value === "number") {
    return value !== 0;
  }
  if (typeof value === "string") {
    const normalized = value.replace(/\s+/g, "").replace(/,/g, ".");
    if (!normalized) return false;
    const numeric = Number(normalized);
    if (!Number.isFinite(numeric)) {
      return false;
    }
    return numeric !== 0;
  }
  return false;
};

/**
 * Рекурсивно проверяет наличие ненулевых пороговых значений
 */
const hasNonZeroThresholds = (input: unknown): boolean => {
  if (!input) return false;

  if (Array.isArray(input)) {
    return input.some((item) => {
      if (typeof item === "boolean") return false;
      if (typeof item === "object" && item !== null) {
        return hasNonZeroThresholds(item);
      }
      return hasNonZeroNumericValue(item);
    });
  }

  if (typeof input === "object") {
    return Object.entries(input as Record<string, unknown>).some(([key, value]) => {
      if (key === "enabled") return false;
      if (typeof value === "boolean") return false;
      if (value && typeof value === "object") {
        return hasNonZeroThresholds(value);
      }
      return hasNonZeroNumericValue(value);
    });
  }

  return hasNonZeroNumericValue(input);
};

/**
 * Получает статус пользователя (активность Telegram и настроек)
 * @param user - пользователь для проверки
 * @returns объект с флагами telegramActive и settingsActive
 */
export const getAdminUserStatus = (user: AdminUser) => {
  const hasToken = Boolean(user.tg_token && user.tg_token.trim().length > 0);
  const hasChat = Boolean(user.chat_id && user.chat_id.trim().length > 0);
  const telegramActive = user.has_telegram || (hasToken && hasChat);

  let settingsActive = false;
  const raw = user.options_json;

  if (raw) {
    try {
      const trimmed = raw.trim();
      if (trimmed.length === 0 || trimmed === "{}") {
        settingsActive = false;
      } else {
        const opts = JSON.parse(trimmed);
        const pairSettingsActive = hasNonZeroThresholds(opts?.pairSettings);
        settingsActive = Boolean(pairSettingsActive);
      }
    } catch (e) {
      console.warn("[AdminTab] Невозможно распарсить options_json", e);
      settingsActive = true;
    }
  }

  return { telegramActive, settingsActive };
};

