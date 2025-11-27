"use client";

import { useState, useCallback } from "react";
import { AdminUser, AdminUserSettings } from "../types";

export function useAdminUsers() {
  const [adminUsers, setAdminUsers] = useState<AdminUser[]>([]);
  const [adminForm, setAdminForm] = useState<string>("");
  const [adminMsg, setAdminMsg] = useState("");
  const [adminLoading, setAdminLoading] = useState(false);
  const [selectedUserSettings, setSelectedUserSettings] = useState<AdminUserSettings | null>(null);
  const [deletingGlobalStats, setDeletingGlobalStats] = useState(false);

  // Состояния для редактирования настроек бирж в админ панели
  const [adminExchangeFilters, setAdminExchangeFilters] = useState<Record<string, boolean>>({
    binance_spot: true,
    binance_futures: true,
    bybit_spot: true,
    bybit_futures: true,
    bitget_spot: true,
    bitget_futures: true,
    gate_spot: true,
    gate_futures: true,
    hyperliquid_spot: true,
    hyperliquid_futures: true,
  });
  const [adminPairSettings, setAdminPairSettings] = useState<Record<string, { enabled: boolean; delta: string; volume: string; shadow: string }>>({});
  const [adminExpandedExchanges, setAdminExpandedExchanges] = useState<Record<string, boolean>>({});

  // Загрузка пользователей
  const fetchAdminUsers = useCallback(async () => {
    try {
      const res = await fetch("/api/users");
      const data = await res.json();
      setAdminUsers(data.users || []);
    } catch (err) {
      console.error("Ошибка загрузки пользователей:", err);
      setAdminMsg("Ошибка загрузки пользователей");
      setTimeout(() => setAdminMsg(""), 3000);
    }
  }, []);

  // Создание нового пользователя
  const createAdminUser = useCallback(async () => {
    if (!adminForm.trim()) {
      setAdminMsg("Введите имя пользователя");
      setTimeout(() => setAdminMsg(""), 2000);
      return;
    }

    setAdminLoading(true);
    try {
      const trimmedUserName = adminForm.trim();
      const encodedUserName = encodeURIComponent(trimmedUserName);
      const res = await fetch(`/api/users/${encodedUserName}/settings`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          tg_token: "",
          chat_id: "",
          options_json: JSON.stringify({
            exchanges: { gate: false, binance: false, bitget: false, bybit: false, hyperliquid: false },
            pairSettings: {},
          }),
        }),
      });

      if (!res.ok) {
        const error = await res.json();
        throw new Error(error.detail || "Ошибка создания пользователя");
      }

      setAdminMsg(`Пользователь "${trimmedUserName}" успешно создан!`);
      setTimeout(() => setAdminMsg(""), 3000);
      setAdminForm("");
      fetchAdminUsers();
    } catch (err) {
      console.error("Ошибка создания пользователя:", err);
      setAdminMsg(err instanceof Error ? err.message : "Ошибка создания пользователя");
      setTimeout(() => setAdminMsg(""), 3000);
    } finally {
      setAdminLoading(false);
    }
  }, [adminForm, fetchAdminUsers]);

  // Загрузка настроек пользователя
  const loadUserSettings = useCallback(async (userName: string) => {
    setAdminLoading(true);
    try {
      const res = await fetch(`/api/users/${userName}`);
      if (res.ok) {
        const data = await res.json();
        let optionsJson = data.options_json || "{}";
        if (!optionsJson || optionsJson.trim() === "") {
          optionsJson = JSON.stringify({
            exchanges: { gate: true, binance: true, bitget: true, bybit: true, hyperliquid: true },
            pairSettings: {},
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
          // Поддерживаем как старый формат (binance: true), так и новый (binance_spot: true, binance_futures: true)
          const newFilters: Record<string, boolean> = {
            binance_spot: true,
            binance_futures: true,
            bybit_spot: true,
            bybit_futures: true,
            bitget_spot: true,
            bitget_futures: true,
            gate_spot: true,
            gate_futures: true,
            hyperliquid_spot: true,
            hyperliquid_futures: true,
          };

          if (options.exchanges && typeof options.exchanges === "object") {
            // Проверяем, есть ли новый формат (binance_spot, binance_futures и т.д.)
            const hasNewFormat = Object.keys(options.exchanges).some(key => key.includes("_spot") || key.includes("_futures"));
            
            if (hasNewFormat) {
              // Новый формат - используем напрямую
              ["binance", "bybit", "bitget", "gate", "hyperliquid"].forEach((exchange) => {
                ["spot", "futures"].forEach((market) => {
                  const key = `${exchange}_${market}`;
                  newFilters[key] = options.exchanges[key] !== false && options.exchanges[key] !== undefined 
                    ? options.exchanges[key] 
                    : true;
                });
              });
            } else {
              // Старый формат - конвертируем в новый
              ["binance", "bybit", "bitget", "gate", "hyperliquid"].forEach((exchange) => {
                const exchangeValue = options.exchanges[exchange];
                const isEnabled = exchangeValue !== false && exchangeValue !== undefined ? exchangeValue : true;
                newFilters[`${exchange}_spot`] = isEnabled;
                newFilters[`${exchange}_futures`] = isEnabled;
              });
            }
          }
          
          setAdminExchangeFilters(newFilters);

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
          } else {
            setAdminPairSettings({});
          }

          // Сбрасываем состояние раскрытия секций при загрузке нового пользователя
          setAdminExpandedExchanges({});
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
  }, []);

  // Удаление пользователя
  const deleteAdminUser = useCallback(async (userName: string) => {
    const trimmedUserName = userName.trim();

    if (!trimmedUserName) {
      setAdminMsg("Имя пользователя не может быть пустым");
      setTimeout(() => setAdminMsg(""), 3000);
      return;
    }

    const lowerUserName = trimmedUserName.toLowerCase();
    if (lowerUserName === "stats" || lowerUserName === "влад") {
      setAdminMsg(`Нельзя удалить системного пользователя '${trimmedUserName}'`);
      setTimeout(() => setAdminMsg(""), 3000);
      return;
    }

    if (!confirm(`Удалить пользователя "${trimmedUserName}"?`)) return;

    setAdminLoading(true);
    try {
      const encodedUserName = encodeURIComponent(trimmedUserName);
      const res = await fetch(`/api/users/${encodedUserName}/delete`, {
        method: "DELETE",
      });

      if (!res.ok) {
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
  }, [fetchAdminUsers, selectedUserSettings]);

  // Удаление рыночной статистики
  const deleteGlobalStats = useCallback(async () => {
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
  }, []);

  // Сохранение настроек пользователя
  const saveAdminUserSettings = useCallback(async () => {
    if (!selectedUserSettings) return;

    setAdminLoading(true);
    try {
      let options: any = {};
      try {
        options = selectedUserSettings.options_json ? JSON.parse(selectedUserSettings.options_json) : {};
      } catch (e) {
        options = {};
      }

      // Конвертируем новый формат фильтров (binance_spot, binance_futures) обратно в старый формат (binance)
      // для совместимости с бэкендом. Биржа считается включенной, если включен хотя бы один из рынков
      const legacyExchanges: Record<string, boolean> = {};
      ["binance", "bybit", "bitget", "gate", "hyperliquid"].forEach((exchange) => {
        const spotKey = `${exchange}_spot`;
        const futuresKey = `${exchange}_futures`;
        legacyExchanges[exchange] = adminExchangeFilters[spotKey] || adminExchangeFilters[futuresKey] || false;
      });
      
      // Сохраняем оба формата для совместимости
      options.exchanges = {
        ...legacyExchanges,
        ...adminExchangeFilters, // Сохраняем и новый формат
      };
      options.pairSettings = adminPairSettings;

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
      fetchAdminUsers();
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
  }, [selectedUserSettings, adminExchangeFilters, adminPairSettings, fetchAdminUsers]);

  return {
    // Состояния
    adminUsers,
    adminForm,
    adminMsg,
    adminLoading,
    selectedUserSettings,
    deletingGlobalStats,
    adminExchangeFilters,
    adminPairSettings,
    adminExpandedExchanges,
    // Сеттеры
    setAdminForm,
    setAdminMsg,
    setSelectedUserSettings,
    setAdminExchangeFilters,
    setAdminPairSettings,
    setAdminExpandedExchanges,
    // Функции
    fetchAdminUsers,
    createAdminUser,
    loadUserSettings,
    deleteAdminUser,
    deleteGlobalStats,
    saveAdminUserSettings,
  };
}

