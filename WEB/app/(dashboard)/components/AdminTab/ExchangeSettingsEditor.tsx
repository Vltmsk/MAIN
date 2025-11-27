"use client";

import { getPairsForExchange, getQuoteCurrencyForExchange, shouldShowPairsImmediately } from "./utils/pairUtils";

interface ExchangeSettingsEditorProps {
  exchangeFilters: Record<string, boolean>;
  pairSettings: Record<string, { enabled: boolean; delta: string; volume: string; shadow: string }>;
  onExchangeFiltersChange: (filters: Record<string, boolean>) => void;
  onPairSettingsChange: (settings: Record<string, { enabled: boolean; delta: string; volume: string; shadow: string }>) => void;
  expandedExchanges: Record<string, boolean>;
  onExpandedExchangesChange: (expanded: Record<string, boolean>) => void;
}

export default function ExchangeSettingsEditor({
  exchangeFilters,
  pairSettings,
  onExchangeFiltersChange,
  onPairSettingsChange,
  expandedExchanges,
  onExpandedExchangesChange,
}: ExchangeSettingsEditorProps) {
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

  const handlePairSettingsChange = (pairKey: string, settings: { enabled: boolean; delta: string; volume: string; shadow: string }) => {
    onPairSettingsChange({
      ...pairSettings,
      [pairKey]: settings,
    });
  };

  // Создаем массив всех комбинаций биржа + рынок
  const exchangeMarketCombinations: Array<{exchange: string, market: "spot" | "futures"}> = [];
  ["binance", "bybit", "bitget", "gate", "hyperliquid"].forEach((exchange) => {
    exchangeMarketCombinations.push({exchange, market: "spot"});
    exchangeMarketCombinations.push({exchange, market: "futures"});
  });

  return (
    <div>
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
  );
}

