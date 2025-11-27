"use client";

import { useState, useEffect, useCallback } from "react";

const formatNumber = (num: number) => {
  return new Intl.NumberFormat("ru-RU").format(num);
};

// Извлечение пары из символа (например, BTCUSDT -> USDT, ZECUSDC/USDC -> USDC)
const extractQuoteCurrency = (symbol: string): string => {
  if (!symbol) return "";
  
  const symbolUpper = symbol.toUpperCase();
  
  // Список известных котируемых валют (по длине, от самой длинной к короткой)
  const quoteCurrencies = [
    "USDC", "USDT", "FDUSD", "BIDR", "AEUR",
    "BTC", "ETH", "BNB", "TUSD", "DOGE", "TRX",
    "TRY", "EUR", "GBP", "AUD", "BRL"
  ];
  
  // Сначала проверяем разделители (приоритет для символов с разделителями)
  const separators = ["/", "_", "-"];
  for (const sep of separators) {
    if (symbolUpper.includes(sep)) {
      const parts = symbolUpper.split(sep);
      if (parts.length >= 2) {
        const lastPart = parts[parts.length - 1];
        // Проверяем, является ли последняя часть котируемой валютой
        if (quoteCurrencies.includes(lastPart)) {
          return lastPart;
        }
      }
    }
  }
  
  // Если разделителей нет, ищем самую длинную котируемую валюту в конце символа
  // Сортируем по длине (от самой длинной к короткой) для правильного определения
  const sortedQuotes = [...quoteCurrencies].sort((a, b) => b.length - a.length);
  for (const quote of sortedQuotes) {
    if (symbolUpper.endsWith(quote)) {
      return quote;
    }
  }
  
  return "";
};

// Извлечение базовой валюты из символа (например, BTCUSDT -> BTC, ETH_USDT -> ETH)
const extractBaseCurrency = (symbol: string): string => {
  if (!symbol) return "";
  
  const symbolUpper = symbol.toUpperCase();
  
  // Список известных котируемых валют (по длине, от самой длинной к короткой)
  const quoteCurrencies = [
    "USDC", "USDT", "FDUSD", "BIDR", "AEUR",
    "BTC", "ETH", "BNB", "TUSD", "DOGE", "TRX",
    "TRY", "EUR", "GBP", "AUD", "BRL"
  ];
  
  // Сначала проверяем разделители (приоритет для символов с разделителями)
  const separators = ["/", "_", "-"];
  for (const sep of separators) {
    if (symbolUpper.includes(sep)) {
      const parts = symbolUpper.split(sep);
      if (parts.length >= 2) {
        const firstPart = parts[0];
        const lastPart = parts[parts.length - 1];
        // Проверяем, является ли последняя часть котируемой валютой
        if (quoteCurrencies.includes(lastPart) && firstPart) {
          return firstPart;
        }
      }
    }
  }
  
  // Если разделителей нет, ищем самую длинную котируемую валюту в конце символа
  // Сортируем по длине (от самой длинной к короткой) для правильного определения
  const sortedQuotes = [...quoteCurrencies].sort((a, b) => b.length - a.length);
  for (const quote of sortedQuotes) {
    if (symbolUpper.endsWith(quote)) {
      const base = symbolUpper.slice(0, -quote.length);
      if (base && base.length >= 2) {
        return base;
      }
    }
  }
  
  // Если не удалось извлечь, проверяем, не является ли весь символ базовой валютой
  // (для случаев типа BTC, ETH без пары)
  if (symbolUpper.length <= 10 && !quoteCurrencies.includes(symbolUpper)) {
    return symbolUpper;
  }
  
  return "";
};

// Форматирование символа в формат "BASE/QUOTE" (например, PORT3USDT -> PORT3/USDT)
const formatSymbol = (symbol: string): string => {
  if (!symbol) return "";
  
  const baseCurrency = extractBaseCurrency(symbol);
  const quoteCurrency = extractQuoteCurrency(symbol);
  
  if (baseCurrency && quoteCurrency) {
    return `${baseCurrency}/${quoteCurrency}`;
  } else if (baseCurrency) {
    return baseCurrency;
  }
  
  return symbol;
};

// Форматирование объема в кратком виде (тысячи, миллионы)
const formatVolumeCompact = (volume: number): string => {
  if (volume >= 1000000) {
    const millions = volume / 1000000;
    if (millions >= 100) {
      return `${millions.toFixed(0)}M`;
    }
    return `${millions.toFixed(1)}M`;
  } else if (volume >= 1000) {
    const thousands = volume / 1000;
    if (thousands >= 100) {
      return `${thousands.toFixed(0)}K`;
    }
    return `${thousands.toFixed(1)}K`;
  }
  return `${volume.toFixed(0)}`;
};

type SpikesStats = {
  total_count: number;
  avg_delta: number;
  avg_volume: number;
  total_volume: number;
  chart_data: Array<{ date: string; count: number }>;
  by_exchange: Record<string, number>;
  by_market: Record<string, number>;
  top_symbols: Array<{ symbol: string; count: number }>;
  top_by_delta: Array<any>;
  top_by_volume: Array<any>;
  spikes: Array<any>;
  binance_spot_settings?: {
    delta: string;
    volume: string;
    shadow: string;
  };
};

interface StatisticsTabProps {
  userLogin: string;
}

export default function StatisticsTab({ userLogin }: StatisticsTabProps) {
  const [spikesStats, setSpikesStats] = useState<SpikesStats | null>(null);
  const [spikesStatsLoading, setSpikesStatsLoading] = useState(false);
  const [statisticsMode, setStatisticsMode] = useState<"personal" | "global">("personal");
  const [statisticsPeriod, setStatisticsPeriod] = useState<number>(30);
  const [deletingSpikes, setDeletingSpikes] = useState(false);
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);
  const [symbolSpikes, setSymbolSpikes] = useState<any[]>([]);
  const [symbolSpikesLoading, setSymbolSpikesLoading] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [lastUpdateTime, setLastUpdateTime] = useState<Date | null>(null);
  const [searchDelta, setSearchDelta] = useState<string>("");
  const [searchVolume, setSearchVolume] = useState<string>("");
  
  // Функция фильтрации сигналов по базовой валюте
  const filterSpikesByBaseCurrency = useCallback((spikes: any[], searchQuery: string): any[] => {
    if (!searchQuery.trim()) {
      return spikes;
    }
    
    const searchUpper = searchQuery.trim().toUpperCase();
    const filtered = spikes.filter((spike) => {
      const baseCurrency = extractBaseCurrency(spike.symbol);
      return baseCurrency === searchUpper || spike.symbol.toUpperCase().includes(searchUpper);
    });
    
    // Возвращаем топ 10 (уже отсортированы по дельте/объёму)
    return filtered.slice(0, 10);
  }, []);

  // Функция загрузки статистики
  const fetchSpikesStats = useCallback(async (showLoading = true) => {
    if (showLoading) {
      setSpikesStatsLoading(true);
    }
    setIsRefreshing(true);
    try {
      let url: string;
      if (statisticsMode === "personal") {
        url = `/api/users/${encodeURIComponent(userLogin)}/spikes/stats?days=${statisticsPeriod}`;
      } else {
        url = `/api/users/Stats/spikes/stats?days=${statisticsPeriod}`;
      }
      
      const res = await fetch(url);
      if (res.ok) {
        const data = await res.json();
        setSpikesStats(data);
        setLastUpdateTime(new Date());
      } else {
        console.error("Ошибка загрузки статистики стрел:", res.status);
        setSpikesStats(null);
      }
    } catch (error) {
      console.error("Ошибка загрузки статистики стрел:", error);
      setSpikesStats(null);
    } finally {
      if (showLoading) {
        setSpikesStatsLoading(false);
      }
      setIsRefreshing(false);
    }
  }, [statisticsMode, statisticsPeriod, userLogin]);

  // Загрузка статистики
  useEffect(() => {
    // Загружаем данные сразу
    fetchSpikesStats(true);
    
    // Автоматическое обновление каждые 15 секунд (без показа индикатора загрузки)
    const interval = setInterval(() => {
      fetchSpikesStats(false);
    }, 15000);
    
    // Очищаем интервал при размонтировании или изменении зависимостей
    return () => {
      clearInterval(interval);
    };
  }, [fetchSpikesStats]);

  // Функция загрузки деталей по монете
  const fetchSymbolSpikes = useCallback(async () => {
    if (selectedSymbol) {
      setSymbolSpikesLoading(true);
      try {
        let url: string;
        if (statisticsMode === "personal") {
          url = `/api/users/${encodeURIComponent(userLogin)}/spikes/by-symbol/${encodeURIComponent(selectedSymbol)}`;
        } else {
          url = `/api/users/Stats/spikes/by-symbol/${encodeURIComponent(selectedSymbol)}`;
        }
        
        const res = await fetch(url);
        if (res.ok) {
          const data = await res.json();
          console.log("Данные по монете:", data); // Для отладки
          // Проверяем структуру ответа - API возвращает {symbol, total_count, spikes}
          const spikes = data.spikes || [];
          if (Array.isArray(spikes) && spikes.length > 0) {
            // Данные уже отсортированы по времени (новые первыми) в API
            // Берем последние 10 сигналов
            const lastSpikes = spikes.slice(0, 10);
            setSymbolSpikes(lastSpikes);
          } else {
            console.log("Нет данных в ответе API. spikes:", spikes, "data:", data);
            setSymbolSpikes([]);
          }
        } else {
          const errorText = await res.text().catch(() => "");
          let errorData;
          try {
            errorData = JSON.parse(errorText);
          } catch {
            errorData = { detail: errorText || "Неизвестная ошибка" };
          }
          console.error("Ошибка загрузки деталей по монете:", res.status, errorData);
          setSymbolSpikes([]);
        }
      } catch (error) {
        console.error("Ошибка загрузки деталей по монете:", error);
        setSymbolSpikes([]);
      } finally {
        setSymbolSpikesLoading(false);
      }
    }
  }, [selectedSymbol, statisticsMode, userLogin]);

  // Загрузка деталей по монете
  useEffect(() => {
    // Загружаем данные сразу, если выбрана монета
    fetchSymbolSpikes();
    
    // Автоматическое обновление каждые 15 секунд, если выбрана монета
    if (selectedSymbol) {
      const interval = setInterval(fetchSymbolSpikes, 15000);
      
      // Очищаем интервал при размонтировании или изменении зависимостей
      return () => {
        clearInterval(interval);
      };
    }
  }, [fetchSymbolSpikes, selectedSymbol]);

  // Функция для очистки статистики стрел пользователя
  const handleDeleteSpikes = async () => {
    if (!userLogin) return;
    
    const confirmed = window.confirm(
      "Вы уверены, что хотите очистить всю вашу статистику стрел? Это действие нельзя отменить."
    );
    
    if (!confirmed) return;
    
    setDeletingSpikes(true);
    try {
      const res = await fetch(`/api/users/${encodeURIComponent(userLogin)}/spikes`, {
        method: "DELETE",
      });
      
      if (res.ok) {
        const data = await res.json();
        alert(`Статистика успешно очищена. Удалено записей: ${data.deleted_count || 0}`);
        setSpikesStats(null);
        try {
          const statsRes = await fetch(`/api/users/${encodeURIComponent(userLogin)}/spikes/stats?days=${statisticsPeriod}`);
          if (statsRes.ok) {
            const statsData = await statsRes.json();
            setSpikesStats(statsData);
          }
        } catch (statsError) {
          console.error("Ошибка при обновлении статистики после удаления:", statsError);
        }
      } else {
        const error = await res.json();
        alert(`Ошибка очистки статистики: ${error.detail || "Неизвестная ошибка"}`);
      }
    } catch (error) {
      console.error("Ошибка очистки статистики:", error);
      alert("Ошибка при очистке статистики");
    } finally {
      setDeletingSpikes(false);
    }
  };

  return (
    <div className="mb-6 md:mb-8 animate-fade-in">
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 mb-4">
        <div>
          <div className="flex items-center gap-3 mb-2">
            <h1 className="text-2xl md:text-3xl font-bold gradient-text">Статистика стрел</h1>
            {/* Индикатор обновления */}
            {isRefreshing && (
              <div className="w-5 h-5 border-2 border-emerald-500 border-t-transparent rounded-full animate-spin"></div>
            )}
            {/* Кнопка ручного обновления */}
            <button
              onClick={() => fetchSpikesStats(true)}
              disabled={isRefreshing || spikesStatsLoading}
              className="p-2 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-400 hover:text-white transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              title="Обновить данные"
            >
              <svg 
                className={`w-5 h-5 ${isRefreshing ? 'animate-spin' : ''}`} 
                fill="none" 
                stroke="currentColor" 
                viewBox="0 0 24 24"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
            </button>
          </div>
          <p className="text-zinc-400">
            {statisticsMode === "personal" 
              ? `Статистика по вашим детектам за последние ${statisticsPeriod} дней (с учетом ваших фильтров)`
              : (() => {
                  const settings = spikesStats?.binance_spot_settings;
                  if (settings) {
                    const delta = settings.delta ? `${settings.delta}%` : "";
                    let volume = "";
                    if (settings.volume) {
                      const volumeNum = parseFloat(settings.volume);
                      if (!isNaN(volumeNum)) {
                        if (volumeNum >= 1000) {
                          volume = `${(volumeNum / 1000).toFixed(0)}k$`;
                        } else {
                          volume = `${volumeNum}$`;
                        }
                      } else {
                        volume = `${settings.volume}$`;
                      }
                    }
                    const shadow = settings.shadow ? `${settings.shadow}%` : "";
                    const parts = [delta, volume, shadow].filter(Boolean);
                    const settingsText = parts.length > 0 ? ` (${parts.join(" ")})` : "";
                    return `Рыночная статистика по детектам за последние ${statisticsPeriod} дней (с учетом настроек пользователя Stats${settingsText})`;
                  }
                  return `Рыночная статистика по детектам за последние ${statisticsPeriod} дней (с учетом настроек пользователя Stats)`;
                })()}
          </p>
          {lastUpdateTime && (
            <p className="text-zinc-500 text-sm mt-1">
              Последнее обновление: {lastUpdateTime.toLocaleTimeString('ru-RU')}
            </p>
          )}
        </div>
        <div className="flex items-center gap-3">
          {/* Селектор периода */}
          <select
            value={statisticsPeriod}
            onChange={(e) => setStatisticsPeriod(Number(e.target.value))}
            className="bg-zinc-900 border border-zinc-800 rounded-lg px-4 py-2 text-sm text-white focus:outline-none focus:ring-2 focus:ring-emerald-500"
          >
            <option value={7}>7 дней</option>
            <option value={14}>14 дней</option>
            <option value={30}>30 дней</option>
            <option value={60}>60 дней</option>
            <option value={90}>90 дней</option>
            <option value={180}>180 дней</option>
            <option value={365}>365 дней</option>
          </select>
          {/* Переключатель между личной и общей статистикой */}
          <div className="flex items-center gap-2 bg-zinc-900 border border-zinc-800 rounded-lg p-1">
            <button
              onClick={() => setStatisticsMode("personal")}
              className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                statisticsMode === "personal"
                  ? "bg-emerald-500 text-white shadow-emerald"
                  : "text-zinc-400 hover:text-white hover:bg-zinc-800"
              }`}
            >
              Моя статистика
            </button>
            <button
              onClick={() => setStatisticsMode("global")}
              className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                statisticsMode === "global"
                  ? "bg-emerald-500 text-white shadow-emerald"
                  : "text-zinc-400 hover:text-white hover:bg-zinc-800"
              }`}
            >
              Рыночная статистика
            </button>
          </div>
          {/* Кнопка очистки статистики (только для личной статистики) */}
          {statisticsMode === "personal" && (
            <button
              onClick={handleDeleteSpikes}
              disabled={deletingSpikes}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                deletingSpikes
                  ? "bg-zinc-700 text-zinc-400 cursor-not-allowed"
                  : "bg-red-600 hover:bg-red-700 text-white"
              }`}
              title="Очистить всю мою статистику стрел"
            >
              {deletingSpikes ? (
                <span className="flex items-center gap-2">
                  <span className="w-4 h-4 border-2 border-zinc-400 border-t-transparent rounded-full animate-spin"></span>
                  Очищение...
                </span>
              ) : (
                "🗑️ Очистить мою статистику"
              )}
            </button>
          )}
        </div>
      </div>
      
      {spikesStatsLoading ? (
        <div className="flex items-center justify-center py-12">
          <div className="flex flex-col items-center gap-4">
            <div className="w-12 h-12 border-4 border-emerald-500 border-t-transparent rounded-full animate-spin"></div>
            <div className="text-white text-xl animate-pulse-slow">Загрузка статистики...</div>
          </div>
        </div>
      ) : spikesStats ? (
        <>
          {/* Карточки со сводной статистикой */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
            <div className="glass-strong border border-zinc-800 rounded-xl p-6 card-hover gradient-border float-animation shadow-emerald animate-scale-in">
              <div className="text-zinc-400 text-sm mb-1">Всего детектов</div>
              <div className="text-3xl font-bold text-white">{formatNumber(spikesStats.total_count)}</div>
            </div>
            <div className="glass-strong border border-zinc-800 rounded-xl p-6 card-hover gradient-border float-animation shadow-blue animate-scale-in" style={{ animationDelay: '0.1s' }}>
              <div className="text-zinc-400 text-sm mb-1">Средняя дельта</div>
              <div className="text-3xl font-bold text-white">{spikesStats.avg_delta.toFixed(2)}%</div>
            </div>
            <div className="glass-strong border border-zinc-800 rounded-xl p-6 card-hover gradient-border float-animation shadow-purple animate-scale-in" style={{ animationDelay: '0.2s' }}>
              <div className="text-zinc-400 text-sm mb-1">Средний объём</div>
              <div className="text-3xl font-bold text-white">${formatNumber(Math.round(spikesStats.avg_volume))}</div>
            </div>
          </div>
          
          {/* График детектов по дням (линейный) */}
          {spikesStats.chart_data.length > 0 && (() => {
            const maxCount = Math.max(...spikesStats.chart_data.map(d => d.count), 1);
            const dataPoints = spikesStats.chart_data.length;
            const paddingLeft = 70;
            const paddingRight = 30;
            const paddingTop = 30;
            const paddingBottom = 60;
            const chartHeight = 350;
            
            const yAxisSteps = 5;
            const yStep = Math.ceil(maxCount / yAxisSteps);
            const yAxisMax = yStep * yAxisSteps;
            const yAxisValues = Array.from({ length: yAxisSteps + 1 }, (_, i) => i * yStep);
            
            return (
              <div className="glass-strong border border-zinc-800 rounded-xl p-6 mb-8 card-hover animate-fade-in">
                <h2 className="text-xl font-semibold gradient-text mb-6">Детекты по дням</h2>
                <div className="relative w-full" style={{ minHeight: '450px' }}>
                  <svg className="w-full" style={{ height: `${chartHeight + paddingTop + paddingBottom}px` }} viewBox={`0 0 1000 ${chartHeight + paddingTop + paddingBottom}`} preserveAspectRatio="none">
                    <defs>
                      <linearGradient id="lineGradient" x1="0%" y1="0%" x2="0%" y2="100%">
                        <stop offset="0%" stopColor="#10b981" stopOpacity="0.3" />
                        <stop offset="100%" stopColor="#10b981" stopOpacity="0" />
                      </linearGradient>
                    </defs>
                    
                    {(() => {
                      const chartWidth = 1000 - paddingLeft - paddingRight;
                      const stepX = dataPoints > 1 ? chartWidth / (dataPoints - 1) : 0;
                      
                      return (
                        <>
                          <line
                            x1={paddingLeft}
                            y1={paddingTop}
                            x2={paddingLeft}
                            y2={chartHeight + paddingTop}
                            stroke="#4b5563"
                            strokeWidth="2"
                          />
                          
                          <line
                            x1={paddingLeft}
                            y1={chartHeight + paddingTop}
                            x2={1000 - paddingRight}
                            y2={chartHeight + paddingTop}
                            stroke="#4b5563"
                            strokeWidth="2"
                          />
                          
                          {yAxisValues.map((value, idx) => {
                            const y = chartHeight + paddingTop - (value / yAxisMax) * chartHeight;
                            return (
                              <g key={idx}>
                                <line
                                  x1={paddingLeft - 6}
                                  y1={y}
                                  x2={paddingLeft}
                                  y2={y}
                                  stroke="#6b7280"
                                  strokeWidth="1.5"
                                />
                                <text
                                  x={paddingLeft - 15}
                                  y={y + 5}
                                  textAnchor="end"
                                  fill="#9ca3af"
                                  fontSize="12"
                                  fontFamily="system-ui, -apple-system, sans-serif"
                                  fontWeight="500"
                                >
                                  {value}
                                </text>
                              </g>
                            );
                          })}
                          
                          <path
                            d={`M ${paddingLeft},${chartHeight + paddingTop} ${spikesStats.chart_data.map((item, idx) => {
                              const y = chartHeight + paddingTop - (item.count / yAxisMax) * chartHeight;
                              const x = paddingLeft + idx * stepX;
                              return `L ${x},${y}`;
                            }).join(' ')} L ${paddingLeft + (dataPoints - 1) * stepX},${chartHeight + paddingTop} Z`}
                            fill="url(#lineGradient)"
                          />
                          
                          <polyline
                            points={spikesStats.chart_data.map((item, idx) => {
                              const y = chartHeight + paddingTop - (item.count / yAxisMax) * chartHeight;
                              const x = paddingLeft + idx * stepX;
                              return `${x},${y}`;
                            }).join(' ')}
                            fill="none"
                            stroke="#10b981"
                            strokeWidth="2.5"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                          />
                          
                          {spikesStats.chart_data.map((item, idx) => {
                            const y = chartHeight + paddingTop - (item.count / yAxisMax) * chartHeight;
                            const x = paddingLeft + idx * stepX;
                            return (
                              <circle
                                key={idx}
                                cx={x}
                                cy={y}
                                r="3"
                                fill="#10b981"
                                stroke="#0f172a"
                                strokeWidth="1.5"
                                className="hover:r-4 transition-all cursor-pointer"
                              />
                            );
                          })}
                          
                          {spikesStats.chart_data.map((item, idx) => {
                            const x = paddingLeft + idx * stepX;
                            return (
                              <line
                                key={idx}
                                x1={x}
                                y1={chartHeight + paddingTop}
                                x2={x}
                                y2={chartHeight + paddingTop + 6}
                                stroke="#6b7280"
                                strokeWidth="1.5"
                              />
                            );
                          })}
                        </>
                      );
                    })()}
                  </svg>
                  
                  <div className="absolute bottom-0 left-0 right-0" style={{ height: `${paddingBottom}px` }}>
                    {spikesStats.chart_data.map((item, idx) => {
                      const chartWidth = 1000 - paddingLeft - paddingRight;
                      const stepX = dataPoints > 1 ? chartWidth / (dataPoints - 1) : 0;
                      const xPosition = paddingLeft + idx * stepX;
                      const leftPercent = (xPosition / 1000) * 100;
                      return (
                        <div
                          key={idx}
                          className="text-zinc-400 text-xs text-center absolute"
                          style={{
                            left: `${leftPercent}%`,
                            transform: 'translateX(-50%)',
                            whiteSpace: 'nowrap',
                            bottom: '15px',
                            fontSize: '11px'
                          }}
                        >
                          {new Date(item.date).toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' })}
                        </div>
                      );
                    })}
                  </div>
                  
                  <div 
                    className="absolute text-zinc-400 text-xs font-medium whitespace-nowrap" 
                    style={{ 
                      left: `${paddingLeft / 2}px`,
                      top: '50%',
                      transform: 'translate(-50%, -50%) rotate(-90deg)',
                      transformOrigin: 'center center',
                      fontSize: '12px'
                    }}
                  >
                    Количество детектов
                  </div>
                  
                  <div className="absolute bottom-0 left-1/2 transform translate-x-1/2 translate-y-full text-zinc-400 text-xs font-medium" style={{ marginBottom: '10px', fontSize: '12px' }}>
                    Дата
                  </div>
                </div>
              </div>
            );
          })()}
          
          {/* Распределение по биржам и рынкам */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-8">
            <div className="glass-strong border border-zinc-800 rounded-xl p-6 card-hover gradient-border animate-fade-in">
              <h2 className="text-xl font-semibold gradient-text mb-4">По биржам</h2>
              <div className="space-y-2">
                {Object.entries(spikesStats.by_exchange).map(([exchange, count]) => (
                  <div key={exchange} className="flex items-center justify-between smooth-transition hover:bg-zinc-800/30 p-2 rounded">
                    <span className="text-zinc-300 capitalize">{exchange}</span>
                    <span className="text-white font-semibold">{formatNumber(count as number)}</span>
                  </div>
                ))}
              </div>
            </div>
            <div className="glass-strong border border-zinc-800 rounded-xl p-6 card-hover gradient-border animate-fade-in">
              <h2 className="text-xl font-semibold gradient-text mb-4">По рынкам</h2>
              <div className="space-y-2">
                {Object.entries(spikesStats.by_market).map(([market, count]) => (
                  <div key={market} className="flex items-center justify-between smooth-transition hover:bg-zinc-800/30 p-2 rounded">
                    <span className="text-zinc-300 capitalize">{market === 'linear' ? 'Фьючерсы' : market === 'spot' ? 'Спот' : market}</span>
                    <span className="text-white font-semibold">{formatNumber(count as number)}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
          
          {/* Топ символов */}
          {spikesStats.top_symbols.length > 0 && (
            <div className="glass-strong border border-zinc-800 rounded-xl p-6 mb-8 card-hover animate-fade-in">
              <h2 className="text-xl font-semibold gradient-text mb-4">Топ-10 символов</h2>
              <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
                {spikesStats.top_symbols.map((item) => (
                  <button
                    key={item.symbol}
                    onClick={() => setSelectedSymbol(item.symbol)}
                    className="text-center p-3 rounded-lg glass hover:bg-zinc-800/50 smooth-transition ripple hover-glow border border-transparent hover:border-emerald-500"
                  >
                    <div className="text-zinc-400 text-sm mb-1">{item.symbol}</div>
                    <div className="text-white font-bold">{formatNumber(item.count)}</div>
                  </button>
                ))}
              </div>
            </div>
          )}
          
          {/* Детали по выбранной монете */}
          {selectedSymbol && (
            <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6 mb-8">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-xl font-semibold text-white">
                  Последние 10 сигналов по монете {selectedSymbol}
                </h2>
                <button
                  onClick={() => setSelectedSymbol(null)}
                  className="text-zinc-400 hover:text-white transition-colors"
                >
                  ✕
                </button>
              </div>
              
              {symbolSpikesLoading ? (
                <div className="text-zinc-400 text-center py-8">Загрузка...</div>
              ) : symbolSpikes.length > 0 ? (
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead className="bg-zinc-800/50">
                      <tr>
                        <th className="px-4 py-2 text-left text-xs font-semibold text-zinc-300">Время</th>
                        <th className="px-4 py-2 text-left text-xs font-semibold text-zinc-300">Дельта %</th>
                        <th className="px-4 py-2 text-left text-xs font-semibold text-zinc-300">Объём USDT</th>
                        <th className="px-4 py-2 text-left text-xs font-semibold text-zinc-300">Тень %</th>
                        <th className="px-4 py-2 text-left text-xs font-semibold text-zinc-300">Торговая пара</th>
                        <th className="px-4 py-2 text-left text-xs font-semibold text-zinc-300">Биржа</th>
                        <th className="px-4 py-2 text-left text-xs font-semibold text-zinc-300">Рынок</th>
                      </tr>
                    </thead>
                    <tbody>
                      {symbolSpikes.map((spike: any, idx: number) => {
                        const quoteCurrency = extractQuoteCurrency(spike.symbol);
                        return (
                          <tr key={idx} className="border-t border-zinc-800 hover:bg-zinc-800/30 transition-colors">
                            <td className="px-4 py-3 text-zinc-300 text-sm">
                              {new Date(spike.ts).toLocaleString('ru-RU', {
                                year: 'numeric',
                                month: '2-digit',
                                day: '2-digit',
                                hour: '2-digit',
                                minute: '2-digit',
                                second: '2-digit'
                              })}
                            </td>
                            <td className={`px-4 py-3 font-semibold ${spike.delta >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                              {spike.delta >= 0 ? '+' : ''}{spike.delta.toFixed(2)}%
                            </td>
                            <td className="px-4 py-3 text-zinc-300">${formatNumber(Math.round(spike.volume_usdt))}</td>
                            <td className="px-4 py-3 text-zinc-300">{spike.wick_pct.toFixed(1)}%</td>
                            <td className="px-4 py-3 text-white font-medium">
                              {quoteCurrency || '-'}
                            </td>
                            <td className="px-4 py-3 text-zinc-300 capitalize">{spike.exchange}</td>
                            <td className="px-4 py-3 text-zinc-300 capitalize">
                              {spike.market === 'linear' ? 'Фьючерсы' : spike.market}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="text-zinc-400 text-center py-8">Нет данных по этой монете</div>
              )}
            </div>
          )}
          
          {/* Топ 10 стрел по дельте и объёму */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-8">
            {/* Топ 10 по дельте */}
            <div className="glass-strong border border-zinc-800 rounded-xl p-4 card-hover animate-fade-in">
              <div className="flex items-center justify-between mb-3">
                <h2 className="text-lg font-semibold gradient-text">Топ 10 стрел по дельте</h2>
                <div className="relative">
                  <input
                    type="text"
                    placeholder="Поиск монеты..."
                    value={searchDelta}
                    onChange={(e) => setSearchDelta(e.target.value)}
                    className="bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-1.5 text-sm text-white placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent w-32"
                  />
                  {searchDelta && (
                    <button
                      onClick={() => setSearchDelta("")}
                      className="absolute right-2 top-1/2 -translate-y-1/2 text-zinc-500 hover:text-white transition-colors"
                      title="Очистить"
                    >
                      ✕
                    </button>
                  )}
                </div>
              </div>
              {spikesStats.top_by_delta && spikesStats.top_by_delta.length > 0 ? (() => {
                const filteredSpikes = filterSpikesByBaseCurrency(spikesStats.top_by_delta, searchDelta);
                return filteredSpikes.length > 0 ? (
                  <div className="grid grid-cols-2 gap-2">
                    {filteredSpikes.map((spike: any, idx: number) => {
                    const volumeCompact = formatVolumeCompact(spike.volume_usdt || 0);
                    const formattedSymbol = formatSymbol(spike.symbol);
                    return (
                      <div key={idx} className="p-2 rounded-lg glass hover:bg-zinc-800/50 smooth-transition">
                        <div className="flex items-center justify-between mb-1">
                          <div className="text-zinc-400 text-xs font-medium">#{idx + 1}</div>
                          <div className={`font-semibold text-xs ${spike.delta >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                            {spike.delta >= 0 ? '+' : ''}{spike.delta.toFixed(2)}%
                          </div>
                        </div>
                        <div className="text-white font-medium text-sm mb-0.5 truncate">
                          {formattedSymbol}
                        </div>
                        <div className="text-zinc-400 text-xs truncate mb-0.5">
                          {spike.exchange} • {spike.market === 'linear' ? 'Фьючерсы' : 'Спот'}
                          {volumeCompact && <span className="ml-1">• ${volumeCompact}</span>}
                        </div>
                        <div className="text-zinc-500 text-xs">
                          {new Date(spike.ts).toLocaleString('ru-RU', { 
                            day: '2-digit', 
                            month: '2-digit',
                            hour: '2-digit',
                            minute: '2-digit'
                          })}
                        </div>
                      </div>
                    );
                  })}
                  </div>
                ) : (
                  <div className="text-zinc-500 text-center py-8 text-sm">
                    {searchDelta ? "Монета не найдена" : "Нет данных за выбранный период"}
                  </div>
                );
              })() : (
                <div className="text-zinc-500 text-center py-8 text-sm">Нет данных за выбранный период</div>
              )}
            </div>
            
            {/* Топ 10 по объёму */}
            <div className="glass-strong border border-zinc-800 rounded-xl p-4 card-hover animate-fade-in">
              <div className="flex items-center justify-between mb-3">
                <h2 className="text-lg font-semibold gradient-text">Топ 10 стрел по объёму</h2>
                <div className="relative">
                  <input
                    type="text"
                    placeholder="Поиск монеты..."
                    value={searchVolume}
                    onChange={(e) => setSearchVolume(e.target.value)}
                    className="bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-1.5 text-sm text-white placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent w-32"
                  />
                  {searchVolume && (
                    <button
                      onClick={() => setSearchVolume("")}
                      className="absolute right-2 top-1/2 -translate-y-1/2 text-zinc-500 hover:text-white transition-colors"
                      title="Очистить"
                    >
                      ✕
                    </button>
                  )}
                </div>
              </div>
              {spikesStats.top_by_volume && spikesStats.top_by_volume.length > 0 ? (() => {
                const filteredSpikes = filterSpikesByBaseCurrency(spikesStats.top_by_volume, searchVolume);
                return filteredSpikes.length > 0 ? (
                  <div className="grid grid-cols-2 gap-2">
                    {filteredSpikes.map((spike: any, idx: number) => {
                    const formattedSymbol = formatSymbol(spike.symbol);
                    return (
                      <div key={idx} className="p-2 rounded-lg glass hover:bg-zinc-800/50 smooth-transition">
                        <div className="flex items-center justify-between mb-1">
                          <div className="text-zinc-400 text-xs font-medium">#{idx + 1}</div>
                          <div className="text-green-400 font-semibold text-xs">
                            ${formatNumber(Math.round(spike.volume_usdt))}
                          </div>
                        </div>
                        <div className="text-white font-medium text-sm mb-0.5 truncate">
                          {formattedSymbol}
                        </div>
                        <div className="text-zinc-400 text-xs truncate mb-0.5">
                          {spike.exchange} • {spike.market === 'linear' ? 'Фьючерсы' : 'Спот'}
                          {spike.delta !== undefined && (
                            <span className="ml-1 font-semibold text-zinc-400">
                              • {spike.delta >= 0 ? '+' : ''}{spike.delta.toFixed(2)}%
                            </span>
                          )}
                        </div>
                        <div className="text-zinc-500 text-xs">
                          {new Date(spike.ts).toLocaleString('ru-RU', { 
                            day: '2-digit', 
                            month: '2-digit',
                            hour: '2-digit',
                            minute: '2-digit'
                          })}
                        </div>
                      </div>
                    );
                  })}
                  </div>
                ) : (
                  <div className="text-zinc-500 text-center py-8 text-sm">
                    {searchVolume ? "Монета не найдена" : "Нет данных за выбранный период"}
                  </div>
                );
              })() : (
                <div className="text-zinc-500 text-center py-8 text-sm">Нет данных за выбранный период</div>
              )}
            </div>
          </div>
          
          {/* Таблица детектов */}
          {spikesStats.spikes.length > 0 && (
            <div className="bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden">
              <div className="p-6 border-b border-zinc-800">
                <h2 className="text-xl font-semibold text-white">Последние детекты</h2>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead className="bg-zinc-800/50">
                    <tr>
                      <th className="px-6 py-3 text-left text-xs font-semibold text-zinc-300">Время</th>
                      <th className="px-6 py-3 text-left text-xs font-semibold text-zinc-300">Биржа</th>
                      <th className="px-6 py-3 text-left text-xs font-semibold text-zinc-300">Рынок</th>
                      <th className="px-6 py-3 text-left text-xs font-semibold text-zinc-300">Символ</th>
                      <th className="px-6 py-3 text-left text-xs font-semibold text-zinc-300">Дельта %</th>
                      <th className="px-6 py-3 text-left text-xs font-semibold text-zinc-300">Объём USDT</th>
                      <th className="px-6 py-3 text-left text-xs font-semibold text-zinc-300">Тень %</th>
                    </tr>
                  </thead>
                  <tbody>
                    {spikesStats.spikes.map((spike: any, idx: number) => {
                      const formattedSymbol = formatSymbol(spike.symbol);
                      return (
                        <tr key={idx} className="border-t border-zinc-800 hover:bg-zinc-800/30 transition-colors">
                          <td className="px-6 py-4 text-zinc-300 text-sm">
                            {new Date(spike.ts).toLocaleString('ru-RU')}
                          </td>
                          <td className="px-6 py-4 text-zinc-300 capitalize">{spike.exchange}</td>
                          <td className="px-6 py-4 text-zinc-300 capitalize">{spike.market === 'linear' ? 'Фьючерсы' : spike.market}</td>
                          <td className="px-6 py-4 text-white font-medium">
                            {formattedSymbol}
                          </td>
                          <td className={`px-6 py-4 font-semibold ${spike.delta >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                            {spike.delta >= 0 ? '+' : ''}{spike.delta.toFixed(2)}%
                          </td>
                          <td className="px-6 py-4 text-zinc-300">${formatNumber(Math.round(spike.volume_usdt))}</td>
                          <td className="px-6 py-4 text-zinc-300">{spike.wick_pct.toFixed(1)}%</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      ) : (
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6">
          <p className="text-zinc-400">Нет данных для отображения. Убедитесь, что у вас настроены фильтры детектирования.</p>
        </div>
      )}
    </div>
  );
}

