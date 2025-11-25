"use client";

import { useState, useCallback } from "react";
import { ConditionalTemplate } from "../types";
import { convertToTechnicalKeys } from "../utils/templateUtils";

export function useStrategies() {
  const [conditionalTemplates, setConditionalTemplates] = useState<ConditionalTemplate[]>([]);
  const [strategyValidationErrors, setStrategyValidationErrors] = useState<Record<number, {
    hasError: boolean;
    missingFields: string[];
    message: string;
  }>>({});
  
  const isConditionalUserEditingRef = { current: false };

  // Генерация описания стратегии
  const generateTemplateDescription = useCallback((template: ConditionalTemplate): string => {
    if (!template.conditions || template.conditions.length === 0) {
      return "Нет условий";
    }

    const parts: string[] = [];

    template.conditions.forEach((condition) => {
      switch (condition.type) {
        case "volume":
          if (condition.value !== undefined) {
            parts.push(`Объём ≥ ${condition.value.toLocaleString()} USDT`);
          }
          break;
        case "delta":
          if (condition.valueMin !== undefined) {
            const min = condition.valueMin;
            const max = condition.valueMax;
            if (max === null || max === undefined) {
              parts.push(`Дельта ≥ ${min}%`);
            } else {
              parts.push(`Дельта ${min}% - ${max}%`);
            }
          } else if (condition.value !== undefined) {
            parts.push(`Дельта ≥ ${condition.value}%`);
          }
          break;
        case "series":
          if (condition.count !== undefined && condition.timeWindowSeconds !== undefined) {
            const minutes = Math.floor(condition.timeWindowSeconds / 60);
            parts.push(`Серия: ${condition.count} стрел за ${minutes} мин`);
          }
          break;
        case "symbol":
          if (condition.symbol) {
            parts.push(`Монета: ${condition.symbol}`);
          }
          break;
        case "wick_pct":
          if (condition.valueMin !== undefined) {
            const min = condition.valueMin;
            const max = condition.valueMax;
            if (max === null || max === undefined) {
              parts.push(`Тень ≥ ${min}%`);
            } else {
              parts.push(`Тень ${min}% - ${max}%`);
            }
          }
          break;
        case "exchange_market":
          if (condition.exchange_market) {
            const [exchange, market] = condition.exchange_market.split("_");
            const exchangeNames: Record<string, string> = {
              binance: "Binance",
              gate: "Gate",
              bitget: "Bitget",
              bybit: "Bybit",
              hyperliquid: "Hyperliquid",
            };
            const marketNames: Record<string, string> = {
              spot: "Spot",
              futures: "Futures",
              linear: "Linear",
            };
            const exchangeName = exchangeNames[exchange] || exchange;
            const marketName = marketNames[market] || market;
            parts.push(`${exchangeName} ${marketName}`);
          } else if (condition.exchange && condition.market) {
            // Обратная совместимость
            const exchangeNames: Record<string, string> = {
              binance: "Binance",
              gate: "Gate",
              bitget: "Bitget",
              bybit: "Bybit",
              hyperliquid: "Hyperliquid",
            };
            const marketNames: Record<string, string> = {
              spot: "Spot",
              futures: "Futures",
              linear: "Linear",
            };
            const exchangeName = exchangeNames[condition.exchange] || condition.exchange;
            const marketName = marketNames[condition.market] || condition.market;
            parts.push(`${exchangeName} ${marketName}`);
          }
          break;
        case "direction":
          if (condition.direction) {
            parts.push(`Направление: ${condition.direction === "up" ? "Вверх ⬆️" : "Вниз ⬇️"}`);
          }
          break;
      }
    });

    if (parts.length === 0) {
      return "Нет условий";
    }

    return parts.join(" • ");
  }, []);

  // Валидация стратегий
  const validateStrategies = useCallback((templates: ConditionalTemplate[]): boolean => {
    const errors: Record<number, {
      hasError: boolean;
      missingFields: string[];
      message: string;
    }> = {};
    
    let hasErrors = false;
    
    templates.forEach((template, index) => {
      // Проверяем только если стратегия включена и useGlobalFilters = false
      if (template.enabled !== false && template.useGlobalFilters === false) {
        const missingFields: string[] = [];
        
        // Проверяем наличие базовых фильтров
        const hasDelta = template.conditions.some(c => c.type === "delta" && c.valueMin !== undefined);
        const hasVolume = template.conditions.some(c => c.type === "volume" && c.value !== undefined);
        const hasWickPct = template.conditions.some(c => c.type === "wick_pct" && c.valueMin !== undefined);
        
        if (!hasDelta) {
          missingFields.push("Дельта");
        }
        if (!hasVolume) {
          missingFields.push("Объём");
        }
        if (!hasWickPct) {
          missingFields.push("Тень");
        }
        
        if (missingFields.length > 0) {
          hasErrors = true;
          errors[index] = {
            hasError: true,
            missingFields,
            message: `Стратегия "${template.name || `Стратегия #${index + 1}`}" не может работать без базовых фильтров. Пожалуйста, либо включите 'Использовать мои фильтры из глобальных настроек', либо укажите значения для ${missingFields.join(", ")} в условиях стратегии.`
          };
        }
      }
    });
    
    setStrategyValidationErrors(errors);
    return !hasErrors;
  }, []);

  // Добавление стратегии
  const addStrategy = useCallback((baseTemplate?: string) => {
    const newTemplate: ConditionalTemplate = {
      name: undefined,
      enabled: true,
      useGlobalFilters: true,
      conditions: [{
        type: "volume",
        value: 0,
      }],
      template: baseTemplate ? convertToTechnicalKeys(baseTemplate) : "",
    };
    
    setConditionalTemplates(prev => [...prev, newTemplate]);
    return conditionalTemplates.length; // Возвращаем индекс новой стратегии
  }, [conditionalTemplates.length]);

  // Обновление стратегии
  const updateStrategy = useCallback((index: number, updates: Partial<ConditionalTemplate>) => {
    setConditionalTemplates(prev => {
      const updated = [...prev];
      if (updated[index]) {
        updated[index] = { ...updated[index], ...updates };
        // Обновляем описание, если изменились условия
        if (updates.conditions !== undefined) {
          updated[index].description = generateTemplateDescription(updated[index]);
        }
      }
      return updated;
    });
  }, [generateTemplateDescription]);

  // Удаление стратегии
  const deleteStrategy = useCallback((index: number) => {
    setConditionalTemplates(prev => prev.filter((_, i) => i !== index));
    // Удаляем ошибки валидации для удалённой стратегии
    setStrategyValidationErrors(prev => {
      const updated = { ...prev };
      delete updated[index];
      // Сдвигаем индексы ошибок
      const shifted: typeof prev = {};
      Object.entries(updated).forEach(([key, value]) => {
        const oldIndex = parseInt(key);
        if (oldIndex > index) {
          shifted[oldIndex - 1] = value;
        } else {
          shifted[oldIndex] = value;
        }
      });
      return shifted;
    });
  }, []);

  // Обновление условия в стратегии
  const updateCondition = useCallback((
    strategyIndex: number,
    conditionIndex: number,
    updates: Partial<ConditionalTemplate["conditions"][0]>
  ) => {
    setConditionalTemplates(prev => {
      const updated = [...prev];
      if (updated[strategyIndex]?.conditions[conditionIndex]) {
        updated[strategyIndex].conditions[conditionIndex] = {
          ...updated[strategyIndex].conditions[conditionIndex],
          ...updates,
        };
        // Обновляем описание стратегии
        updated[strategyIndex].description = generateTemplateDescription(updated[strategyIndex]);
      }
      return updated;
    });
  }, [generateTemplateDescription]);

  // Добавление условия в стратегию
  const addCondition = useCallback((
    strategyIndex: number,
    condition: ConditionalTemplate["conditions"][0]
  ) => {
    setConditionalTemplates(prev => {
      const updated = [...prev];
      if (updated[strategyIndex]) {
        updated[strategyIndex].conditions = [...updated[strategyIndex].conditions, condition];
        updated[strategyIndex].description = generateTemplateDescription(updated[strategyIndex]);
      }
      return updated;
    });
  }, [generateTemplateDescription]);

  // Удаление условия из стратегии
  const deleteCondition = useCallback((
    strategyIndex: number,
    conditionIndex: number
  ) => {
    setConditionalTemplates(prev => {
      const updated = [...prev];
      if (updated[strategyIndex]) {
        updated[strategyIndex].conditions = updated[strategyIndex].conditions.filter(
          (_, i) => i !== conditionIndex
        );
        updated[strategyIndex].description = generateTemplateDescription(updated[strategyIndex]);
      }
      return updated;
    });
  }, [generateTemplateDescription]);

  return {
    // Состояния
    conditionalTemplates,
    strategyValidationErrors,
    isConditionalUserEditingRef,
    // Сеттеры
    setConditionalTemplates,
    setStrategyValidationErrors,
    // Функции
    validateStrategies: () => validateStrategies(conditionalTemplates),
    generateTemplateDescription,
    addStrategy,
    updateStrategy,
    deleteStrategy,
    updateCondition,
    addCondition,
    deleteCondition,
  };
}

