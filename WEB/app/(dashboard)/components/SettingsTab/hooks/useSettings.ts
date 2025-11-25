"use client";

import { useState, useCallback, useEffect } from "react";
import { ConditionalTemplate } from "../types";
import { convertToTechnicalKeys } from "../utils/templateUtils";

interface UseSettingsParams {
  userLogin: string;
  // Callbacks для установки загруженных данных
  setTelegramBotToken: (token: string) => void;
  setTelegramChatId: (chatId: string) => void;
  setIsTelegramConfigured: (configured: boolean) => void;
  setIsEditingTelegram: (editing: boolean) => void;
  timezone: string;
  setTimezone: (timezone: string) => void;
  setExchangeFilters: (filters: Record<string, boolean>) => void;
  setPairSettings: (settings: Record<string, { enabled: boolean; delta: string; volume: string; shadow: string; sendChart?: boolean }>) => void;
  setChartSettings: (settings: Record<string, boolean>) => void;
  setBlacklist: (blacklist: string[]) => void;
  setMessageTemplate: (template: string) => void;
  setConditionalTemplates: (templates: ConditionalTemplate[]) => void;
  // Данные для сохранения
  telegramBotToken: string;
  telegramChatId: string;
  exchangeFilters: Record<string, boolean>;
  pairSettings: Record<string, { enabled: boolean; delta: string; volume: string; shadow: string; sendChart?: boolean }>;
  chartSettings: Record<string, boolean>;
  blacklist: string[];
  messageTemplate: string;
  conditionalTemplates: ConditionalTemplate[];
  // Функции-хелперы
  extractTextFromEditor: () => string;
  validateStrategies: () => boolean;
  convertToFriendlyNames: (template: string) => string;
}

export function useSettings({
  userLogin,
  setTelegramBotToken,
  setTelegramChatId,
  setIsTelegramConfigured,
  setIsEditingTelegram,
  setTimezone,
  setExchangeFilters,
  setPairSettings,
  setChartSettings,
  setBlacklist,
  setMessageTemplate,
  setConditionalTemplates,
  timezone,
  telegramBotToken,
  telegramChatId,
  exchangeFilters,
  pairSettings,
  chartSettings,
  blacklist,
  messageTemplate,
  conditionalTemplates,
  extractTextFromEditor,
  validateStrategies,
  convertToFriendlyNames,
}: UseSettingsParams) {
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Автоматическое скрытие уведомления через 3 секунды
  useEffect(() => {
    if (saveMessage) {
      const timer = setTimeout(() => {
        setSaveMessage(null);
      }, 3000);
      return () => clearTimeout(timer);
    }
  }, [saveMessage]);

  // Загрузка настроек пользователя
  const fetchUserSettings = useCallback(async () => {
    if (!userLogin) {
      console.log("[SettingsTab] fetchUserSettings: userLogin is empty");
      return;
    }
    
    setLoading(true);
    setError(null);
    
    try {
      const url = `/api/users/${encodeURIComponent(userLogin)}`;
      console.log(`[SettingsTab] fetchUserSettings: Fetching from ${url}`);
      
      const res = await fetch(url);
      console.log(`[SettingsTab] fetchUserSettings: Response status: ${res.status}`);
      
      if (res.ok) {
        const userData = await res.json();
        console.log(`[SettingsTab] fetchUserSettings: User data received:`, {
          user: userData.user,
          has_tg_token: !!userData.tg_token,
          has_chat_id: !!userData.chat_id,
          has_options_json: !!userData.options_json
        });
        
        const tgToken = (userData.tg_token || "").trim();
        const chatId = (userData.chat_id || "").trim();
        setTelegramBotToken(tgToken);
        setTelegramChatId(chatId);
        
        const hasTelegram = !!(tgToken && chatId);
        setIsTelegramConfigured(hasTelegram);
        setIsEditingTelegram(!hasTelegram);
        
        try {
          const optionsJson = userData.options_json || "{}";
          const options = typeof optionsJson === "string" ? JSON.parse(optionsJson) : optionsJson;
          
          // Загрузка шаблона сообщения
          if (options.messageTemplate && options.messageTemplate.trim() !== '') {
            console.log("Загружен шаблон из БД (технический):", options.messageTemplate);
            let template = options.messageTemplate;
            
            // Миграция старого формата
            if (template.includes("{exchange}") && template.includes("{market}")) {
              template = template.replace(/\{exchange\}\s*\|\s*\{market\}/g, "{exchange_market}");
              template = template.replace(/\{exchange\}\s*\{market\}/g, "{exchange_market}");
              template = template.replace(/\{market\}\s*\|\s*\{exchange\}/g, "{exchange_market}");
              template = template.replace(/\{market\}\s*\{exchange\}/g, "{exchange_market}");
            }
            
            let friendlyTemplate = convertToFriendlyNames(template);
            friendlyTemplate = friendlyTemplate.replace(/\[\[Объём торгов\]\]/g, "[[Объём стрелы]]");
            
            if (friendlyTemplate.includes("[[Биржа]]") && friendlyTemplate.includes("[[Тип рынка]]")) {
              friendlyTemplate = friendlyTemplate.replace(/\[\[Биржа\]\]\s*\|\s*\[\[Тип рынка\]\]/g, "[[Биржа и тип рынка]]");
              friendlyTemplate = friendlyTemplate.replace(/\[\[Биржа\]\]\s*\[\[Тип рынка\]\]/g, "[[Биржа и тип рынка]]");
              friendlyTemplate = friendlyTemplate.replace(/\[\[Тип рынка\]\]\s*\|\s*\[\[Биржа\]\]/g, "[[Биржа и тип рынка]]");
              friendlyTemplate = friendlyTemplate.replace(/\[\[Тип рынка\]\]\s*\[\[Биржа\]\]/g, "[[Биржа и тип рынка]]");
            }
            
            console.log("Шаблон после преобразования (понятный):", friendlyTemplate);
            setMessageTemplate(friendlyTemplate);
          } else {
            const exampleTemplate = `🚨 <b>НАЙДЕНА СТРЕЛА!</b> [[Направление]]

<b>[[Биржа и тип рынка]]</b>
💰 <b>[[Торговая пара]]</b>

📊 <b>Метрики:</b>
• Изменение: <b>[[Дельта стрелы]]</b> [[Направление]]
• Объём: <b>[[Объём стрелы]] USDT</b>
• Тень: <b>[[Тень свечи]]</b>

⏰ <b>[[Время детекта]]</b>`;
            console.log("Шаблон не найден в БД, используем дефолтный");
            setMessageTemplate(exampleTemplate);
          }
          
          // Загрузка фильтров бирж
          if (options.exchanges && typeof options.exchanges === "object") {
            const oldFormat = options.exchanges.binance !== undefined || 
                             options.exchanges.bybit !== undefined ||
                             options.exchanges.bitget !== undefined ||
                             options.exchanges.gate !== undefined ||
                             options.exchanges.hyperliquid !== undefined;
            
            if (oldFormat) {
              // Старый формат: биржа целиком
              setExchangeFilters({
                binance_spot: options.exchanges.binance === true,
                binance_futures: options.exchanges.binance === true,
                bybit_spot: options.exchanges.bybit === true,
                bybit_futures: options.exchanges.bybit === true,
                bitget_spot: options.exchanges.bitget === true,
                bitget_futures: options.exchanges.bitget === true,
                gate_spot: options.exchanges.gate === true,
                gate_futures: options.exchanges.gate === true,
                hyperliquid_spot: options.exchanges.hyperliquid === true,
                hyperliquid_futures: options.exchanges.hyperliquid === true,
              });
            } else {
              // Новый формат: отдельно для каждого рынка
              setExchangeFilters({
                binance_spot: options.exchanges.binance_spot === true,
                binance_futures: options.exchanges.binance_futures === true,
                bybit_spot: options.exchanges.bybit_spot === true,
                bybit_futures: options.exchanges.bybit_futures === true,
                bitget_spot: options.exchanges.bitget_spot === true,
                bitget_futures: options.exchanges.bitget_futures === true,
                gate_spot: options.exchanges.gate_spot === true,
                gate_futures: options.exchanges.gate_futures === true,
                hyperliquid_spot: options.exchanges.hyperliquid_spot === true,
                hyperliquid_futures: options.exchanges.hyperliquid_futures === true,
              });
            }
          } else {
            setExchangeFilters({
              binance_spot: false,
              binance_futures: false,
              bybit_spot: false,
              bybit_futures: false,
              bitget_spot: false,
              bitget_futures: false,
              gate_spot: false,
              gate_futures: false,
              hyperliquid_spot: false,
              hyperliquid_futures: false,
            });
          }
          
          // Загрузка настроек пар
          if (options.pairSettings && typeof options.pairSettings === "object") {
            const migratedPairSettings: Record<string, { enabled: boolean; delta: string; volume: string; shadow: string; sendChart?: boolean }> = {};
            Object.entries(options.pairSettings).forEach(([key, value]: [string, any]) => {
              if (value && typeof value === 'object' && !('enabled' in value)) {
                migratedPairSettings[key] = {
                  enabled: false,
                  delta: value.delta || "",
                  volume: value.volume || "",
                  shadow: value.shadow || "",
                  sendChart: value.sendChart || false,
                };
              } else {
                migratedPairSettings[key] = {
                  enabled: value?.enabled === true,
                  delta: value?.delta || "",
                  volume: value?.volume || "",
                  shadow: value?.shadow || "",
                  sendChart: value?.sendChart || false,
                };
              }
            });
            setPairSettings(migratedPairSettings);
          }
          
          // Загрузка чёрного списка
          if (options.blacklist) {
            setBlacklist(options.blacklist || []);
          }
          
          // Загрузка стратегий
          if (options.conditionalTemplates && Array.isArray(options.conditionalTemplates)) {
            const templatesWithFriendlyNames = options.conditionalTemplates.map((template: any) => {
              let conditions = [];
              if (template.conditions && Array.isArray(template.conditions)) {
                conditions = template.conditions.map((cond: any) => {
                  const condType = cond.type === "wick" ? "delta" : (cond.type || "volume");
                  if (condType === "series") {
                    return {
                      type: "series",
                      count: cond.count || 2,
                      timeWindowSeconds: cond.timeWindowSeconds || 300,
                    };
                  } else if (condType === "delta" || condType === "wick_pct") {
                    if (cond.valueMin !== undefined || cond.valueMax !== undefined) {
                      return {
                        type: condType,
                        valueMin: cond.valueMin !== undefined ? cond.valueMin : 0,
                        valueMax: cond.valueMax !== undefined ? cond.valueMax : null,
                      };
                    } else {
                      return {
                        type: condType,
                        valueMin: cond.value !== undefined ? cond.value : 0,
                        valueMax: null,
                      };
                    }
                  } else if (condType === "symbol") {
                    return {
                      type: "symbol",
                      symbol: (cond.symbol || cond.value || "").toUpperCase().trim(),
                    };
                  } else if (condType === "exchange_market") {
                    if (cond.exchange_market) {
                      return {
                        type: "exchange_market",
                        exchange_market: cond.exchange_market.toLowerCase(),
                      };
                    } else {
                      const exchange = (cond.exchange || "binance").toLowerCase();
                      const market = (cond.market || "spot").toLowerCase();
                      const marketNormalized = market === "linear" ? "futures" : market;
                      return {
                        type: "exchange_market",
                        exchange_market: `${exchange}_${marketNormalized}`,
                      };
                    }
                  } else if (condType === "exchange") {
                    const exchange = (cond.exchange || "binance").toLowerCase();
                    return {
                      type: "exchange_market",
                      exchange_market: `${exchange}_spot`,
                    };
                  } else if (condType === "market") {
                    const market = (cond.market || "spot").toLowerCase();
                    const marketNormalized = market === "linear" ? "futures" : market;
                    return {
                      type: "exchange_market",
                      exchange_market: `binance_${marketNormalized}`,
                    };
                  } else if (condType === "direction") {
                    return {
                      type: "direction",
                      direction: (cond.direction || "up").toLowerCase() as "up" | "down",
                    };
                  } else {
                    return {
                      type: condType,
                      value: cond.value || 0,
                    };
                  }
                });
              } else if (template.condition) {
                const condType = template.condition.type === "wick" ? "delta" : (template.condition.type || "volume");
                if (condType === "delta") {
                  conditions = [{
                    type: "delta",
                    valueMin: template.condition.value !== undefined ? template.condition.value : 0,
                    valueMax: null,
                  }];
                } else {
                  conditions = [{
                    type: condType,
                    value: template.condition.value || 0,
                  }];
                }
              } else {
                conditions = [{ type: "volume", value: 0 }];
              }
              
              return {
                name: template.name || undefined,
                enabled: template.enabled !== undefined ? template.enabled : true,
                useGlobalFilters: template.useGlobalFilters !== undefined ? template.useGlobalFilters : true,
                conditions,
                template: convertToFriendlyNames(template.template || ""),
                chatId: template.chatId || undefined,
              };
            });
            setConditionalTemplates(templatesWithFriendlyNames);
          } else {
            setConditionalTemplates([]);
          }
          
          // Загрузка настроек графиков
          const chartSettingsMap: Record<string, boolean> = {};
          if (options.pairSettings && typeof options.pairSettings === "object") {
            Object.entries(options.pairSettings).forEach(([key, value]: [string, any]) => {
              if (value && typeof value === 'object' && 'sendChart' in value) {
                chartSettingsMap[key] = value.sendChart === true;
              }
            });
          }
          setChartSettings(chartSettingsMap);
          
          // Загрузка временной зоны
          if (options.timezone && typeof options.timezone === "string") {
            setTimezone(options.timezone);
          } else {
            try {
              const browserTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
              setTimezone(browserTimezone || "UTC");
            } catch (e) {
              setTimezone("UTC");
            }
          }
          
          console.log("Настройки пользователя загружены:", {
            hasTelegram,
            exchangeFilters: options.exchanges,
            timezone: options.timezone,
            optionsKeys: Object.keys(options)
          });
        } catch (e) {
          console.error("Ошибка парсинга options_json:", e);
          setExchangeFilters({
            binance_spot: false,
            binance_futures: false,
            bybit_spot: false,
            bybit_futures: false,
            bitget_spot: false,
            bitget_futures: false,
            gate_spot: false,
            gate_futures: false,
            hyperliquid_spot: false,
            hyperliquid_futures: false,
          });
        }
      } else if (res.status === 404) {
        console.log(`Пользователь "${userLogin}" не найден в БД. Будет создан при сохранении настроек.`);
      } else {
        const errorText = await res.text().catch(() => "Unknown error");
        console.error(`Ошибка загрузки настроек пользователя ${userLogin}:`, res.status, errorText);
        setError(`Ошибка загрузки настроек: ${res.status}`);
      }
    } catch (err) {
      console.error("Ошибка загрузки настроек пользователя:", err);
      setError(err instanceof Error ? err.message : "Ошибка загрузки настроек");
    } finally {
      setLoading(false);
    }
  }, [
    userLogin,
    setTelegramBotToken,
    setTelegramChatId,
    setIsTelegramConfigured,
    setIsEditingTelegram,
    setTimezone,
    setExchangeFilters,
    setPairSettings,
    setChartSettings,
    setBlacklist,
    setMessageTemplate,
    setConditionalTemplates,
    convertToFriendlyNames,
  ]);

  // Сохранение всех настроек
  const saveAllSettings = useCallback(async (): Promise<boolean> => {
    if (!userLogin) return false;
    
    // Валидация стратегий перед сохранением
    if (!validateStrategies()) {
      setSaveMessage({
        type: "error",
        text: "Не удалось сохранить: обнаружены ошибки в стратегиях. Пожалуйста, исправьте их перед сохранением."
      });
      setTimeout(() => setSaveMessage(null), 5000);
      return false;
    }
    
    const extractedText = extractTextFromEditor();
    
    const pairSettingsWithCharts: Record<string, { enabled: boolean; delta: string; volume: string; shadow: string; sendChart?: boolean }> = { ...pairSettings };
    
    // Объединяем chartSettings с pairSettings
    Object.keys(chartSettings).forEach((key) => {
      if (pairSettings[key]) {
        const currentSettings = pairSettings[key];
        pairSettingsWithCharts[key] = {
          enabled: currentSettings.enabled,
          delta: currentSettings.delta,
          volume: currentSettings.volume,
          shadow: currentSettings.shadow,
          sendChart: chartSettings[key]
        };
      } else {
        const parts = key.split('_');
        if (parts.length === 3) {
          const [exchange, market, pair] = parts;
          if (market === "spot" || market === "futures") {
            const existingSettings = (key in pairSettings ? pairSettings[key] : undefined) as { enabled: boolean; delta: string; volume: string; shadow: string; sendChart?: boolean } | undefined;
            pairSettingsWithCharts[key] = {
              enabled: existingSettings?.enabled || false,
              delta: existingSettings?.delta || "",
              volume: existingSettings?.volume || "",
              shadow: existingSettings?.shadow || "",
              sendChart: chartSettings[key]
            };
          }
        }
      }
    });
    
    const options = {
      exchanges: exchangeFilters,
      pairSettings: pairSettingsWithCharts,
      blacklist,
      messageTemplate: convertToTechnicalKeys(extractedText),
      conditionalTemplates: conditionalTemplates.map(template => {
        const templateData: any = {
          conditions: template.conditions.map(condition => {
            const baseCondition: any = {
              type: condition.type,
              operator: ">=",
            };
            
            if (condition.type === "series") {
              baseCondition.count = condition.count || 2;
              baseCondition.timeWindowSeconds = condition.timeWindowSeconds || 300;
            } else if (condition.type === "delta" || condition.type === "wick_pct") {
              if (condition.valueMin !== undefined) {
                baseCondition.valueMin = condition.valueMin;
              }
              if (condition.valueMax !== undefined || condition.valueMax === null) {
                baseCondition.valueMax = condition.valueMax;
              }
            } else if (condition.type === "symbol") {
              if (condition.symbol) {
                baseCondition.value = condition.symbol.toUpperCase().trim();
                baseCondition.symbol = condition.symbol.toUpperCase().trim();
              }
            } else if (condition.type === "exchange_market") {
              if (condition.exchange_market) {
                baseCondition.exchange_market = condition.exchange_market.toLowerCase();
              } else if (condition.exchange && condition.market) {
                const market = condition.market === "linear" ? "futures" : condition.market;
                baseCondition.exchange_market = `${condition.exchange.toLowerCase()}_${market.toLowerCase()}`;
              }
            } else if (condition.type === "direction") {
              if (condition.direction) {
                baseCondition.direction = condition.direction.toLowerCase();
              }
            } else {
              baseCondition.value = condition.value || 0;
            }
            
            return baseCondition;
          }),
          template: convertToTechnicalKeys(template.template),
        };
        
        if (template.name) {
          templateData.name = template.name;
        }
        
        if (template.enabled === false) {
          templateData.enabled = false;
        }
        
        templateData.useGlobalFilters = template.useGlobalFilters !== undefined ? template.useGlobalFilters : true;
        
        if (template.chatId) {
          templateData.chatId = template.chatId;
        }
        
        return templateData;
      }),
      timezone: timezone || "UTC",
    };
    
    setSaving(true);
    setError(null);
    
    try {
      const res = await fetch(`/api/users/${userLogin}/settings`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          tg_token: telegramBotToken,
          chat_id: telegramChatId,
          options_json: JSON.stringify(options),
        })
      });
      
      if (res.ok) {
        const hasTelegram = !!(telegramBotToken && telegramChatId);
        if (hasTelegram) {
          setIsTelegramConfigured(true);
          setIsEditingTelegram(false);
        }
        
        setSaveMessage({
          type: "success",
          text: "Настройки успешно сохранены! Изменения применятся в течение 1 минуты (время обновления кэша системы)."
        });
        return true;
      } else {
        const error = await res.json();
        setSaveMessage({ type: "error", text: error.detail || "Ошибка сохранения настроек" });
        setError(error.detail || "Ошибка сохранения настроек");
        return false;
      }
    } catch (err) {
      console.error("Ошибка сохранения настроек:", err);
      const errorMessage = err instanceof Error ? err.message : "Ошибка сохранения настроек";
      setSaveMessage({ type: "error", text: errorMessage });
      setError(errorMessage);
      return false;
    } finally {
      setSaving(false);
    }
  }, [
    userLogin,
    timezone,
    telegramBotToken,
    telegramChatId,
    exchangeFilters,
    pairSettings,
    chartSettings,
    blacklist,
    messageTemplate,
    conditionalTemplates,
    extractTextFromEditor,
    validateStrategies,
    setIsTelegramConfigured,
    setIsEditingTelegram,
    convertToTechnicalKeys,
  ]);

  return {
    loading,
    saving,
    saveMessage,
    error,
    fetchUserSettings,
    saveAllSettings,
    setSaveMessage,
  };
}

