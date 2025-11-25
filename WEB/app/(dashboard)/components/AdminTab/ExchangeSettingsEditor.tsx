"use client";

import { getPairsForExchange } from "./utils/pairUtils";

interface ExchangeSettingsEditorProps {
  exchangeFilters: Record<string, boolean>;
  pairSettings: Record<string, { enabled: boolean; delta: string; volume: string; shadow: string }>;
  onExchangeFiltersChange: (filters: Record<string, boolean>) => void;
  onPairSettingsChange: (settings: Record<string, { enabled: boolean; delta: string; volume: string; shadow: string }>) => void;
  openPairs: Record<string, boolean>;
  onOpenPairsChange: (openPairs: Record<string, boolean>) => void;
}

export default function ExchangeSettingsEditor({
  exchangeFilters,
  pairSettings,
  onExchangeFiltersChange,
  onPairSettingsChange,
  openPairs,
  onOpenPairsChange,
}: ExchangeSettingsEditorProps) {
  return (
    <div className="border-t border-zinc-700 pt-4">
      <h3 className="text-lg font-semibold text-white mb-3">Фильтры по биржам</h3>
      <p className="text-sm text-zinc-400 mb-4">Выберите биржи для мониторинга и настройте параметры</p>

      <div className="space-y-2">
        {["binance", "bybit", "bitget", "gate", "hyperliquid"].map((exchange) => {
          const exchangeDisplayName =
            exchange === "gate"
              ? "Gate"
              : exchange === "hyperliquid"
              ? "Hyperliquid"
              : exchange.charAt(0).toUpperCase() + exchange.slice(1);

          return (
            <div key={exchange} className="bg-zinc-800 rounded-lg overflow-hidden">
              {/* Заголовок биржи */}
              <div className="flex items-center gap-3 p-4">
                <div
                  className={`w-12 h-6 rounded-full transition-colors cursor-pointer ${
                    exchangeFilters[exchange] ? "bg-emerald-500" : "bg-zinc-600"
                  }`}
                  onClick={(e) => {
                    e.stopPropagation();
                    onExchangeFiltersChange({
                      ...exchangeFilters,
                      [exchange]: !exchangeFilters[exchange],
                    });
                  }}
                >
                  <div
                    className={`w-5 h-5 bg-white rounded-full transition-transform mt-0.5 ${
                      exchangeFilters[exchange] ? "translate-x-6" : "translate-x-1"
                    }`}
                  />
                </div>
                <span className="flex-1 text-white font-medium">{exchangeDisplayName}</span>
              </div>

              {/* Кнопки для открытия дополнительных пар */}
              {((exchange === "binance" || exchange === "bybit") && (
                <div className="px-4 pb-4 space-y-2">
                  <button
                    onClick={() => {
                      const key = `${exchange}_spot`;
                      onOpenPairsChange({
                        ...openPairs,
                        [key]: !openPairs[key],
                      });
                    }}
                    className="w-full px-3 py-1.5 bg-zinc-700 hover:bg-zinc-600 text-white text-sm font-medium rounded-lg transition-colors"
                  >
                    {openPairs[`${exchange}_spot`] ? "Скрыть пары Spot" : "Открыть дополнительные пары Spot"}
                  </button>
                  {exchange === "binance" && (
                    <button
                      onClick={() => {
                        const key = `${exchange}_futures`;
                        onOpenPairsChange({
                          ...openPairs,
                          [key]: !openPairs[key],
                        });
                      }}
                      className="w-full px-3 py-1.5 bg-zinc-700 hover:bg-zinc-600 text-white text-sm font-medium rounded-lg transition-colors"
                    >
                      {openPairs[`${exchange}_futures`] ? "Скрыть пары Futures" : "Открыть дополнительные пары Futures"}
                    </button>
                  )}
                </div>
              ))}

              {/* Дополнительные пары для Spot (если открыты) */}
              {((exchange === "binance" || exchange === "bybit") && openPairs[`${exchange}_spot`]) && (
                <div className="px-4 pb-4">
                  <div className="bg-zinc-950 rounded-lg p-4 border border-zinc-700">
                    <h4 className="text-sm font-medium text-white mb-4">Дополнительные пары для Spot</h4>
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                      {getPairsForExchange(exchange, "spot").map((pair) => {
                        const pairKey = `${exchange}_spot_${pair}`;
                        const savedPairData = pairSettings[pairKey];

                        const pairData =
                          savedPairData ||
                          ({
                            enabled: true,
                            delta: "0",
                            volume: "0",
                            shadow: "0",
                          } as { enabled: boolean; delta: string; volume: string; shadow: string });

                        return (
                          <div key={pair} className="bg-zinc-800 rounded-lg p-3 space-y-2">
                            <div className="flex items-center justify-between mb-2">
                              <div className="text-white font-medium text-sm">{pair}</div>
                              <div
                                className={`w-10 h-5 rounded-full transition-colors cursor-pointer ${
                                  pairData.enabled ? "bg-emerald-500" : "bg-zinc-600"
                                }`}
                                onClick={() => {
                                  onPairSettingsChange({
                                    ...pairSettings,
                                    [pairKey]: { ...pairData, enabled: !pairData.enabled },
                                  });
                                }}
                              >
                                <div
                                  className={`w-4 h-4 bg-white rounded-full transition-transform mt-0.5 ${
                                    pairData.enabled ? "translate-x-5" : "translate-x-1"
                                  }`}
                                />
                              </div>
                            </div>
                            <div>
                              <label className="block text-xs text-zinc-400 mb-1">Дельта %</label>
                              <input
                                type="number"
                                value={pairData.delta}
                                onChange={(e) => {
                                  onPairSettingsChange({
                                    ...pairSettings,
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
                                  onPairSettingsChange({
                                    ...pairSettings,
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
                                  onPairSettingsChange({
                                    ...pairSettings,
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
                </div>
              )}

              {/* Дополнительные пары для Futures (если открыты) */}
              {exchange === "binance" && openPairs[`${exchange}_futures`] && (
                <div className="px-4 pb-4">
                  <div className="bg-zinc-950 rounded-lg p-4 border border-zinc-700">
                    <h4 className="text-sm font-medium text-white mb-4">Дополнительные пары для Futures</h4>
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                      {getPairsForExchange(exchange, "futures").map((pair) => {
                        const pairKey = `${exchange}_futures_${pair}`;
                        const savedPairData = pairSettings[pairKey];

                        const pairData =
                          savedPairData ||
                          ({
                            enabled: true,
                            delta: "0",
                            volume: "0",
                            shadow: "0",
                          } as { enabled: boolean; delta: string; volume: string; shadow: string });

                        return (
                          <div key={pair} className="bg-zinc-800 rounded-lg p-3 space-y-2">
                            <div className="flex items-center justify-between mb-2">
                              <div className="text-white font-medium text-sm">{pair}</div>
                              <div
                                className={`w-10 h-5 rounded-full transition-colors cursor-pointer ${
                                  pairData.enabled ? "bg-emerald-500" : "bg-zinc-600"
                                }`}
                                onClick={() => {
                                  onPairSettingsChange({
                                    ...pairSettings,
                                    [pairKey]: { ...pairData, enabled: !pairData.enabled },
                                  });
                                }}
                              >
                                <div
                                  className={`w-4 h-4 bg-white rounded-full transition-transform mt-0.5 ${
                                    pairData.enabled ? "translate-x-5" : "translate-x-1"
                                  }`}
                                />
                              </div>
                            </div>
                            <div>
                              <label className="block text-xs text-zinc-400 mb-1">Дельта %</label>
                              <input
                                type="number"
                                value={pairData.delta}
                                onChange={(e) => {
                                  onPairSettingsChange({
                                    ...pairSettings,
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
                                  onPairSettingsChange({
                                    ...pairSettings,
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
                                  onPairSettingsChange({
                                    ...pairSettings,
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
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

