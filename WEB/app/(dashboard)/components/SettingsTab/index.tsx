"use client";

import { useEffect, useState } from "react";
import { ConditionalTemplate } from "./types";
import SettingsNavigation from "./SettingsNavigation";
import TelegramSettings from "./TelegramSettings";
import MessageFormatSettings from "./MessageFormatSettings";
import ChartSettings from "./ChartSettings";
import SpikesSettings from "./SpikesSettings";
import BlacklistSettings from "./BlacklistSettings";
import StrategiesSettings from "./StrategiesSettings";
import { useSettings } from "./hooks/useSettings";
import { useTelegramSettings } from "./hooks/useTelegramSettings";
import { useMessageTemplate } from "./hooks/useMessageTemplate";
import { useStrategies } from "./hooks/useStrategies";
import { convertToFriendlyKeys } from "./utils/templateUtils";

interface SettingsTabProps {
  userLogin: string;
  activeSubTab?: "telegram" | "format" | "charts" | "spikes" | "blacklist" | "strategies";
  onSubTabChange?: (subTab: "telegram" | "format" | "charts" | "spikes" | "blacklist" | "strategies") => void;
}

export default function SettingsTab({ userLogin, activeSubTab: externalActiveSubTab, onSubTabChange }: SettingsTabProps) {
  // Состояние для активной подтемы настроек
  const [internalActiveSubTab, setInternalActiveSubTab] = useState<"telegram" | "format" | "charts" | "spikes" | "blacklist" | "strategies">("spikes");
  
  // Используем внешнее состояние, если оно передано, иначе внутреннее
  const activeSubTab = externalActiveSubTab ?? internalActiveSubTab;
  const setActiveSubTab = onSubTabChange ?? setInternalActiveSubTab;

  // Состояния для фильтров по биржам
  const [exchangeFilters, setExchangeFilters] = useState<Record<string, boolean>>({
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
  const [expandedExchanges, setExpandedExchanges] = useState<Record<string, boolean>>({});

  // Состояния для настроек пар
  const [pairSettings, setPairSettings] = useState<Record<string, { enabled: boolean; delta: string; volume: string; shadow: string; sendChart?: boolean }>>({});

  // Состояния для настроек графиков
  const [chartSettings, setChartSettings] = useState<Record<string, boolean>>({});

  // Состояния для чёрного списка
  const [blacklist, setBlacklist] = useState<string[]>([]);

  // Хуки
  const telegramSettings = useTelegramSettings();
  const messageTemplate = useMessageTemplate();
  const strategies = useStrategies();

  // Используем generateTemplateDescription из useStrategies
  const generateTemplateDescription = strategies.generateTemplateDescription;

  // Функция для извлечения текста из редактора
  const extractTextFromEditor = (): string => {
    return messageTemplate.extractTextFromEditor("messageTemplate");
  };

  // Функция для валидации стратегий
  const validateStrategies = (): boolean => {
    return strategies.validateStrategies();
  };

  // Функция для преобразования в понятные названия
  const convertToFriendlyNames = (template: string): string => {
    return convertToFriendlyKeys(template);
  };

  // Используем хук useSettings для загрузки и сохранения
  const settings = useSettings({
    userLogin,
    setTelegramBotToken: telegramSettings.setTelegramBotToken,
    setTelegramChatId: telegramSettings.setTelegramChatId,
    setIsTelegramConfigured: telegramSettings.setIsTelegramConfigured,
    setIsEditingTelegram: telegramSettings.setIsEditingTelegram,
    timezone: messageTemplate.timezone,
    setTimezone: messageTemplate.setTimezone,
    setExchangeFilters,
    setPairSettings,
    setChartSettings,
    setBlacklist,
    setMessageTemplate: messageTemplate.setMessageTemplate,
    setConditionalTemplates: strategies.setConditionalTemplates,
    telegramBotToken: telegramSettings.telegramBotToken,
    telegramChatId: telegramSettings.telegramChatId,
    exchangeFilters,
    pairSettings,
    chartSettings,
    blacklist,
    messageTemplate: messageTemplate.messageTemplate,
    conditionalTemplates: strategies.conditionalTemplates,
    extractTextFromEditor,
    validateStrategies,
    convertToFriendlyNames,
  });

  // Обертка для saveAllSettings, чтобы соответствовать типу Promise<void>
  const handleSave = async (): Promise<void> => {
    await settings.saveAllSettings();
  };

  // Автоматическое обновление тумблеров бирж при изменении состояния торговых пар
  useEffect(() => {
    setExchangeFilters((currentFilters) => {
      const updatedExchangeFilters = { ...currentFilters };
      let hasChanges = false;

      ["binance", "bybit", "bitget", "gate", "hyperliquid"].forEach((exchange) => {
        (["spot", "futures"] as const).forEach((market) => {
          const sectionKey = `${exchange}_${market}`;
          const prefix = `${exchange}_${market}_`;

          let hasEnabledPair = false;
          Object.keys(pairSettings).forEach((pairKey) => {
            if (pairKey.startsWith(prefix)) {
              const pairData = pairSettings[pairKey];
              if (pairData && pairData.enabled) {
                hasEnabledPair = true;
              }
            }
          });

          if (updatedExchangeFilters[sectionKey] !== hasEnabledPair) {
            updatedExchangeFilters[sectionKey] = hasEnabledPair;
            hasChanges = true;
          }
        });
      });

      return hasChanges ? updatedExchangeFilters : currentFilters;
    });
  }, [pairSettings]);

  // Загрузка настроек при монтировании
  useEffect(() => {
    if (userLogin) {
      settings.fetchUserSettings();
    }
  }, [userLogin]);

  // Синхронизация с внешним состоянием
  useEffect(() => {
    if (externalActiveSubTab !== undefined) {
      // Если передано внешнее состояние, используем его
      // Внутреннее состояние будет обновлено через setActiveSubTab
    }
  }, [externalActiveSubTab]);

  // Сохранение активной подтемы в localStorage (только для внутреннего состояния)
  useEffect(() => {
    if (typeof window === "undefined" || onSubTabChange) return; // Не сохраняем, если управление внешнее
    const storageKey = `settings_active_subtab_${userLogin || "default"}`;
    const stored = window.localStorage.getItem(storageKey) as
      | "telegram"
      | "format"
      | "charts"
      | "spikes"
      | "blacklist"
      | "strategies"
      | null;
    if (stored) {
      setInternalActiveSubTab(stored);
    }
  }, [userLogin, onSubTabChange]);

  useEffect(() => {
    if (typeof window === "undefined" || onSubTabChange) return; // Не сохраняем, если управление внешнее
    const storageKey = `settings_active_subtab_${userLogin || "default"}`;
    window.localStorage.setItem(storageKey, activeSubTab);
  }, [activeSubTab, userLogin, onSubTabChange]);

  // Обработчик тестирования Telegram
  const handleTestTelegram = async () => {
    const result = await telegramSettings.testTelegramConnection(userLogin);
    if (result.success) {
      settings.setSaveMessage({ type: "success", text: result.message });
    } else {
      settings.setSaveMessage({ type: "error", text: result.message });
    }
  };

  return (
    <div className="mb-6 md:mb-8">
      <div className="max-w-[1400px] mx-auto px-6 md:px-8">
        {/* Заголовок страницы */}
        <div className="mb-8">
          <h1 className="text-2xl md:text-3xl font-bold text-white mb-2">Настройки</h1>
          <p className="text-sm md:text-base text-zinc-400 max-w-2xl">
            Управление профилями, фильтрами и интеграциями
          </p>
        </div>

        {/* Навигация - скрыта, так как подтемы теперь в выпадающем меню Dashboard */}
        {/* <SettingsNavigation
          activeSection={activeSubTab}
          onSectionChange={setActiveSubTab}
        /> */}

        {/* Предупреждение о незаполненных Telegram-данных */}
        {(!telegramSettings.telegramChatId || !telegramSettings.telegramChatId.trim() || !telegramSettings.telegramBotToken || !telegramSettings.telegramBotToken.trim()) && (
          <div className="mb-6">
            <div className="bg-red-500/15 border border-red-500/60 text-red-300 px-4 py-3 rounded-lg text-sm flex items-start gap-2">
              <svg
                className="w-5 h-5 mt-0.5 flex-shrink-0"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M12 9v2m0 4h.01M10.29 3.86L1.82 18a1 1 0 00.86 1.5h18.64a1 1 0 00.86-1.5L13.71 3.86a1 1 0 00-1.72 0z"
                />
              </svg>
              <span>Введите данные Телеграм для получения детектов</span>
            </div>
          </div>
        )}

        {/* Уведомление по центру экрана */}
        {settings.saveMessage && (
          <div className="fixed top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2 z-50">
            <div className={`p-6 rounded-xl shadow-2xl max-w-md ${
              settings.saveMessage.type === "success" 
                ? "bg-green-500/95 text-white border-2 border-green-400" 
                : "bg-red-500/95 text-white border-2 border-red-400"
            }`}>
              <div className="flex items-start gap-3">
                {settings.saveMessage.type === "success" ? (
                  <svg className="w-6 h-6 mt-0.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                ) : (
                  <svg className="w-6 h-6 mt-0.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                )}
                <div className="flex-1">
                  <p className="font-semibold text-lg">{settings.saveMessage.type === "success" ? "Успешно сохранено" : "Ошибка"}</p>
                  <p className="text-sm mt-2 opacity-90">{settings.saveMessage.text}</p>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Контент в зависимости от выбранной подтемы */}
        {activeSubTab === "telegram" && (
          <TelegramSettings
            chatId={telegramSettings.telegramChatId}
            botToken={telegramSettings.telegramBotToken}
            isConfigured={telegramSettings.isTelegramConfigured}
            isEditing={telegramSettings.isEditingTelegram}
            chatIdError={telegramSettings.telegramChatIdError}
            botTokenError={telegramSettings.telegramBotTokenError}
            testing={telegramSettings.testing}
            onChatIdChange={telegramSettings.setTelegramChatId}
            onBotTokenChange={telegramSettings.setTelegramBotToken}
            onTest={handleTestTelegram}
            onToggleEdit={() => telegramSettings.setIsEditingTelegram(!telegramSettings.isEditingTelegram)}
            onSave={handleSave}
            saving={settings.saving}
          />
        )}

        {activeSubTab === "format" && (
          <MessageFormatSettings
            template={messageTemplate.messageTemplate}
            timezone={messageTemplate.timezone}
            onTemplateChange={messageTemplate.setMessageTemplate}
            onTimezoneChange={messageTemplate.setTimezone}
            isUserEditingRef={messageTemplate.isUserEditingRef}
          />
        )}

        {activeSubTab === "charts" && (
          <ChartSettings
            chartSettings={chartSettings}
            onChartSettingsChange={setChartSettings}
            onSave={handleSave}
            saving={settings.saving}
          />
        )}

        {activeSubTab === "spikes" && (
          <SpikesSettings
            exchangeFilters={exchangeFilters}
            pairSettings={pairSettings}
            chartSettings={chartSettings}
            expandedExchanges={expandedExchanges}
            onExchangeFiltersChange={setExchangeFilters}
            onPairSettingsChange={setPairSettings}
            onChartSettingsChange={setChartSettings}
            onExpandedExchangesChange={setExpandedExchanges}
            onSave={handleSave}
            saving={settings.saving}
          />
        )}

        {activeSubTab === "blacklist" && (
          <BlacklistSettings
            blacklist={blacklist}
            onBlacklistChange={setBlacklist}
          />
        )}

        {activeSubTab === "strategies" && (
          <StrategiesSettings
            conditionalTemplates={strategies.conditionalTemplates}
            strategyValidationErrors={strategies.strategyValidationErrors}
            isConditionalUserEditingRef={strategies.isConditionalUserEditingRef}
            onTemplatesChange={strategies.setConditionalTemplates}
            onValidationErrorsChange={strategies.setStrategyValidationErrors}
            onSave={handleSave}
            saving={settings.saving}
            extractTextFromEditor={extractTextFromEditor}
            messageTemplate={messageTemplate.messageTemplate}
            generateTemplateDescription={generateTemplateDescription}
          />
        )}
      </div>
    </div>
  );
}

