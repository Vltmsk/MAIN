"use client";

import { getPairsForExchange } from "./utils/pairUtils";

interface ChartSettingsProps {
  chartSettings: Record<string, boolean>;
  onChartSettingsChange: (settings: Record<string, boolean>) => void;
  onSave: () => Promise<void>;
  saving?: boolean;
}

export default function ChartSettings({
  chartSettings,
  onChartSettingsChange,
  onSave,
  saving = false,
}: ChartSettingsProps) {
  // Функция для проверки, все ли графики включены
  const areAllChartsEnabled = (): boolean => {
    const exchanges = ["binance", "bybit", "bitget", "gate", "hyperliquid"];
    for (const exchange of exchanges) {
      const spotPairs = getPairsForExchange(exchange, "spot");
      const futuresPairs = getPairsForExchange(exchange, "futures");
      
      for (const pair of [...spotPairs, ...futuresPairs]) {
        const market = spotPairs.includes(pair) ? "spot" : "futures";
        const currencyKey = `${exchange}_${market}_${pair}`;
        if (chartSettings[currencyKey] !== true) {
          return false;
        }
      }
    }
    return true;
  };

  // Функция для переключения всех графиков
  const toggleAllCharts = () => {
    const allEnabled = areAllChartsEnabled();
    const newSettings: Record<string, boolean> = { ...chartSettings };
    
    const exchanges = ["binance", "bybit", "bitget", "gate", "hyperliquid"];
    exchanges.forEach((exchange) => {
      const spotPairs = getPairsForExchange(exchange, "spot");
      const futuresPairs = getPairsForExchange(exchange, "futures");
      
      [...spotPairs, ...futuresPairs].forEach((pair) => {
        const market = spotPairs.includes(pair) ? "spot" : "futures";
        const currencyKey = `${exchange}_${market}_${pair}`;
        newSettings[currencyKey] = !allEnabled;
      });
    });
    
    onChartSettingsChange(newSettings);
  };

  // Функция для переключения одного графика
  const toggleChart = (currencyKey: string) => {
    onChartSettingsChange({
      ...chartSettings,
      [currencyKey]: !chartSettings[currencyKey],
    });
  };

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6">
      {/* Шапка карточки */}
      <div className="flex items-start justify-between mb-4">
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-2">
            <h2 className="text-xl font-bold text-white">Отправка графиков прострелов</h2>
            <svg className="w-5 h-5 text-zinc-400 cursor-help" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <title>Включите отправку тиковых графиков для выбранных торговых пар. Графики будут отправляться вместе с текстовыми детектами и показывать движение цены за 30 минут до момента детекта. Важно: включение отправки графика задержит приход сигнала в Telegram канал на 1-2 секунды.</title>
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
          <p className="text-sm text-zinc-400 mb-3">
            Включите отправку тиковых графиков для выбранных торговых пар. Графики будут отправляться вместе с текстовыми детектами и показывать движение цены за 30 минут до момента детекта.
          </p>
          <div className="bg-amber-500/10 border border-amber-500/30 rounded-lg p-3 flex items-start gap-2">
            <svg className="w-5 h-5 text-amber-400 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
            <p className="text-sm text-amber-300 font-medium">
              <span className="font-bold">Важно:</span> Включение отправки графика задержит приход сигнала в ваш Telegram канал на 1-2 секунды, так как система сначала генерирует график, а затем отправляет сообщение.
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2 ml-4">
          <button
            onClick={toggleAllCharts}
            className="px-4 py-2 bg-gradient-to-r from-blue-500 to-blue-600 hover:from-blue-600 hover:to-blue-700 text-white text-sm font-medium rounded-lg smooth-transition ripple hover-glow shadow-blue"
          >
            {areAllChartsEnabled() ? "Отключить все графики" : "Включить все графики"}
          </button>
        </div>
      </div>

      {/* Компактная таблица настроек */}
      <div className="overflow-x-auto w-full mb-4">
        <table className="border-collapse w-full">
          <thead>
            <tr className="border-b border-zinc-700">
              <th className="text-left py-2 px-4 text-sm font-semibold text-zinc-300">Биржа</th>
              <th className="text-left py-2 px-4 text-sm font-semibold text-zinc-300">Spot</th>
              <th className="text-left py-2 px-4 text-sm font-semibold text-zinc-300">Futures</th>
            </tr>
          </thead>
          <tbody>
            {["binance", "bybit", "bitget", "gate", "hyperliquid"].map((exchange) => {
              const exchangeDisplayName = exchange === "gate" ? "Gate" : exchange === "hyperliquid" ? "Hyperliquid" : exchange.charAt(0).toUpperCase() + exchange.slice(1);
              const spotCurrencies = getPairsForExchange(exchange, "spot");
              const futuresCurrencies = getPairsForExchange(exchange, "futures");
              
              return (
                <tr key={exchange} className="border-t border-zinc-800 hover:bg-zinc-800/50">
                  <td className="py-2.5 px-4 align-top">
                    <span className="text-sm font-medium text-white">{exchangeDisplayName}</span>
                  </td>
                  <td className="py-2.5 px-4 align-top">
                    {spotCurrencies.length > 0 ? (
                      <div className="flex flex-wrap gap-1.5">
                        {spotCurrencies.map((currency) => {
                          const currencyKey = `${exchange}_spot_${currency}`;
                          const isEnabled = chartSettings[currencyKey] === true;
                          return (
                            <button
                              key={currencyKey}
                              onClick={(e) => {
                                e.stopPropagation();
                                toggleChart(currencyKey);
                              }}
                              className={`inline-flex items-center justify-center h-6 px-2 text-xs font-medium rounded transition-all ${
                                isEnabled
                                  ? "bg-emerald-500/20 border border-emerald-500 text-emerald-300 hover:bg-emerald-500/30"
                                  : "bg-zinc-800 border border-zinc-700 text-zinc-400 hover:bg-zinc-700 hover:text-zinc-300"
                              }`}
                            >
                              {currency}
                            </button>
                          );
                        })}
                      </div>
                    ) : (
                      <span className="text-sm text-zinc-500">—</span>
                    )}
                  </td>
                  <td className="py-2.5 px-4 align-top">
                    {futuresCurrencies.length > 0 ? (
                      <div className="flex flex-wrap gap-1.5">
                        {futuresCurrencies.map((currency) => {
                          const currencyKey = `${exchange}_futures_${currency}`;
                          const isEnabled = chartSettings[currencyKey] === true;
                          return (
                            <button
                              key={currencyKey}
                              onClick={(e) => {
                                e.stopPropagation();
                                toggleChart(currencyKey);
                              }}
                              className={`inline-flex items-center justify-center h-6 px-2 text-xs font-medium rounded transition-all ${
                                isEnabled
                                  ? "bg-emerald-500/20 border border-emerald-500 text-emerald-300 hover:bg-emerald-500/30"
                                  : "bg-zinc-800 border border-zinc-700 text-zinc-400 hover:bg-zinc-700 hover:text-zinc-300"
                              }`}
                            >
                              {currency}
                            </button>
                          );
                        })}
                      </div>
                    ) : (
                      <span className="text-sm text-zinc-500">—</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      
      {/* Кнопка сохранения */}
      <button
        onClick={async () => {
          await onSave();
        }}
        disabled={saving}
        className="w-full px-4 py-2 bg-gradient-to-r from-emerald-500 to-emerald-600 hover:from-emerald-600 hover:to-emerald-700 text-white font-medium rounded-lg smooth-transition ripple hover-glow shadow-emerald disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {saving ? "Сохранение..." : "Сохранить настройки графиков"}
      </button>
    </div>
  );
}

