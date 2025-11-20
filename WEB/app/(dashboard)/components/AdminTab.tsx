"use client";

import { useEffect, useState } from "react";

// Типы
type AdminUser = {
  user: string;
  has_telegram: boolean;
  options_json?: string;
  tg_token?: string;
  chat_id?: string;
};

type AdminUserSettings = {
  user: string;
  tg_token: string;
  chat_id: string;
  options_json?: string;
};

type ErrorLog = {
  id: number;
  timestamp: string;
  exchange?: string;
  error_type: string;
  error_message: string;
  connection_id?: string;
  market?: string;
  symbol?: string;
  stack_trace?: string;
};

interface AdminTabProps {
  userLogin: string;
  isAdmin: boolean;
  activeTab: string;
}

export default function AdminTab({ userLogin, isAdmin, activeTab }: AdminTabProps) {
  // Состояния для админ панели
  const [adminUsers, setAdminUsers] = useState<AdminUser[]>([]);
  const [adminForm, setAdminForm] = useState<string>(""); // Только имя пользователя
  const [adminMsg, setAdminMsg] = useState("");
  const [adminLoading, setAdminLoading] = useState(false);
  const [selectedUserSettings, setSelectedUserSettings] = useState<AdminUserSettings | null>(null);
  const [deletingGlobalStats, setDeletingGlobalStats] = useState(false);
  
  // Состояния для редактирования настроек бирж в админ панели
  const [adminExchangeFilters, setAdminExchangeFilters] = useState<Record<string, boolean>>({
    binance: true,
    bybit: true,
    bitget: true,
    gate: true,
    hyperliquid: true,
  });
  const [adminExpandedExchanges, setAdminExpandedExchanges] = useState<Record<string, boolean>>({});
  const [adminExchangeSettings, setAdminExchangeSettings] = useState<Record<string, {
    spot: { enabled: boolean; delta: string; volume: string; shadow: string };
    futures: { enabled: boolean; delta: string; volume: string; shadow: string };
  }>>({
    binance: { spot: { enabled: true, delta: "0", volume: "0", shadow: "0" }, futures: { enabled: true, delta: "0", volume: "0", shadow: "0" } },
    bybit: { spot: { enabled: true, delta: "0", volume: "0", shadow: "0" }, futures: { enabled: true, delta: "0", volume: "0", shadow: "0" } },
    bitget: { spot: { enabled: true, delta: "0", volume: "0", shadow: "0" }, futures: { enabled: true, delta: "0", volume: "0", shadow: "0" } },
    gate: { spot: { enabled: true, delta: "0", volume: "0", shadow: "0" }, futures: { enabled: true, delta: "0", volume: "0", shadow: "0" } },
    hyperliquid: { spot: { enabled: true, delta: "0", volume: "0", shadow: "0" }, futures: { enabled: true, delta: "0", volume: "0", shadow: "0" } },
  });
  const [adminPairSettings, setAdminPairSettings] = useState<Record<string, { enabled: boolean; delta: string; volume: string; shadow: string }>>({});
  const [adminOpenPairs, setAdminOpenPairs] = useState<Record<string, boolean>>({});

  // Состояния для логов ошибок
  const [errorLogs, setErrorLogs] = useState<ErrorLog[]>([]);
  const [errorLogsLoading, setErrorLogsLoading] = useState(false);
  const [errorLogsFilter, setErrorLogsFilter] = useState<{
    exchange?: string;
    error_type?: string;
    limit: number;
  }>({ limit: 100 });

  // Функция для получения пар для биржи
  const getPairsForExchange = (exchange: string, market: "spot" | "futures"): string[] => {
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

  // Валидация Bot Token
  const validateBotToken = (token: string): string => {
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

  // Валидация Chat ID
  const validateChatId = (chatId: string): string => {
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

  // Получение статуса пользователя
  const getAdminUserStatus = (user: AdminUser) => {
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

          const exchangeSettingsActive = hasNonZeroThresholds(opts?.exchangeSettings);
          const pairSettingsActive = hasNonZeroThresholds(opts?.pairSettings);

          settingsActive = Boolean(exchangeSettingsActive || pairSettingsActive);
        }
      } catch (e) {
        console.warn("[AdminTab] Невозможно распарсить options_json", e);
        settingsActive = true;
      }
    }

    return { telegramActive, settingsActive };
  };

  // Админ панель - загрузка пользователей
  const fetchAdminUsers = async () => {
    try {
      const res = await fetch("/api/users");
      const data = await res.json();
      setAdminUsers(data.users || []);
    } catch (err) {
      console.error("Ошибка загрузки пользователей:", err);
      setAdminMsg("Ошибка загрузки пользователей");
      setTimeout(() => setAdminMsg(""), 3000);
    }
  };

  // Админ панель - создание нового пользователя
  const createAdminUser = async () => {
    if (!adminForm.trim()) {
      setAdminMsg("Введите имя пользователя");
      setTimeout(() => setAdminMsg(""), 2000);
      return;
    }

    setAdminLoading(true);
    try {
      // Кодируем имя пользователя для URL (важно для кириллицы и специальных символов)
      const trimmedUserName = adminForm.trim();
      const encodedUserName = encodeURIComponent(trimmedUserName);
      const res = await fetch(`/api/users/${encodedUserName}/settings`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          tg_token: "",
          chat_id: "",
          options_json: JSON.stringify({
            thresholds: { delta_pct: 1.0, volume_usdt: 10000.0, wick_pct: 50.0 },
            exchanges: { gate: true, binance: true, bitget: true, bybit: true, hyperliquid: true },
          }),
        }),
      });

      if (!res.ok) {
        const error = await res.json();
        throw new Error(error.detail || "Ошибка создания пользователя");
      }

      setAdminMsg(`Пользователь "${trimmedUserName}" успешно создан!`);
      setTimeout(() => setAdminMsg(""), 3000);
      setAdminForm(""); // Очищаем форму
      fetchAdminUsers();
    } catch (err) {
      console.error("Ошибка создания пользователя:", err);
      setAdminMsg(err instanceof Error ? err.message : "Ошибка создания пользователя");
      setTimeout(() => setAdminMsg(""), 3000);
    } finally {
      setAdminLoading(false);
    }
  };

  // Админ панель - загрузка настроек пользователя
  const loadUserSettings = async (userName: string) => {
    setAdminLoading(true);
    try {
      const res = await fetch(`/api/users/${userName}`);
      if (res.ok) {
        const data = await res.json();
        // Если options_json пустой или null, создаем базовую структуру
        let optionsJson = data.options_json || "{}";
        if (!optionsJson || optionsJson.trim() === "") {
          optionsJson = JSON.stringify({
            thresholds: { delta_pct: 1.0, volume_usdt: 10000.0, wick_pct: 50.0 },
            exchanges: { gate: true, binance: true, bitget: true, bybit: true, hyperliquid: true },
          });
        }
        setSelectedUserSettings({
          user: data.user,
          tg_token: data.tg_token || "",
          chat_id: data.chat_id || "",
          options_json: optionsJson,
        });
        
        // Загружаем настройки бирж в состояния для редактирования
        try {
          const options = JSON.parse(optionsJson);
          
          // Загружаем фильтры по биржам
          if (options.exchanges && typeof options.exchanges === "object") {
            setAdminExchangeFilters({
              binance: options.exchanges.binance !== false && options.exchanges.binance !== undefined ? options.exchanges.binance : true,
              bybit: options.exchanges.bybit !== false && options.exchanges.bybit !== undefined ? options.exchanges.bybit : true,
              bitget: options.exchanges.bitget !== false && options.exchanges.bitget !== undefined ? options.exchanges.bitget : true,
              gate: options.exchanges.gate !== false && options.exchanges.gate !== undefined ? options.exchanges.gate : true,
              hyperliquid: options.exchanges.hyperliquid !== false && options.exchanges.hyperliquid !== undefined ? options.exchanges.hyperliquid : true,
            });
          } else {
            setAdminExchangeFilters({
              binance: true,
              bybit: true,
              bitget: true,
              gate: true,
              hyperliquid: true,
            });
          }
          
          // Загружаем настройки бирж (Spot/Futures)
          if (options.exchangeSettings) {
            setAdminExchangeSettings((prevSettings) => {
              const merged = { ...prevSettings };
              Object.keys(options.exchangeSettings).forEach((exchange) => {
                if (merged[exchange]) {
                  merged[exchange] = {
                    spot: {
                      ...merged[exchange].spot,
                      ...options.exchangeSettings[exchange].spot,
                    },
                    futures: {
                      ...merged[exchange].futures,
                      ...options.exchangeSettings[exchange].futures,
                    },
                  };
                } else {
                  merged[exchange] = options.exchangeSettings[exchange];
                }
              });
              return merged;
            });
          }
          
          // Загружаем настройки пар
          if (options.pairSettings) {
            const migratedPairSettings: Record<string, { enabled: boolean; delta: string; volume: string; shadow: string }> = {};
            Object.entries(options.pairSettings).forEach(([key, value]: [string, any]) => {
              if (value && typeof value === 'object' && !('enabled' in value)) {
                migratedPairSettings[key] = {
                  enabled: true,
                  delta: value.delta || "0",
                  volume: value.volume || "0",
                  shadow: value.shadow || "0"
                };
              } else {
                migratedPairSettings[key] = value;
              }
            });
            setAdminPairSettings(migratedPairSettings);
          }
        } catch (e) {
          console.error("Ошибка парсинга options_json при загрузке:", e);
        }
      } else {
        throw new Error("Ошибка загрузки настроек");
      }
    } catch (err) {
      console.error("Ошибка загрузки настроек пользователя:", err);
      setAdminMsg("Ошибка загрузки настроек");
      setTimeout(() => setAdminMsg(""), 2000);
      setSelectedUserSettings(null);
    } finally {
      setAdminLoading(false);
    }
  };

  // Админ панель - удаление пользователя
  const deleteAdminUser = async (userName: string) => {
    // Убираем пробелы в начале и конце имени пользователя
    const trimmedUserName = userName.trim();
    
    if (!trimmedUserName) {
      setAdminMsg("Имя пользователя не может быть пустым");
      setTimeout(() => setAdminMsg(""), 3000);
      return;
    }
    
    // Запрещаем удаление системных пользователей "Stats" и "Влад"
    const lowerUserName = trimmedUserName.toLowerCase();
    if (lowerUserName === "stats" || lowerUserName === "влад") {
      setAdminMsg(`Нельзя удалить системного пользователя '${trimmedUserName}'`);
      setTimeout(() => setAdminMsg(""), 3000);
      return;
    }

    if (!confirm(`Удалить пользователя "${trimmedUserName}"?`)) return;

    setAdminLoading(true);
    try {
      // Кодируем имя пользователя для URL (важно для кириллицы и специальных символов)
      const encodedUserName = encodeURIComponent(trimmedUserName);
      const res = await fetch(`/api/users/${encodedUserName}/delete`, {
        method: "DELETE",
      });

      if (!res.ok) {
        // Пытаемся получить детальное сообщение об ошибке
        let errorMessage = "Ошибка удаления";
        try {
          const errorData = await res.json();
          errorMessage = errorData.error || errorData.detail || errorMessage;
        } catch {
          // Если не удалось распарсить JSON, используем стандартное сообщение
        }
        throw new Error(errorMessage);
      }

      const data = await res.json();
      setAdminMsg(data.message || "Пользователь удалён");
      setTimeout(() => setAdminMsg(""), 2000);
      fetchAdminUsers();
      if (selectedUserSettings?.user === trimmedUserName) {
        setSelectedUserSettings(null);
      }
    } catch (err) {
      console.error("Ошибка удаления:", err);
      const errorMessage = err instanceof Error ? err.message : "Ошибка удаления";
      setAdminMsg(errorMessage);
      setTimeout(() => setAdminMsg(""), 3000);
    } finally {
      setAdminLoading(false);
    }
  };

  // Админ панель - удаление рыночной статистики (пользователь "Stats")
  const deleteGlobalStats = async () => {
    // Подтверждение удаления
    const confirmed = window.confirm(
      "Вы уверены, что хотите удалить всю рыночную статистику стрел (пользователь 'Stats')? Это действие нельзя отменить."
    );
    
    if (!confirmed) return;
    
    setDeletingGlobalStats(true);
    try {
      const res = await fetch(`/api/users/Stats/spikes`, {
        method: "DELETE",
      });
      
      if (res.ok) {
        const data = await res.json();
        setAdminMsg(`Рыночная статистика успешно удалена. Удалено записей: ${data.deleted_count || 0}`);
        setTimeout(() => setAdminMsg(""), 5000);
      } else {
        const errorData = await res.json().catch(() => ({ error: "Неизвестная ошибка" }));
        setAdminMsg(`Ошибка при удалении рыночной статистики: ${errorData.error || errorData.detail || "Неизвестная ошибка"}`);
        setTimeout(() => setAdminMsg(""), 5000);
      }
    } catch (error) {
      console.error("Ошибка при удалении рыночной статистики:", error);
      setAdminMsg("Ошибка при удалении рыночной статистики. Попробуйте позже.");
      setTimeout(() => setAdminMsg(""), 5000);
    } finally {
      setDeletingGlobalStats(false);
    }
  };

  // Админ панель - копирование значений порогов во все биржи
  const copyThresholdsToAllExchanges = () => {
    if (!selectedUserSettings) return;
    
    try {
      // Получаем актуальные значения порогов из текущих настроек
      const options = selectedUserSettings.options_json 
        ? JSON.parse(selectedUserSettings.options_json) 
        : {};
      const thresholds = options.thresholds || { delta_pct: 1.0, volume_usdt: 10000.0, wick_pct: 50.0 };
      
      // Получаем значения из порогов (конвертируем в строки для совместимости с полями)
      const deltaValue = String(thresholds.delta_pct || 0);
      const volumeValue = String(thresholds.volume_usdt || 0);
      const shadowValue = String(thresholds.wick_pct || 0);
      
      // Список всех бирж
      const exchanges = ["binance", "bybit", "bitget", "gate", "hyperliquid"];
      
      // Обновляем настройки для всех бирж, сохраняя состояние enabled
      const updatedSettings = { ...adminExchangeSettings };
      
      exchanges.forEach((exchange) => {
        const currentSettings = adminExchangeSettings[exchange] || {
          spot: { enabled: true, delta: "0", volume: "0", shadow: "0" },
          futures: { enabled: true, delta: "0", volume: "0", shadow: "0" }
        };
        
        updatedSettings[exchange] = {
          spot: {
            ...currentSettings.spot,
            delta: deltaValue,
            volume: volumeValue,
            shadow: shadowValue,
          },
          futures: {
            ...currentSettings.futures,
            delta: deltaValue,
            volume: volumeValue,
            shadow: shadowValue,
          },
        };
      });
      
      setAdminExchangeSettings(updatedSettings);
      setAdminMsg("Значения порогов скопированы во все биржи (Spot и Futures)!");
      setTimeout(() => setAdminMsg(""), 3000);
    } catch (e) {
      console.error("Ошибка при копировании значений:", e);
      setAdminMsg("Ошибка при копировании значений");
      setTimeout(() => setAdminMsg(""), 3000);
    }
  };

  // Админ панель - сохранение настроек пользователя
  const saveAdminUserSettings = async () => {
    if (!selectedUserSettings) return;

    setAdminLoading(true);
    try {
      // Получаем текущие настройки из options_json и обновляем их
      let options: any = {};
      try {
        options = selectedUserSettings.options_json ? JSON.parse(selectedUserSettings.options_json) : {};
      } catch (e) {
        options = {};
      }
      
      // Обновляем настройки из состояний редактирования
      options.exchanges = adminExchangeFilters;
      options.exchangeSettings = adminExchangeSettings;
      options.pairSettings = adminPairSettings;
      
      // Сохраняем пороги детектора (они уже должны быть в options из selectedUserSettings.options_json,
      // но убеждаемся, что они есть, иначе используем дефолтные значения)
      if (!options.thresholds) {
        options.thresholds = { delta_pct: 1.0, volume_usdt: 10000.0, wick_pct: 50.0 };
      }
      // Пороги уже обновлены через onChange в UI и находятся в options из selectedUserSettings.options_json
      
      const optionsJson = JSON.stringify(options);

      const res = await fetch(`/api/users/${selectedUserSettings.user}/settings`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          tg_token: selectedUserSettings.tg_token || "",
          chat_id: selectedUserSettings.chat_id || "",
          options_json: optionsJson,
        }),
      });

      if (!res.ok) {
        const error = await res.json();
        throw new Error(error.detail || "Ошибка сохранения");
      }

      setAdminMsg("Настройки успешно сохранены!");
      setTimeout(() => setAdminMsg(""), 3000);
      fetchAdminUsers(); // Обновляем список пользователей
      // Обновляем текущие настройки, чтобы они соответствовали сохраненным
      setSelectedUserSettings({
        ...selectedUserSettings,
        options_json: optionsJson,
      });
    } catch (err) {
      console.error("Ошибка сохранения настроек:", err);
      setAdminMsg(err instanceof Error ? err.message : "Ошибка сохранения настроек");
      setTimeout(() => setAdminMsg(""), 3000);
    } finally {
      setAdminLoading(false);
    }
  };

  // Админ панель - загрузка логов ошибок
  const fetchErrorLogs = async () => {
    setErrorLogsLoading(true);
    try {
      const params = new URLSearchParams();
      if (errorLogsFilter.exchange) {
        params.append("exchange", errorLogsFilter.exchange);
      }
      if (errorLogsFilter.error_type) {
        params.append("error_type", errorLogsFilter.error_type);
      }
      params.append("limit", errorLogsFilter.limit.toString());

      const res = await fetch(`/api/errors?${params.toString()}`);
      if (res.ok) {
        const data = await res.json();
        setErrorLogs(data.errors || []);
      } else {
        throw new Error("Ошибка загрузки логов");
      }
    } catch (err) {
      console.error("Ошибка загрузки логов:", err);
      setErrorLogs([]);
    } finally {
      setErrorLogsLoading(false);
    }
  };

  // Удаление одного лога ошибки
  const deleteError = async (errorId: number) => {
    if (!isAdmin) {
      alert("Удаление логов ошибок доступно только для пользователя 'Влад'");
      return;
    }

    if (!confirm("Вы уверены, что хотите удалить этот лог ошибки?")) {
      return;
    }

    try {
      const params = new URLSearchParams();
      params.append("error_id", errorId.toString());
      params.append("user", userLogin);

      const res = await fetch(`/api/errors?${params.toString()}`, {
        method: "DELETE",
      });

      if (res.ok) {
        // Обновляем список логов
        fetchErrorLogs();
      } else {
        const data = await res.json();
        alert(data.error || "Ошибка при удалении лога");
      }
    } catch (err) {
      console.error("Ошибка удаления лога:", err);
      alert("Ошибка при удалении лога");
    }
  };

  // Удаление всех логов ошибок
  const deleteAllErrors = async () => {
    if (!isAdmin) {
      alert("Удаление всех логов ошибок доступно только для пользователя 'Влад'");
      return;
    }

    if (!confirm("Вы уверены, что хотите удалить ВСЕ логи ошибок? Это действие нельзя отменить.")) {
      return;
    }

    try {
      const params = new URLSearchParams();
      params.append("user", userLogin);

      const res = await fetch(`/api/errors?${params.toString()}`, {
        method: "DELETE",
      });

      if (res.ok) {
        const data = await res.json();
        alert(`Успешно удалено ${data.deleted_count || 0} логов ошибок`);
        // Обновляем список логов
        fetchErrorLogs();
      } else {
        const data = await res.json();
        alert(data.error || "Ошибка при удалении логов");
      }
    } catch (err) {
      console.error("Ошибка удаления всех логов:", err);
      alert("Ошибка при удалении логов");
    }
  };

  // Загрузка пользователей админ панели при переключении на вкладку
  useEffect(() => {
    if (activeTab === "admin" && isAdmin) {
      fetchAdminUsers();
      fetchErrorLogs();
    }
  }, [activeTab, isAdmin]);

  // Обновление логов при изменении фильтров
  useEffect(() => {
    if (activeTab === "admin" && isAdmin) {
      const timer = setTimeout(() => {
        fetchErrorLogs();
      }, 300); // Небольшая задержка для дебаунса
      return () => clearTimeout(timer);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [errorLogsFilter.exchange, errorLogsFilter.error_type, errorLogsFilter.limit]);

  return (
    <div className="mb-6 md:mb-8">
      {/* Заголовок и кнопка удаления статистики */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 mb-4">
        <div>
          <h1 className="text-2xl md:text-3xl font-bold text-white mb-2">Админ панель</h1>
          <p className="text-zinc-400">
            Управление пользователями системы
          </p>
        </div>
        {/* Кнопка удаления рыночной статистики */}
        <button
          onClick={deleteGlobalStats}
          disabled={deletingGlobalStats}
          className={`px-6 py-3 rounded-lg text-sm font-medium transition-colors ${
            deletingGlobalStats
              ? "bg-zinc-700 text-zinc-400 cursor-not-allowed"
              : "bg-red-600 hover:bg-red-700 text-white"
          }`}
          title="Удалить всю рыночную статистику стрел (пользователь 'Stats')"
        >
          {deletingGlobalStats ? (
            <span className="flex items-center gap-2">
              <span className="w-4 h-4 border-2 border-zinc-400 border-t-transparent rounded-full animate-spin"></span>
              Удаление...
            </span>
          ) : (
            "🗑️ Удалить рыночную статистику"
          )}
        </button>
      </div>

      {/* Уведомление админ панели по центру экрана */}
      {adminMsg && (
        <div className="fixed top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2 z-50">
          <div className="p-6 rounded-xl shadow-2xl max-w-md bg-emerald-500/95 text-white border-2 border-emerald-400">
            <p className="font-semibold text-lg">{adminMsg}</p>
          </div>
        </div>
      )}

      {/* Форма создания нового пользователя */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6 mb-8">
        <h2 className="text-xl font-bold text-white mb-4">Новый пользователь</h2>

        <div className="grid gap-4">
          <div>
            <label className="block text-sm font-medium text-zinc-300 mb-2">
              Имя пользователя
            </label>
            <input
              type="text"
              value={adminForm}
              onChange={(e) => setAdminForm(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  createAdminUser();
                }
              }}
              placeholder="Введите имя пользователя"
              className="w-full px-4 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            <p className="mt-2 text-xs text-zinc-500">
              Введите имя пользователя, чтобы дать разрешение на использование сайта
            </p>
          </div>

          <div className="flex gap-3 pt-2">
            <button
              onClick={createAdminUser}
              disabled={adminLoading}
              className="px-6 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {adminLoading ? "Создание..." : "Создать пользователя"}
            </button>
            <button
              onClick={() => setAdminForm("")}
              disabled={adminLoading}
              className="px-6 py-2 bg-gray-500 text-white rounded-lg hover:bg-gray-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Очистить
            </button>
          </div>
        </div>
      </div>

      {/* Список пользователей */}
      <div className="mb-8 bg-zinc-900 border border-zinc-800 rounded-xl p-6">
        <h2 className="text-xl font-bold text-white mb-4">
          Пользователи ({adminUsers.length})
        </h2>
        {adminUsers.length === 0 ? (
          <div className="text-zinc-600">Нет пользователей</div>
        ) : (
          <div className="space-y-2">
            {adminUsers.map((user) => {
              const statuses = getAdminUserStatus(user);
              const lowerUserName = user.user.trim().toLowerCase();
              const isSystemUser = lowerUserName === "stats" || lowerUserName === "влад";

              return (
                <div
                  key={user.user}
                  className="flex items-center justify-between p-3 bg-zinc-800 rounded-lg hover:bg-zinc-700 transition-colors"
                >
                  <div className="flex items-center gap-3">
                    <button
                      onClick={() => loadUserSettings(user.user)}
                      className="font-medium text-white hover:text-blue-400 transition-colors text-left"
                    >
                      {user.user}
                    </button>
                    {isSystemUser ? (
                      <span className="px-2 py-0.5 bg-blue-900/30 text-blue-400 border border-blue-500/40 rounded text-xs">
                        Системный
                      </span>
                    ) : (
                      <>
                        <span
                          className={`px-2 py-0.5 border rounded text-xs ${
                            statuses.telegramActive
                              ? "bg-emerald-500/20 text-emerald-300 border-emerald-400/60"
                              : "bg-red-500/20 text-red-300 border-red-500/50"
                          }`}
                        >
                          Telegram: {statuses.telegramActive ? "ON" : "OFF"}
                        </span>
                        <span
                          className={`px-2 py-0.5 border rounded text-xs ${
                            statuses.settingsActive
                              ? "bg-emerald-500/20 text-emerald-300 border-emerald-400/60"
                              : "bg-red-500/20 text-red-300 border-red-500/50"
                          }`}
                        >
                          Настройки: {statuses.settingsActive ? "ON" : "OFF"}
                        </span>
                      </>
                    )}
                  </div>
                  <button
                    onClick={() => deleteAdminUser(user.user)}
                    disabled={isSystemUser}
                    className="px-3 py-1 bg-red-500 text-white rounded hover:bg-red-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    Удалить
                  </button>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Панель настроек выбранного пользователя */}
      {selectedUserSettings && (
        <div className="mb-8 bg-zinc-900 border border-zinc-800 rounded-xl p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-xl font-bold text-white">
              Настройки: {selectedUserSettings.user}
            </h2>
            <button
              onClick={() => setSelectedUserSettings(null)}
              className="px-3 py-1 bg-zinc-700 text-white rounded hover:bg-zinc-600 transition-colors"
            >
              Закрыть
            </button>
          </div>

          <div className="space-y-4">
            {/* Telegram */}
            <div className="border-t border-zinc-700 pt-4">
              <h3 className="text-lg font-semibold text-white mb-3">Telegram</h3>
              <div className="grid md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm text-zinc-400 mb-1">Chat ID</label>
                  <input
                    type="text"
                    value={selectedUserSettings.chat_id || ""}
                    onChange={(e) =>
                      setSelectedUserSettings({
                        ...selectedUserSettings,
                        chat_id: e.target.value,
                      })
                    }
                    placeholder="Не настроен"
                    className="w-full px-4 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>
                <div>
                  <label className="block text-sm text-zinc-400 mb-1">Bot Token</label>
                  <input
                    type="text"
                    value={selectedUserSettings.tg_token || ""}
                    onChange={(e) =>
                      setSelectedUserSettings({
                        ...selectedUserSettings,
                        tg_token: e.target.value,
                      })
                    }
                    placeholder="Не настроен"
                    className="w-full px-4 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>
              </div>
            </div>

            {/* Настройки бирж */}
            <div className="border-t border-zinc-700 pt-4">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-lg font-semibold text-white">Фильтры по биржам</h3>
                <button
                  onClick={saveAdminUserSettings}
                  disabled={adminLoading}
                  className="px-4 py-2 bg-gradient-to-r from-emerald-500 to-emerald-600 hover:from-emerald-600 hover:to-emerald-700 text-white text-sm font-medium rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {adminLoading ? "Сохранение..." : "Сохранить изменения"}
                </button>
              </div>
              <p className="text-sm text-zinc-400 mb-4">Выберите биржи для мониторинга и настройте параметры</p>
              
              <div className="space-y-2">
                {["binance", "bybit", "bitget", "gate", "hyperliquid"].map((exchange) => {
                  const isExpanded = adminExpandedExchanges[exchange] || false;
                  const exchangeDisplayName = exchange === "gate" ? "Gate" : exchange === "hyperliquid" ? "Hyperliquid" : exchange.charAt(0).toUpperCase() + exchange.slice(1);
                  const settings = adminExchangeSettings[exchange] || { spot: { enabled: true, delta: "0", volume: "0", shadow: "0" }, futures: { enabled: true, delta: "0", volume: "0", shadow: "0" } };
                  
                  return (
                    <div key={exchange} className="bg-zinc-800 rounded-lg overflow-hidden">
                      {/* Заголовок биржи */}
                      <div className="flex items-center gap-3 p-4">
                        <div
                          className={`w-12 h-6 rounded-full transition-colors cursor-pointer ${
                            adminExchangeFilters[exchange] ? "bg-emerald-500" : "bg-zinc-600"
                          }`}
                          onClick={(e) => {
                            e.stopPropagation();
                            setAdminExchangeFilters({
                              ...adminExchangeFilters,
                              [exchange]: !adminExchangeFilters[exchange],
                            });
                          }}
                        >
                          <div className={`w-5 h-5 bg-white rounded-full transition-transform mt-0.5 ${
                            adminExchangeFilters[exchange] ? "translate-x-6" : "translate-x-1"
                          }`} />
                        </div>
                        <span
                          className="flex-1 text-white font-medium cursor-pointer hover:text-zinc-300 transition-colors"
                          onClick={() => {
                            setAdminExpandedExchanges({
                              ...adminExpandedExchanges,
                              [exchange]: !isExpanded,
                            });
                          }}
                        >
                          {exchangeDisplayName}
                        </span>
                        <svg
                          className={`w-5 h-5 text-zinc-400 transition-transform cursor-pointer ${
                            isExpanded ? "rotate-180" : ""
                          }`}
                          fill="none"
                          stroke="currentColor"
                          viewBox="0 0 24 24"
                          onClick={() => {
                            setAdminExpandedExchanges({
                              ...adminExpandedExchanges,
                              [exchange]: !isExpanded,
                            });
                          }}
                        >
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                        </svg>
                      </div>
                      
                      {/* Раскрывающийся контент */}
                      {isExpanded && (
                        <div className="px-4 pb-4 space-y-4">
                          {/* Spot секция */}
                          <div className="bg-zinc-900 rounded-lg p-4 space-y-4">
                            <div className="flex items-center justify-between">
                              <div>
                                <h3 className="text-white font-medium">Spot</h3>
                                <p className="text-sm text-zinc-400">Все торговые пары</p>
                              </div>
                              <div
                                className={`w-12 h-6 rounded-full transition-colors cursor-pointer ${
                                  settings.spot.enabled ? "bg-emerald-500" : "bg-zinc-600"
                                }`}
                                onClick={(e) => {
                                  e.stopPropagation();
                                  setAdminExchangeSettings({
                                    ...adminExchangeSettings,
                                    [exchange]: {
                                      ...settings,
                                      spot: { ...settings.spot, enabled: !settings.spot.enabled },
                                    },
                                  });
                                }}
                              >
                                <div className={`w-5 h-5 bg-white rounded-full transition-transform mt-0.5 ${
                                  settings.spot.enabled ? "translate-x-6" : "translate-x-1"
                                }`} />
                              </div>
                            </div>
                            
                            {!adminOpenPairs[`${exchange}_spot`] && (
                              <div className="grid grid-cols-3 gap-3">
                                <div>
                                  <label className="block text-xs text-zinc-400 mb-1">Дельта %</label>
                                  <input
                                    type="number"
                                    value={settings.spot.delta}
                                    onChange={(e) => {
                                      setAdminExchangeSettings({
                                        ...adminExchangeSettings,
                                        [exchange]: {
                                          ...settings,
                                          spot: { ...settings.spot, delta: e.target.value },
                                        },
                                      });
                                    }}
                                    className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                                  />
                                </div>
                                <div>
                                  <label className="block text-xs text-zinc-400 mb-1">Объём USDT</label>
                                  <input
                                    type="number"
                                    value={settings.spot.volume}
                                    onChange={(e) => {
                                      setAdminExchangeSettings({
                                        ...adminExchangeSettings,
                                        [exchange]: {
                                          ...settings,
                                          spot: { ...settings.spot, volume: e.target.value },
                                        },
                                      });
                                    }}
                                    className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                                  />
                                </div>
                                <div>
                                  <label className="block text-xs text-zinc-400 mb-1">Тень %</label>
                                  <input
                                    type="number"
                                    value={settings.spot.shadow}
                                    onChange={(e) => {
                                      setAdminExchangeSettings({
                                        ...adminExchangeSettings,
                                        [exchange]: {
                                          ...settings,
                                          spot: { ...settings.spot, shadow: e.target.value },
                                        },
                                      });
                                    }}
                                    className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                                  />
                                </div>
                              </div>
                            )}
                            
                            {/* Дополнительные пары для Spot (если есть) */}
                            {((exchange === "binance" || exchange === "bybit") && adminOpenPairs[`${exchange}_spot`]) && (
                              <div className="bg-zinc-950 rounded-lg p-4 border border-zinc-700">
                                <h4 className="text-sm font-medium text-white mb-4">Дополнительные пары для Spot</h4>
                                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                                  {getPairsForExchange(exchange, "spot").map((pair) => {
                                    const pairKey = `${exchange}_spot_${pair}`;
                                    const savedPairData = adminPairSettings[pairKey];
                                    const spotSettings = settings.spot;
                                    
                                    const pairData = savedPairData || {
                                      enabled: true,
                                      delta: spotSettings.delta || "0",
                                      volume: spotSettings.volume || "0",
                                      shadow: spotSettings.shadow || "0"
                                    };
                                    
                                    return (
                                      <div key={pair} className="bg-zinc-800 rounded-lg p-3 space-y-2">
                                        <div className="flex items-center justify-between mb-2">
                                          <div className="text-white font-medium text-sm">{pair}</div>
                                          <div
                                            className={`w-10 h-5 rounded-full transition-colors cursor-pointer ${
                                              pairData.enabled ? "bg-emerald-500" : "bg-zinc-600"
                                            }`}
                                            onClick={() => {
                                              setAdminPairSettings({
                                                ...adminPairSettings,
                                                [pairKey]: { ...pairData, enabled: !pairData.enabled },
                                              });
                                            }}
                                          >
                                            <div className={`w-4 h-4 bg-white rounded-full transition-transform mt-0.5 ${
                                              pairData.enabled ? "translate-x-5" : "translate-x-1"
                                            }`} />
                                          </div>
                                        </div>
                                        <div>
                                          <label className="block text-xs text-zinc-400 mb-1">Дельта %</label>
                                          <input
                                            type="number"
                                            value={pairData.delta}
                                            onChange={(e) => {
                                              setAdminPairSettings({
                                                ...adminPairSettings,
                                                [pairKey]: { ...pairData, delta: e.target.value },
                                              });
                                            }}
                                            className="w-full px-2 py-1 bg-zinc-900 border border-zinc-700 rounded text-white text-xs focus:outline-none focus:ring-1 focus:ring-emerald-500"
                                          />
                                        </div>
                                        <div>
                                          <label className="block text-xs text-zinc-400 mb-1">Объём USDT</label>
                                          <input
                                            type="number"
                                            value={pairData.volume}
                                            onChange={(e) => {
                                              setAdminPairSettings({
                                                ...adminPairSettings,
                                                [pairKey]: { ...pairData, volume: e.target.value },
                                              });
                                            }}
                                            className="w-full px-2 py-1 bg-zinc-900 border border-zinc-700 rounded text-white text-xs focus:outline-none focus:ring-1 focus:ring-emerald-500"
                                          />
                                        </div>
                                        <div>
                                          <label className="block text-xs text-zinc-400 mb-1">Тень %</label>
                                          <input
                                            type="number"
                                            value={pairData.shadow}
                                            onChange={(e) => {
                                              setAdminPairSettings({
                                                ...adminPairSettings,
                                                [pairKey]: { ...pairData, shadow: e.target.value },
                                              });
                                            }}
                                            className="w-full px-2 py-1 bg-zinc-900 border border-zinc-700 rounded text-white text-xs focus:outline-none focus:ring-1 focus:ring-emerald-500"
                                          />
                                        </div>
                                      </div>
                                    );
                                  })}
                                </div>
                              </div>
                            )}
                            
                            {(exchange === "binance" || exchange === "bybit") && (
                              <div className="flex justify-end">
                                <button
                                  onClick={() => {
                                    const key = `${exchange}_spot`;
                                    setAdminOpenPairs({
                                      ...adminOpenPairs,
                                      [key]: !adminOpenPairs[key],
                                    });
                                  }}
                                  className="px-3 py-1.5 bg-zinc-700 hover:bg-zinc-600 text-white text-sm font-medium rounded-lg transition-colors"
                                >
                                  {adminOpenPairs[`${exchange}_spot`] ? "Скрыть пары" : "Открыть дополнительные пары"}
                                </button>
                              </div>
                            )}
                          </div>
                          
                          {/* Futures секция */}
                          <div className="bg-zinc-900 rounded-lg p-4 space-y-4">
                            <div className="flex items-center justify-between">
                              <div>
                                <h3 className="text-white font-medium">Futures</h3>
                                <p className="text-sm text-zinc-400">Все торговые пары</p>
                              </div>
                              <div
                                className={`w-12 h-6 rounded-full transition-colors cursor-pointer ${
                                  settings.futures.enabled ? "bg-emerald-500" : "bg-zinc-600"
                                }`}
                                onClick={(e) => {
                                  e.stopPropagation();
                                  setAdminExchangeSettings({
                                    ...adminExchangeSettings,
                                    [exchange]: {
                                      ...settings,
                                      futures: { ...settings.futures, enabled: !settings.futures.enabled },
                                    },
                                  });
                                }}
                              >
                                <div className={`w-5 h-5 bg-white rounded-full transition-transform mt-0.5 ${
                                  settings.futures.enabled ? "translate-x-6" : "translate-x-1"
                                }`} />
                              </div>
                            </div>
                            
                            {!adminOpenPairs[`${exchange}_futures`] && (
                              <div className="grid grid-cols-3 gap-3">
                                <div>
                                  <label className="block text-xs text-zinc-400 mb-1">Дельта %</label>
                                  <input
                                    type="number"
                                    value={settings.futures.delta}
                                    onChange={(e) => {
                                      setAdminExchangeSettings({
                                        ...adminExchangeSettings,
                                        [exchange]: {
                                          ...settings,
                                          futures: { ...settings.futures, delta: e.target.value },
                                        },
                                      });
                                    }}
                                    className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                                  />
                                </div>
                                <div>
                                  <label className="block text-xs text-zinc-400 mb-1">Объём USDT</label>
                                  <input
                                    type="number"
                                    value={settings.futures.volume}
                                    onChange={(e) => {
                                      setAdminExchangeSettings({
                                        ...adminExchangeSettings,
                                        [exchange]: {
                                          ...settings,
                                          futures: { ...settings.futures, volume: e.target.value },
                                        },
                                      });
                                    }}
                                    className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                                  />
                                </div>
                                <div>
                                  <label className="block text-xs text-zinc-400 mb-1">Тень %</label>
                                  <input
                                    type="number"
                                    value={settings.futures.shadow}
                                    onChange={(e) => {
                                      setAdminExchangeSettings({
                                        ...adminExchangeSettings,
                                        [exchange]: {
                                          ...settings,
                                          futures: { ...settings.futures, shadow: e.target.value },
                                        },
                                      });
                                    }}
                                    className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                                  />
                                </div>
                              </div>
                            )}
                            
                            {/* Дополнительные пары для Futures (если есть) */}
                            {exchange === "binance" && adminOpenPairs[`${exchange}_futures`] && (
                              <div className="bg-zinc-950 rounded-lg p-4 border border-zinc-700">
                                <h4 className="text-sm font-medium text-white mb-4">Дополнительные пары для Futures</h4>
                                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                                  {getPairsForExchange(exchange, "futures").map((pair) => {
                                    const pairKey = `${exchange}_futures_${pair}`;
                                    const savedPairData = adminPairSettings[pairKey];
                                    const futuresSettings = settings.futures;
                                    
                                    const pairData = savedPairData || {
                                      enabled: true,
                                      delta: futuresSettings.delta || "0",
                                      volume: futuresSettings.volume || "0",
                                      shadow: futuresSettings.shadow || "0"
                                    };
                                    
                                    return (
                                      <div key={pair} className="bg-zinc-800 rounded-lg p-3 space-y-2">
                                        <div className="flex items-center justify-between mb-2">
                                          <div className="text-white font-medium text-sm">{pair}</div>
                                          <div
                                            className={`w-10 h-5 rounded-full transition-colors cursor-pointer ${
                                              pairData.enabled ? "bg-emerald-500" : "bg-zinc-600"
                                            }`}
                                            onClick={() => {
                                              setAdminPairSettings({
                                                ...adminPairSettings,
                                                [pairKey]: { ...pairData, enabled: !pairData.enabled },
                                              });
                                            }}
                                          >
                                            <div className={`w-4 h-4 bg-white rounded-full transition-transform mt-0.5 ${
                                              pairData.enabled ? "translate-x-5" : "translate-x-1"
                                            }`} />
                                          </div>
                                        </div>
                                        <div>
                                          <label className="block text-xs text-zinc-400 mb-1">Дельта %</label>
                                          <input
                                            type="number"
                                            value={pairData.delta}
                                            onChange={(e) => {
                                              setAdminPairSettings({
                                                ...adminPairSettings,
                                                [pairKey]: { ...pairData, delta: e.target.value },
                                              });
                                            }}
                                            className="w-full px-2 py-1 bg-zinc-900 border border-zinc-700 rounded text-white text-xs focus:outline-none focus:ring-1 focus:ring-emerald-500"
                                          />
                                        </div>
                                        <div>
                                          <label className="block text-xs text-zinc-400 mb-1">Объём USDT</label>
                                          <input
                                            type="number"
                                            value={pairData.volume}
                                            onChange={(e) => {
                                              setAdminPairSettings({
                                                ...adminPairSettings,
                                                [pairKey]: { ...pairData, volume: e.target.value },
                                              });
                                            }}
                                            className="w-full px-2 py-1 bg-zinc-900 border border-zinc-700 rounded text-white text-xs focus:outline-none focus:ring-1 focus:ring-emerald-500"
                                          />
                                        </div>
                                        <div>
                                          <label className="block text-xs text-zinc-400 mb-1">Тень %</label>
                                          <input
                                            type="number"
                                            value={pairData.shadow}
                                            onChange={(e) => {
                                              setAdminPairSettings({
                                                ...adminPairSettings,
                                                [pairKey]: { ...pairData, shadow: e.target.value },
                                              });
                                            }}
                                            className="w-full px-2 py-1 bg-zinc-900 border border-zinc-700 rounded text-white text-xs focus:outline-none focus:ring-1 focus:ring-emerald-500"
                                          />
                                        </div>
                                      </div>
                                    );
                                  })}
                                </div>
                              </div>
                            )}
                            
                            {exchange === "binance" && (
                              <div className="flex justify-end">
                                <button
                                  onClick={() => {
                                    const key = `${exchange}_futures`;
                                    setAdminOpenPairs({
                                      ...adminOpenPairs,
                                      [key]: !adminOpenPairs[key],
                                    });
                                  }}
                                  className="px-3 py-1.5 bg-zinc-700 hover:bg-zinc-600 text-white text-sm font-medium rounded-lg transition-colors"
                                >
                                  {adminOpenPairs[`${exchange}_futures`] ? "Скрыть пары" : "Открыть дополнительные пары"}
                                </button>
                              </div>
                            )}
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Пороги детектора */}
            <div className="border-t border-zinc-700 pt-4">
              <h3 className="text-lg font-semibold text-white mb-3">Пороги детектора</h3>
              {(() => {
                try {
                  const options = selectedUserSettings.options_json 
                    ? JSON.parse(selectedUserSettings.options_json) 
                    : {};
                  const thresholds = options.thresholds || { delta_pct: 1.0, volume_usdt: 10000.0, wick_pct: 50.0 };
                  return (
                      <div className="grid md:grid-cols-3 gap-4">
                        <div>
                          <label className="block text-sm text-zinc-400 mb-1">Дельта %</label>
                          <input
                            type="number"
                            step="0.1"
                            value={thresholds.delta_pct || 0}
                            onChange={(e) => {
                              const newThresholds = { ...thresholds, delta_pct: Number(e.target.value) || 0 };
                              const newOptions = { ...options, thresholds: newThresholds };
                              setSelectedUserSettings({
                                ...selectedUserSettings,
                                options_json: JSON.stringify(newOptions),
                              });
                            }}
                            className="w-full px-4 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                          />
                        </div>
                        <div>
                          <label className="block text-sm text-zinc-400 mb-1">Объём USDT</label>
                          <input
                            type="number"
                            step="1000"
                            value={thresholds.volume_usdt || 0}
                            onChange={(e) => {
                              const newThresholds = { ...thresholds, volume_usdt: Number(e.target.value) || 0 };
                              const newOptions = { ...options, thresholds: newThresholds };
                              setSelectedUserSettings({
                                ...selectedUserSettings,
                                options_json: JSON.stringify(newOptions),
                              });
                            }}
                            className="w-full px-4 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                          />
                        </div>
                        <div>
                          <label className="block text-sm text-zinc-400 mb-1">Тень %</label>
                          <input
                            type="number"
                            step="1"
                            value={thresholds.wick_pct || 0}
                            onChange={(e) => {
                              const newThresholds = { ...thresholds, wick_pct: Number(e.target.value) || 0 };
                              const newOptions = { ...options, thresholds: newThresholds };
                              setSelectedUserSettings({
                                ...selectedUserSettings,
                                options_json: JSON.stringify(newOptions),
                              });
                            }}
                            className="w-full px-4 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                          />
                        </div>
                      </div>
                  );
                } catch (e) {
                  return <p className="text-zinc-500 text-sm">Ошибка парсинга настроек</p>;
                }
              })()}
              
              {/* Кнопка для копирования значений во все биржи */}
              <div className="mt-4">
                <button
                  onClick={copyThresholdsToAllExchanges}
                  className="w-full px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-lg transition-colors"
                  title="Скопировать значения порогов (Дельта %, Объём USDT, Тень %) из общих фильтров во все биржи (Spot и Futures)"
                >
                  Вставить значения во все биржи
                </button>
              </div>
            </div>

            {/* Чёрный список */}
            <div className="border-t border-zinc-700 pt-4">
              <h3 className="text-lg font-semibold text-white mb-3">Чёрный список</h3>
              {(() => {
                try {
                  const options = selectedUserSettings.options_json 
                    ? JSON.parse(selectedUserSettings.options_json) 
                    : {};
                  const blacklist = options.blacklist || [];
                  return blacklist.length > 0 ? (
                    <div className="flex flex-wrap gap-2">
                      {blacklist.map((symbol: string) => (
                        <span key={symbol} className="px-3 py-1 bg-red-900/30 text-red-400 rounded-lg text-sm">
                          {symbol}
                        </span>
                      ))}
                    </div>
                  ) : (
                    <p className="text-zinc-500 text-sm">Чёрный список пуст</p>
                  );
                } catch (e) {
                  return <p className="text-zinc-500 text-sm">Ошибка парсинга настроек</p>;
                }
              })()}
            </div>

            {/* Кнопка сохранения */}
            <div className="border-t border-zinc-700 pt-4 mt-4">
              <button
                onClick={saveAdminUserSettings}
                disabled={adminLoading}
                className="w-full px-6 py-3 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed font-semibold"
              >
                {adminLoading ? "Сохранение..." : "Сохранить изменения"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Блок Логов */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-bold text-white">Логи ошибок</h2>
          <div className="flex gap-2">
            {isAdmin && (
              <button
                onClick={deleteAllErrors}
                disabled={errorLogsLoading}
                className="px-4 py-2 bg-red-500 text-white rounded-lg hover:bg-red-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed text-sm"
                title="Удалить все логи ошибок"
              >
                Удалить все
              </button>
            )}
            <button
              onClick={fetchErrorLogs}
              disabled={errorLogsLoading}
              className="px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed text-sm"
            >
              {errorLogsLoading ? "Загрузка..." : "Обновить"}
            </button>
          </div>
        </div>

        {/* Фильтры */}
        <div className="grid md:grid-cols-4 gap-4 mb-4">
          <div>
            <label className="block text-sm text-zinc-400 mb-1">Биржа</label>
            <select
              value={errorLogsFilter.exchange || ""}
              onChange={(e) =>
                setErrorLogsFilter({
                  ...errorLogsFilter,
                  exchange: e.target.value || undefined,
                })
              }
              className="w-full px-4 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="">Все биржи</option>
              <option value="binance">Binance</option>
              <option value="bybit">Bybit</option>
              <option value="bitget">Bitget</option>
              <option value="gate">Gate.io</option>
            </select>
          </div>
          <div>
            <label className="block text-sm text-zinc-400 mb-1">Тип ошибки</label>
            <select
              value={errorLogsFilter.error_type || ""}
              onChange={(e) =>
                setErrorLogsFilter({
                  ...errorLogsFilter,
                  error_type: e.target.value || undefined,
                })
              }
              className="w-full px-4 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="">Все типы</option>
              <option value="reconnect">Reconnect</option>
              <option value="websocket_error">WebSocket Error</option>
              <option value="critical">Critical</option>
              <option value="connection_error">Connection Error</option>
              <option value="telegram_error">Telegram Error</option>
            </select>
          </div>
          <div>
            <label className="block text-sm text-zinc-400 mb-1">Лимит записей</label>
            <input
              type="number"
              min="10"
              max="1000"
              step="10"
              value={errorLogsFilter.limit}
              onChange={(e) =>
                setErrorLogsFilter({
                  ...errorLogsFilter,
                  limit: parseInt(e.target.value) || 100,
                })
              }
              className="w-full px-4 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
          <div className="flex items-end">
            <button
              onClick={() => {
                setErrorLogsFilter({ limit: 100 });
              }}
              className="w-full px-4 py-2 bg-zinc-700 text-white rounded-lg hover:bg-zinc-600 transition-colors text-sm"
            >
              Сбросить фильтры
            </button>
          </div>
        </div>

        {/* Таблица логов */}
        <div className="overflow-x-auto">
          {errorLogsLoading ? (
            <div className="text-center py-8 text-zinc-400">Загрузка логов...</div>
          ) : errorLogs.length === 0 ? (
            <div className="text-center py-8 text-zinc-400">Логи отсутствуют</div>
          ) : (
            <div className="space-y-2 max-h-96 overflow-y-auto">
              {errorLogs.map((error) => (
                <div
                  key={error.id}
                  className="bg-zinc-800 border border-zinc-700 rounded-lg p-4 hover:bg-zinc-750 transition-colors"
                >
                  <div className="flex items-start justify-between mb-2">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="px-2 py-1 bg-red-900/30 text-red-400 rounded text-xs font-medium">
                        {error.error_type}
                      </span>
                      {error.exchange && (
                        <span className="px-2 py-1 bg-blue-900/30 text-blue-400 rounded text-xs">
                          {error.exchange}
                        </span>
                      )}
                      {error.market && (
                        <span className="px-2 py-1 bg-purple-900/30 text-purple-400 rounded text-xs">
                          {error.market}
                        </span>
                      )}
                      {error.symbol && (
                        <span className="px-2 py-1 bg-emerald-900/30 text-emerald-400 rounded text-xs">
                          {error.symbol}
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-zinc-500">
                        {new Date(error.timestamp).toLocaleString("ru-RU")}
                      </span>
                      {isAdmin && (
                        <button
                          onClick={() => deleteError(error.id)}
                          className="px-2 py-1 bg-red-500/20 text-red-400 rounded text-xs hover:bg-red-500/30 transition-colors"
                          title="Удалить этот лог"
                        >
                          ✕
                        </button>
                      )}
                    </div>
                  </div>
                  <div className="text-sm text-white mb-2">{error.error_message}</div>
                  {error.connection_id && (
                    <div className="text-xs text-zinc-500 mb-1">
                      Connection ID: {error.connection_id}
                    </div>
                  )}
                  {error.stack_trace && (
                    <details className="mt-2">
                      <summary className="text-xs text-zinc-400 cursor-pointer hover:text-zinc-300">
                        Показать стек трейс
                      </summary>
                      <pre className="mt-2 p-2 bg-zinc-900 rounded text-xs text-zinc-300 overflow-x-auto">
                        {error.stack_trace}
                      </pre>
                    </details>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

