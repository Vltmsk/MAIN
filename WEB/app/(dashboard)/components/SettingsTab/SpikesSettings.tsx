"use client";

import { useState, useRef } from "react";
import { getPairsForExchange, getQuoteCurrencyForExchange, shouldShowPairsImmediately } from "./utils/pairUtils";
import { formatNumberCompact } from "./utils/formatters";

interface PairSettings {
  enabled: boolean;
  delta: string;
  volume: string;
  shadow: string;
  sendChart?: boolean;
}

interface SpikesSettingsProps {
  exchangeFilters: Record<string, boolean>;
  pairSettings: Record<string, PairSettings>;
  chartSettings: Record<string, boolean>;
  expandedExchanges: Record<string, boolean>;
  onExchangeFiltersChange: (filters: Record<string, boolean>) => void;
  onPairSettingsChange: (settings: Record<string, PairSettings>) => void;
  onChartSettingsChange: (settings: Record<string, boolean>) => void;
  onExpandedExchangesChange: (expanded: Record<string, boolean>) => void;
  onSave: () => Promise<void>;
  saving: boolean;
}

export default function SpikesSettings({
  exchangeFilters,
  pairSettings,
  chartSettings,
  expandedExchanges,
  onExchangeFiltersChange,
  onPairSettingsChange,
  onChartSettingsChange,
  onExpandedExchangesChange,
  onSave,
  saving,
}: SpikesSettingsProps) {
  const [editingCell, setEditingCell] = useState<{
    rowId: string;
    field: "delta" | "volume" | "shadow";
    value: string;
    previousValue: string;
  } | null>(null);
  const [highlightedRowId, setHighlightedRowId] = useState<string | null>(null);
  const highlightTimeoutRef = useRef<number | null>(null);

  const handleExchangeToggle = (exchange: string, market: "spot" | "futures", enabled: boolean) => {
    const sectionKey = `${exchange}_${market}`;
    
    // Обновляем состояние биржи
    onExchangeFiltersChange({
      ...exchangeFilters,
      [sectionKey]: enabled,
    });
    
    // Автоматически включаем/отключаем все торговые пары этой биржи
    const updatedPairSettings = { ...pairSettings };
    const prefix = `${exchange}_${market}_`;
    
    // Обновляем все существующие пары для этой биржи и рынка
    Object.keys(pairSettings).forEach((pairKey) => {
      if (pairKey.startsWith(prefix)) {
        const currentPairData = pairSettings[pairKey];
        updatedPairSettings[pairKey] = {
          ...currentPairData,
          enabled: enabled,
        };
      }
    });
    
    // Также обновляем стандартные пары, если их еще нет в pairSettings
    const pairs = getPairsForExchange(exchange, market);
    pairs.forEach((pair) => {
      const pairKey = `${exchange}_${market}_${pair}`;
      if (!(pairKey in updatedPairSettings)) {
        updatedPairSettings[pairKey] = {
          enabled: enabled,
          delta: "",
          volume: "",
          shadow: "",
        };
      } else {
        // Обновляем enabled для существующих пар
        updatedPairSettings[pairKey] = {
          ...updatedPairSettings[pairKey],
          enabled: enabled,
        };
      }
    });
    
    onPairSettingsChange(updatedPairSettings);
  };

  const handlePairSettingsChange = (pairKey: string, settings: PairSettings) => {
    onPairSettingsChange({
      ...pairSettings,
      [pairKey]: settings,
    });
  };

  const handleToggleStatus = async (row: {
    exchangeKey: string;
    marketKey: "spot" | "futures";
    pair: string | null;
    delta: string;
    volume: string;
    shadow: string;
  }) => {
    const pairKey = `${row.exchangeKey}_${row.marketKey}_${row.pair}`;
    const currentPair = pairSettings[pairKey] || {
      enabled: false,
      delta: row.delta,
      volume: row.volume,
      shadow: row.shadow,
    };

    onPairSettingsChange({
      ...pairSettings,
      [pairKey]: { ...currentPair, enabled: !currentPair.enabled },
    });

    await onSave();
  };

  const commitInlineEdit = async (
    row: {
      exchangeKey: string;
      marketKey: "spot" | "futures";
      pair: string | null;
      delta: string;
      volume: string;
      shadow: string;
    },
    field: "delta" | "volume" | "shadow",
    newValue: string,
    previousValue: string
  ) => {
    // Обновляем состояние
    const pairKey = `${row.exchangeKey}_${row.marketKey}_${row.pair}`;
    const currentPair = pairSettings[pairKey] || {
      enabled: true,
      delta: row.delta,
      volume: row.volume,
      shadow: row.shadow,
    };

    onPairSettingsChange({
      ...pairSettings,
      [pairKey]: {
        ...currentPair,
        [field]: newValue,
      },
    });

    try {
      await onSave();
      // Подсветка строки при успешном сохранении
      if (highlightTimeoutRef.current) {
        window.clearTimeout(highlightTimeoutRef.current);
      }
      const rowId = `${row.exchangeKey}_${row.marketKey}_${row.pair}`;
      setHighlightedRowId(rowId);
      highlightTimeoutRef.current = window.setTimeout(() => {
        setHighlightedRowId(null);
      }, 2000);
    } catch (error) {
      // Откатываем в случае ошибки
      const pairKey = `${row.exchangeKey}_${row.marketKey}_${row.pair}`;
      const currentPair = pairSettings[pairKey];
      if (!currentPair) return;

      onPairSettingsChange({
        ...pairSettings,
        [pairKey]: {
          ...currentPair,
          [field]: previousValue,
        },
      });
    }

    setEditingCell(null);
  };

  const handleCellKeyDown = async (
    e: React.KeyboardEvent<HTMLInputElement>,
    row: {
      exchangeKey: string;
      marketKey: "spot" | "futures";
      pair: string | null;
      delta: string;
      volume: string;
      shadow: string;
    },
    field: "delta" | "volume" | "shadow"
  ) => {
    if (!editingCell) return;

    if (e.key === "Enter") {
      e.preventDefault();
      await commitInlineEdit(row, field, editingCell.value, editingCell.previousValue);
    } else if (e.key === "Escape") {
      e.preventDefault();
      setEditingCell(null);
    }
  };

  const handleCellBlur = async (
    row: {
      exchangeKey: string;
      marketKey: "spot" | "futures";
      pair: string | null;
      delta: string;
      volume: string;
      shadow: string;
    },
    field: "delta" | "volume" | "shadow"
  ) => {
    if (!editingCell) return;
    await commitInlineEdit(row, field, editingCell.value, editingCell.previousValue);
  };

  // Создаем массив всех комбинаций биржа + рынок
  const exchangeMarketCombinations: Array<{exchange: string, market: "spot" | "futures"}> = [];
  ["binance", "bybit", "bitget", "gate", "hyperliquid"].forEach((exchange) => {
    exchangeMarketCombinations.push({exchange, market: "spot"});
    exchangeMarketCombinations.push({exchange, market: "futures"});
  });

  // Собираем активные фильтры для таблицы
  type ActiveFilterRow = {
    id: string;
    exchangeKey: string;
    exchangeLabel: string;
    marketKey: "spot" | "futures";
    marketLabel: string;
    pair: string | null;
    delta: string;
    volume: string;
    shadow: string;
    enabled: boolean;
  };

  const activeFilterRows: ActiveFilterRow[] = [];
  ["binance", "bybit", "bitget", "gate", "hyperliquid"].forEach((exchangeKey) => {
    const exchangeDisplayName =
      exchangeKey === "gate"
        ? "Gate"
        : exchangeKey === "hyperliquid"
        ? "Hyperliquid"
        : exchangeKey.charAt(0).toUpperCase() + exchangeKey.slice(1);

    (["spot", "futures"] as const).forEach((marketKey) => {
      const marketLabel = marketKey === "spot" ? "Spot" : "Futures";

      Object.entries(pairSettings).forEach(([key, pairData]) => {
        if (!key.startsWith(`${exchangeKey}_${marketKey}_`)) return;
        if (!pairData?.enabled) return;

        const parts = key.split("_");
        if (parts.length < 3) return;
        const pair = parts.slice(2).join("_");
        const id = `${exchangeKey}_${marketKey}_${pair}`;

        activeFilterRows.push({
          id,
          exchangeKey,
          exchangeLabel: exchangeDisplayName,
          marketKey,
          marketLabel,
          pair,
          delta: pairData.delta || "0",
          volume: pairData.volume || "0",
          shadow: pairData.shadow || "0",
          enabled: pairData.enabled,
        });
      });
    });
  });

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
      {/* Фильтры по биржам */}
      <div className="space-y-6">
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6">
          <div className="flex items-center justify-between mb-1">
            <div className="flex items-center gap-2">
              <h2 className="text-xl font-bold text-white">Фильтры по биржам</h2>
              <svg className="w-5 h-5 text-zinc-400 cursor-help" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <title>Выберите биржи для мониторинга и настройте параметры детектирования для каждой биржи отдельно (Spot и Futures). Можно включить/выключить биржи и настроить минимальные значения дельты, объёма и тени свечи.</title>
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
            <button
              onClick={onSave}
              disabled={saving}
              className="px-4 py-2 bg-gradient-to-r from-emerald-500 to-emerald-600 hover:from-emerald-600 hover:to-emerald-700 text-white text-sm font-medium rounded-lg smooth-transition ripple hover-glow shadow-emerald disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {saving ? "Сохранение..." : "Сохранить изменения"}
            </button>
          </div>
          <p className="text-sm text-zinc-400 mb-6">Выберите биржи для мониторинга и настройте параметры детектирования для каждой биржи отдельно (Spot и Futures). Можно включить/выключить биржи и настроить минимальные значения дельты, объёма и тени свечи.</p>
          
          <div className="space-y-2">
            {exchangeMarketCombinations.map(({exchange, market}) => {
              const sectionKey = `${exchange}_${market}`;
              const isExpanded = expandedExchanges[sectionKey] || false;
              const exchangeDisplayName = exchange === "gate" ? "Gate" : exchange === "hyperliquid" ? "Hyperliquid" : exchange.charAt(0).toUpperCase() + exchange.slice(1);
              const marketDisplayName = market === "spot" ? "Spot" : "Futures";
              const pairs = getPairsForExchange(exchange, market);
              const showPairsImmediately = shouldShowPairsImmediately(exchange, market);
              
              return (
                <div key={sectionKey} className="bg-zinc-800 rounded-lg overflow-hidden">
                  {/* Заголовок секции */}
                  <div className="flex items-center gap-3 p-4">
                    <div
                      className={`w-12 h-6 rounded-full transition-colors cursor-pointer ${
                        exchangeFilters[sectionKey] ? "bg-emerald-500" : "bg-zinc-600"
                      }`}
                      onClick={(e) => {
                        e.stopPropagation();
                        handleExchangeToggle(exchange, market, !exchangeFilters[sectionKey]);
                      }}
                    >
                      <div className={`w-5 h-5 bg-white rounded-full transition-transform mt-0.5 ${
                        exchangeFilters[sectionKey] ? "translate-x-6" : "translate-x-1"
                      }`} />
                    </div>
                    <span
                      className="flex-1 text-white font-medium cursor-pointer hover:text-zinc-300 transition-colors"
                      onClick={() => {
                        onExpandedExchangesChange({
                          ...expandedExchanges,
                          [sectionKey]: !isExpanded,
                        });
                      }}
                    >
                      {exchangeDisplayName} {marketDisplayName}
                    </span>
                    <svg
                      className={`w-5 h-5 text-zinc-400 transition-transform cursor-pointer ${
                        isExpanded ? "rotate-180" : ""
                      }`}
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                      onClick={() => {
                        onExpandedExchangesChange({
                          ...expandedExchanges,
                          [sectionKey]: !isExpanded,
                        });
                      }}
                    >
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                    </svg>
                  </div>
                  
                  {/* Раскрывающийся контент */}
                  {isExpanded && (
                    <div className="px-4 pb-4">
                      {showPairsImmediately ? (
                        // Для Binance Spot, Binance Futures и Bybit Spot - показываем таблицу всех пар
                        <div className="bg-zinc-900 rounded-lg p-4 border border-zinc-700 w-full">
                          <h4 className="text-sm font-medium text-white mb-4">Торговые пары</h4>
                          <div className="overflow-x-auto w-full">
                            <table className="border-collapse w-full">
                              <thead>
                                <tr className="border-b border-zinc-700">
                                  <th className="text-left py-2 px-3 text-xs font-semibold text-zinc-300">Пара</th>
                                  <th className="text-left py-2 px-3 text-xs font-semibold text-zinc-300">Включено</th>
                                  <th className="text-left py-2 px-3 text-xs font-semibold text-zinc-300">Дельта %</th>
                                  <th className="text-left py-2 px-3 text-xs font-semibold text-zinc-300">Объём USDT</th>
                                  <th className="text-left py-2 px-3 text-xs font-semibold text-zinc-300">Тень %</th>
                                </tr>
                              </thead>
                              <tbody>
                                {pairs.map((pair) => {
                                  const pairKey = `${exchange}_${market}_${pair}`;
                                  const savedPairData = pairSettings[pairKey];
                                  
                                  const pairData = savedPairData || {
                                    enabled: false,
                                    delta: "",
                                    volume: "",
                                    shadow: ""
                                  };
                                  
                                  return (
                                    <tr key={pair} className={`border-b border-zinc-800 hover:bg-zinc-800/50 ${!pairData.enabled ? "opacity-60" : ""}`}>
                                      <td className="py-2 px-3 text-white font-medium text-sm">{pair}</td>
                                      <td className="py-2 px-3">
                                        <div
                                          className={`w-10 h-5 rounded-full transition-colors cursor-pointer inline-flex ${
                                            pairData.enabled ? "bg-emerald-500" : "bg-zinc-600"
                                          }`}
                                          onClick={() => {
                                            handlePairSettingsChange(pairKey, { ...pairData, enabled: !pairData.enabled });
                                          }}
                                        >
                                          <div className={`w-4 h-4 bg-white rounded-full transition-transform mt-0.5 ${
                                            pairData.enabled ? "translate-x-5" : "translate-x-1"
                                          }`} />
                                        </div>
                                      </td>
                                      <td className="py-2 px-3">
                                        <input
                                          type="number"
                                          min="0"
                                          step="any"
                                          value={pairData.delta}
                                          onChange={(e) => {
                                            const value = e.target.value;
                                            if (value === "" || !value.startsWith("-")) {
                                              if (value === "") {
                                                handlePairSettingsChange(pairKey, { ...pairData, delta: value });
                                              } else {
                                                const numValue = parseFloat(value);
                                                if (numValue >= 0 && !isNaN(numValue)) {
                                                  handlePairSettingsChange(pairKey, { ...pairData, delta: value });
                                                }
                                              }
                                            }
                                          }}
                                          className="w-20 px-2 py-1 bg-zinc-800 border border-zinc-700 rounded text-white text-xs focus:outline-none focus:ring-1 focus:ring-emerald-500"
                                          placeholder=""
                                        />
                                      </td>
                                      <td className="py-2 px-3">
                                        <input
                                          type="number"
                                          min="0"
                                          step="any"
                                          value={pairData.volume}
                                          onChange={(e) => {
                                            const value = e.target.value;
                                            if (value === "" || !value.startsWith("-")) {
                                              if (value === "") {
                                                handlePairSettingsChange(pairKey, { ...pairData, volume: value });
                                              } else {
                                                const numValue = parseFloat(value);
                                                if (numValue >= 0 && !isNaN(numValue)) {
                                                  handlePairSettingsChange(pairKey, { ...pairData, volume: value });
                                                }
                                              }
                                            }
                                          }}
                                          className="w-24 px-2 py-1 bg-zinc-800 border border-zinc-700 rounded text-white text-xs focus:outline-none focus:ring-1 focus:ring-emerald-500"
                                          placeholder=""
                                        />
                                      </td>
                                      <td className="py-2 px-3">
                                        <input
                                          type="number"
                                          min="0"
                                          step="any"
                                          value={pairData.shadow}
                                          onChange={(e) => {
                                            const value = e.target.value;
                                            if (value === "" || !value.startsWith("-")) {
                                              if (value === "") {
                                                handlePairSettingsChange(pairKey, { ...pairData, shadow: value });
                                              } else {
                                                const numValue = parseFloat(value);
                                                if (numValue >= 0 && !isNaN(numValue)) {
                                                  handlePairSettingsChange(pairKey, { ...pairData, shadow: value });
                                                }
                                              }
                                            }
                                          }}
                                          className="w-20 px-2 py-1 bg-zinc-800 border border-zinc-700 rounded text-white text-xs focus:outline-none focus:ring-1 focus:ring-emerald-500"
                                          placeholder=""
                                        />
                                      </td>
                                    </tr>
                                  );
                                })}
                              </tbody>
                            </table>
                          </div>
                        </div>
                      ) : (
                        // Для остальных бирж - показываем настройки для одной пары
                        <div className="bg-zinc-900 rounded-lg p-4 space-y-4">
                          {(() => {
                            const quoteCurrency = getQuoteCurrencyForExchange(exchange, market);
                            const pairKey = `${exchange}_${market}_${quoteCurrency}`;
                            const savedPairData = pairSettings[pairKey];
                            
                            const pairData = savedPairData || {
                              enabled: false,
                              delta: "",
                              volume: "",
                              shadow: ""
                            };
                            
                            return (
                              <>
                                {quoteCurrency && (
                                  <div className="flex items-center justify-between mb-4">
                                    <div>
                                      <h3 className="text-white font-medium">{quoteCurrency}</h3>
                                      <p className="text-sm text-zinc-400">Торговая пара</p>
                                    </div>
                                    <div
                                      className={`w-12 h-6 rounded-full transition-colors cursor-pointer ${
                                        pairData.enabled ? "bg-emerald-500" : "bg-zinc-600"
                                      }`}
                                      onClick={() => {
                                        handlePairSettingsChange(pairKey, { ...pairData, enabled: !pairData.enabled });
                                      }}
                                    >
                                      <div className={`w-5 h-5 bg-white rounded-full transition-transform mt-0.5 ${
                                        pairData.enabled ? "translate-x-6" : "translate-x-1"
                                      }`} />
                                    </div>
                                  </div>
                                )}
                                
                                <div className="grid grid-cols-3 gap-3">
                                  <div>
                                    <label className="block text-xs text-zinc-400 mb-1">Дельта %</label>
                                    <input
                                      type="number"
                                      min="0"
                                      step="any"
                                      value={pairData.delta}
                                      onChange={(e) => {
                                        const value = e.target.value;
                                        if (value === "" || !value.startsWith("-")) {
                                          if (value === "") {
                                            handlePairSettingsChange(pairKey, { ...pairData, delta: value });
                                          } else {
                                            const numValue = parseFloat(value);
                                            if (numValue >= 0 && !isNaN(numValue)) {
                                              handlePairSettingsChange(pairKey, { ...pairData, delta: value });
                                            }
                                          }
                                        }
                                      }}
                                      className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                                    />
                                  </div>
                                  <div>
                                    <label className="block text-xs text-zinc-400 mb-1">Объём USDT</label>
                                    <input
                                      type="number"
                                      min="0"
                                      step="any"
                                      value={pairData.volume}
                                      onChange={(e) => {
                                        const value = e.target.value;
                                        if (value === "" || !value.startsWith("-")) {
                                          if (value === "") {
                                            handlePairSettingsChange(pairKey, { ...pairData, volume: value });
                                          } else {
                                            const numValue = parseFloat(value);
                                            if (numValue >= 0 && !isNaN(numValue)) {
                                              handlePairSettingsChange(pairKey, { ...pairData, volume: value });
                                            }
                                          }
                                        }
                                      }}
                                      className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                                    />
                                  </div>
                                  <div>
                                    <label className="block text-xs text-zinc-400 mb-1">Тень %</label>
                                    <input
                                      type="number"
                                      min="0"
                                      step="any"
                                      value={pairData.shadow}
                                      onChange={(e) => {
                                        const value = e.target.value;
                                        if (value === "" || !value.startsWith("-")) {
                                          if (value === "") {
                                            handlePairSettingsChange(pairKey, { ...pairData, shadow: value });
                                          } else {
                                            const numValue = parseFloat(value);
                                            if (numValue >= 0 && !isNaN(numValue)) {
                                              handlePairSettingsChange(pairKey, { ...pairData, shadow: value });
                                            }
                                          }
                                        }
                                      }}
                                      className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                                    />
                                  </div>
                                </div>
                              </>
                            );
                          })()}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      </div>
      
      {/* Правая колонка - Активные фильтры */}
      <div>
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6">
          <h2 className="text-xl font-bold text-white mb-1">Активные фильтры</h2>
          <p className="text-xs text-zinc-500 mb-4">
            Сводная таблица по всем включённым фильтрам прострелов
          </p>

          {activeFilterRows.length === 0 ? (
            <div className="text-center py-8">
              <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-zinc-800/50 mb-3">
                <svg className="w-8 h-8 text-zinc-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                  />
                </svg>
              </div>
              <p className="text-zinc-400 text-sm">Нет активных фильтров</p>
              <p className="text-zinc-500 text-xs mt-1">
                Включите биржи и пары в левом блоке для отображения активных фильтров
              </p>
            </div>
          ) : (
            <div className="mt-2 border border-zinc-800/80 rounded-lg bg-zinc-900/60">
              <div className="overflow-x-auto rounded-lg">
                <table className="w-full text-xs md:text-sm border-separate border-spacing-0">
                  <thead className="sticky top-0 z-10 bg-zinc-900/95 backdrop-blur border-b border-zinc-800">
                    <tr>
                      <th className="px-3 md:px-4 py-2 md:py-3 text-left font-semibold text-zinc-300 text-xs md:text-sm">
                        Биржа
                      </th>
                      <th className="px-3 md:px-4 py-2 md:py-3 text-left font-semibold text-zinc-300 text-xs md:text-sm">
                        Рынок
                      </th>
                      <th className="px-3 md:px-4 py-2 md:py-3 text-left font-semibold text-zinc-300 text-xs md:text-sm">
                        Пара
                      </th>
                      <th className="px-3 md:px-4 py-2 md:py-3 text-right font-semibold text-zinc-300 text-xs md:text-sm">
                        Дельта %
                      </th>
                      <th className="px-3 md:px-4 py-2 md:py-3 text-right font-semibold text-zinc-300 text-xs md:text-sm">
                        Объём, USDT
                      </th>
                      <th className="px-3 md:px-4 py-2 md:py-3 text-right font-semibold text-zinc-300 text-xs md:text-sm">
                        Тень %
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {activeFilterRows.map((row, index) => {
                      const isHighlighted = highlightedRowId === row.id;
                      return (
                        <tr
                          key={row.id}
                          className={`border-b border-zinc-800/70 transition-colors ${
                            index % 2 === 0
                              ? "bg-zinc-900/40"
                              : "bg-zinc-900/20"
                          } hover:bg-zinc-800/60 ${
                            isHighlighted ? "ring-1 ring-emerald-500/60 bg-emerald-500/10" : ""
                          }`}
                        >
                          <td className="px-3 md:px-4 py-2 md:py-2.5 text-white text-xs md:text-sm whitespace-nowrap">
                            {row.exchangeLabel}
                          </td>
                          <td className="px-3 md:px-4 py-2 md:py-2.5 text-xs md:text-sm whitespace-nowrap">
                            <span
                              className={`inline-flex items-center px-2 py-0.5 rounded-full border text-[10px] md:text-xs ${
                                row.marketKey === "spot"
                                  ? "bg-emerald-500/10 border-emerald-500/40 text-emerald-300"
                                  : "bg-blue-500/10 border-blue-500/40 text-blue-300"
                              }`}
                            >
                              {row.marketLabel}
                            </span>
                          </td>
                          <td className="px-3 md:px-4 py-2 md:py-2.5 text-xs md:text-sm text-zinc-200 whitespace-nowrap">
                            {row.pair ?? "USDT"}
                          </td>
                          <td
                            className="px-3 md:px-4 py-2 md:py-2.5 text-right text-xs md:text-sm text-zinc-100 cursor-pointer"
                            onClick={() => {
                              setEditingCell({
                                rowId: row.id,
                                field: "delta",
                                value: row.delta,
                                previousValue: row.delta,
                              });
                            }}
                          >
                            {editingCell &&
                            editingCell.rowId === row.id &&
                            editingCell.field === "delta" ? (
                              <input
                                type="number"
                                min="0"
                                step="any"
                                className="w-full px-2 py-1 bg-zinc-800 border border-emerald-500 rounded text-right text-xs md:text-sm text-white focus:outline-none focus:ring-1 focus:ring-emerald-500"
                                value={editingCell.value}
                                autoFocus
                                onChange={(e) => {
                                  const value = e.target.value;
                                  if (value === "" || !value.startsWith("-")) {
                                    if (value === "") {
                                      setEditingCell((prev) =>
                                        prev
                                          ? { ...prev, value: value }
                                          : prev
                                      );
                                    } else {
                                      const numValue = parseFloat(value);
                                      if (numValue >= 0 && !isNaN(numValue)) {
                                        setEditingCell((prev) =>
                                          prev
                                            ? { ...prev, value: value }
                                            : prev
                                        );
                                      }
                                    }
                                  }
                                }}
                                onBlur={() => handleCellBlur(row, "delta")}
                                onKeyDown={(e) => handleCellKeyDown(e, row, "delta")}
                              />
                            ) : (
                              formatNumberCompact(row.delta)
                            )}
                          </td>
                          <td
                            className="px-3 md:px-4 py-2 md:py-2.5 text-right text-xs md:text-sm text-zinc-100 cursor-pointer whitespace-nowrap"
                            onClick={() => {
                              setEditingCell({
                                rowId: row.id,
                                field: "volume",
                                value: row.volume,
                                previousValue: row.volume,
                              });
                            }}
                          >
                            {editingCell &&
                            editingCell.rowId === row.id &&
                            editingCell.field === "volume" ? (
                              <input
                                type="number"
                                min="0"
                                step="any"
                                className="w-full px-2 py-1 bg-zinc-800 border border-emerald-500 rounded text-right text-xs md:text-sm text-white focus:outline-none focus:ring-1 focus:ring-emerald-500"
                                value={editingCell.value}
                                autoFocus
                                onChange={(e) => {
                                  const value = e.target.value;
                                  if (value === "" || !value.startsWith("-")) {
                                    if (value === "") {
                                      setEditingCell((prev) =>
                                        prev
                                          ? { ...prev, value: value }
                                          : prev
                                      );
                                    } else {
                                      const numValue = parseFloat(value);
                                      if (numValue >= 0 && !isNaN(numValue)) {
                                        setEditingCell((prev) =>
                                          prev
                                            ? { ...prev, value: value }
                                            : prev
                                        );
                                      }
                                    }
                                  }
                                }}
                                onBlur={() => handleCellBlur(row, "volume")}
                                onKeyDown={(e) => handleCellKeyDown(e, row, "volume")}
                              />
                            ) : (
                              formatNumberCompact(row.volume)
                            )}
                          </td>
                          <td
                            className="px-3 md:px-4 py-2 md:py-2.5 text-right text-xs md:text-sm text-zinc-100 cursor-pointer"
                            onClick={() => {
                              setEditingCell({
                                rowId: row.id,
                                field: "shadow",
                                value: row.shadow,
                                previousValue: row.shadow,
                              });
                            }}
                          >
                            {editingCell &&
                            editingCell.rowId === row.id &&
                            editingCell.field === "shadow" ? (
                              <input
                                type="number"
                                min="0"
                                step="any"
                                className="w-full px-2 py-1 bg-zinc-800 border border-emerald-500 rounded text-right text-xs md:text-sm text-white focus:outline-none focus:ring-1 focus:ring-emerald-500"
                                value={editingCell.value}
                                autoFocus
                                onChange={(e) => {
                                  const value = e.target.value;
                                  if (value === "" || !value.startsWith("-")) {
                                    if (value === "") {
                                      setEditingCell((prev) =>
                                        prev
                                          ? { ...prev, value: value }
                                          : prev
                                      );
                                    } else {
                                      const numValue = parseFloat(value);
                                      if (numValue >= 0 && !isNaN(numValue)) {
                                        setEditingCell((prev) =>
                                          prev
                                            ? { ...prev, value: value }
                                            : prev
                                        );
                                      }
                                    }
                                  }
                                }}
                                onBlur={() => handleCellBlur(row, "shadow")}
                                onKeyDown={(e) => handleCellKeyDown(e, row, "shadow")}
                              />
                            ) : (
                              formatNumberCompact(row.shadow)
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

