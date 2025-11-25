"use client";

import { useState, useCallback } from "react";
import { validateChatId, validateBotToken } from "../utils/validators";

export function useTelegramSettings() {
  const [telegramChatId, setTelegramChatId] = useState("");
  const [telegramBotToken, setTelegramBotToken] = useState("");
  const [isTelegramConfigured, setIsTelegramConfigured] = useState(false);
  const [isEditingTelegram, setIsEditingTelegram] = useState(true);
  const [telegramChatIdError, setTelegramChatIdError] = useState<string>("");
  const [telegramBotTokenError, setTelegramBotTokenError] = useState<string>("");
  const [testing, setTesting] = useState(false);

  // Обёртки для установки значений с валидацией
  const handleChatIdChange = useCallback((value: string) => {
    setTelegramChatId(value);
    setTelegramChatIdError(validateChatId(value));
  }, []);

  const handleBotTokenChange = useCallback((value: string) => {
    setTelegramBotToken(value);
    setTelegramBotTokenError(validateBotToken(value));
  }, []);

  // Валидация при потере фокуса
  const validateChatIdOnBlur = useCallback((value: string) => {
    setTelegramChatIdError(validateChatId(value));
  }, []);

  const validateBotTokenOnBlur = useCallback((value: string) => {
    setTelegramBotTokenError(validateBotToken(value));
  }, []);

  // Тестирование подключения
  const testTelegramConnection = useCallback(async (userLogin: string): Promise<{ success: boolean; message: string }> => {
    if (!userLogin || !telegramBotToken || !telegramChatId) {
      return {
        success: false,
        message: "Заполните Chat ID и Bot Token перед отправкой теста"
      };
    }

    // Валидация перед отправкой
    const chatIdError = validateChatId(telegramChatId);
    const botTokenError = validateBotToken(telegramBotToken);
    
    setTelegramChatIdError(chatIdError);
    setTelegramBotTokenError(botTokenError);
    
    if (chatIdError || botTokenError) {
      return {
        success: false,
        message: "Исправьте ошибки в полях перед отправкой теста"
      };
    }

    setTesting(true);
    
    try {
      const res = await fetch(`/api/users/${userLogin}/test`, {
        method: "POST"
      });
      
      if (res.ok) {
        return {
          success: true,
          message: "Тестовое сообщение успешно отправлено! Проверьте Telegram."
        };
      } else {
        const error = await res.json();
        return {
          success: false,
          message: error.detail || "Ошибка отправки тестового сообщения"
        };
      }
    } catch (err) {
      console.error(err);
      return {
        success: false,
        message: "Ошибка при отправке тестового сообщения"
      };
    } finally {
      setTesting(false);
    }
  }, [telegramBotToken, telegramChatId]);

  return {
    // Состояния
    telegramChatId,
    telegramBotToken,
    isTelegramConfigured,
    isEditingTelegram,
    telegramChatIdError,
    telegramBotTokenError,
    testing,
    // Сеттеры
    setTelegramChatId: handleChatIdChange,
    setTelegramBotToken: handleBotTokenChange,
    setIsTelegramConfigured,
    setIsEditingTelegram,
    setTelegramChatIdError,
    setTelegramBotTokenError,
    // Валидация
    validateChatIdOnBlur,
    validateBotTokenOnBlur,
    // Функции
    testTelegramConnection,
  };
}

