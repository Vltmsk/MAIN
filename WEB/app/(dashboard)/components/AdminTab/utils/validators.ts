/**
 * Утилиты валидации для AdminTab
 */

/**
 * Валидация Bot Token
 * @param token - токен бота для проверки
 * @returns строка с ошибкой или пустая строка, если валидация прошла
 */
export const validateBotToken = (token: string): string => {
  if (!token.trim()) {
    return ""; // Пустое поле - не ошибка
  }
  
  // Формат: число:буквы_и_цифры
  // Пример: 1234567890:ABCdefGHIjkIMNOpqrsTUVwxyz
  // Число: от 8 до 12 цифр, затем двоеточие, затем строка из букв, цифр, подчёркиваний и дефисов (от 30 до 40 символов)
  const botTokenRegex = /^\d{8,12}:[A-Za-z0-9_-]{30,40}$/;
  
  if (!botTokenRegex.test(token)) {
    return "Неверный формат Bot Token. Формат: число:буквы (например: 1234567890:ABCdefGHIjkIMNOpqrsTUVwxyz)";
  }
  
  return "";
};

/**
 * Валидация Chat ID
 * @param chatId - Chat ID для проверки
 * @returns строка с ошибкой или пустая строка, если валидация прошла
 */
export const validateChatId = (chatId: string): string => {
  if (!chatId.trim()) {
    return ""; // Пустое поле - не ошибка
  }
  
  // Chat ID - это число (может быть отрицательным для групп)
  // Обычно от 8 до 11 цифр, но может быть больше
  const chatIdRegex = /^-?\d{8,20}$/;
  
  if (!chatIdRegex.test(chatId)) {
    return "Неверный формат Chat ID. Chat ID должен быть числом от 8 до 20 цифр (например: 123456789 для личных чатов или -1001234567890 для групп/каналов). Разверните инструкцию ниже, чтобы узнать, как получить Chat ID.";
  }
  
  return "";
};

