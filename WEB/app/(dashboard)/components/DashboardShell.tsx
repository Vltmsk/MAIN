"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import MonitoringTab from "./MonitoringTab";
import StatisticsTab from "./StatisticsTab";
import SettingsTab from "./SettingsTab";
import AdminTab from "./AdminTab";

type Exchange = {
  name: string;
  market: "spot" | "linear";
  status: "active" | "inactive" | "problems";
  websocketInfo: string; // Например: "2 WS, 4 batches" или "5 WS"
  candles: number;
  lastUpdate: string;
  lastUpdateTimestamp?: number; // Timestamp последнего обновления в миллисекундах
  wsConnections: number;
  reconnects: number;
  tradingPairs: number; // торговые пары (active_symbols)
  tps: number; // T/s - тики в секунду (ticks per second)
};

export default function Dashboard() {
  const router = useRouter();
  const [activeTab, setActiveTab] = useState<"monitoring" | "statistics" | "settings" | "admin">("monitoring");
  const [userLogin, setUserLogin] = useState("");
  const [loading, setLoading] = useState(true);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [isSettingsDropdownOpen, setIsSettingsDropdownOpen] = useState(false);
  const [activeSettingsSubTab, setActiveSettingsSubTab] = useState<"telegram" | "format" | "charts" | "spikes" | "blacklist" | "strategies">("spikes");
  
  const [exchanges, setExchanges] = useState<Exchange[]>([]);
  const [totalDetects, setTotalDetects] = useState(0);
  const [uptimeSeconds, setUptimeSeconds] = useState<number | null>(0);
  const [startTime, setStartTime] = useState<number | null>(null);
  const [exchangeLimits, setExchangeLimits] = useState<Record<string, { spot: number; linear: number }>>({});
  
  // Состояния для статистики стрел
  const [spikesStats, setSpikesStats] = useState<{
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
  } | null>(null);
  const [spikesStatsLoading, setSpikesStatsLoading] = useState(false);
  const [statisticsMode, setStatisticsMode] = useState<"personal" | "global">("personal");
  const [statisticsPeriod, setStatisticsPeriod] = useState<number>(30);
  const [deletingSpikes, setDeletingSpikes] = useState(false);


  // Проверка, является ли текущий пользователь администратором (без учета регистра)
  const isAdmin = userLogin?.toLowerCase() === "влад";

  // Восстанавливаем последнюю активную вкладку при загрузке
  useEffect(() => {
    if (typeof window === "undefined") return;

    const stored = window.localStorage.getItem("dashboard_active_tab") as
      | "monitoring"
      | "statistics"
      | "settings"
      | "admin"
      | null;

    if (stored) {
      setActiveTab(stored);
    }
  }, []);

  // Сохраняем активную вкладку между обновлениями страницы
  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem("dashboard_active_tab", activeTab);
    // Закрываем выпадающее меню только при переключении на другую вкладку
    if (activeTab !== "settings") {
      setIsSettingsDropdownOpen(false);
    } else {
      // Если переключились на настройки, открываем меню
      setIsSettingsDropdownOpen(true);
    }
  }, [activeTab]);

  const fetchMetrics = async () => {
    try {
      // Загружаем метрики, статистику бирж, статус системы и статистику детектов параллельно
      const [metricsRes, statsRes, statusRes, spikesStatsRes] = await Promise.allSettled([
        fetch("/api/metrics").catch(() => null),
        fetch("/api/exchanges/stats").catch(() => null),
        fetch("/api/status").catch(() => null),
        fetch("/api/spikes/stats").catch(() => null)
      ]);
      
      // Обрабатываем результаты с проверкой статуса
      const metricsResult = metricsRes.status === "fulfilled" && metricsRes.value ? metricsRes.value : null;
      const statsResult = statsRes.status === "fulfilled" && statsRes.value ? statsRes.value : null;
      const statusResult = statusRes.status === "fulfilled" && statusRes.value ? statusRes.value : null;
      const spikesStatsResult = spikesStatsRes.status === "fulfilled" && spikesStatsRes.value ? spikesStatsRes.value : null;
      
      // Проверяем доступность API сервера
      if (!metricsResult || !statsResult) {
        const errorMsg = metricsRes.status === "rejected" || statsRes.status === "rejected"
          ? "API сервер недоступен. Убедитесь, что FastAPI сервер запущен (python api_server.py)"
          : "Ошибка загрузки данных. Проверьте, что API сервер запущен.";
        console.warn(errorMsg);
        // Показываем пустые данные вместо полного стопа
        if (!metricsResult) {
          console.warn("Не удалось загрузить метрики");
        }
        if (!statsResult) {
          console.warn("Не удалось загрузить статистику бирж");
        }
        // Не возвращаемся, продолжаем обработку с пустыми данными
      }
      
      // Обрабатываем ответы метрик
      let metricsData = null;
      if (metricsResult && metricsResult.ok) {
        try {
          metricsData = await metricsResult.json();
        } catch (e) {
          console.error("Ошибка парсинга JSON метрик:", e);
          metricsData = null;
        }
      } else if (metricsResult && !metricsResult.ok) {
        try {
          const errorData = await metricsResult.json().catch(async () => {
            const errorText = await metricsResult.text().catch(() => "Unknown error");
            return { error: errorText };
          });
          console.error("Ошибка загрузки метрик:", metricsResult.status, errorData.detail || errorData.error || JSON.stringify(errorData));
        } catch (e) {
          console.error("Ошибка загрузки метрик:", metricsResult.status, "Unknown error");
        }
      }
      
      // Обрабатываем ответы статистики бирж
      let statsData = null;
      if (statsResult && statsResult.ok) {
        try {
          statsData = await statsResult.json();
        } catch (e) {
          console.error("Ошибка парсинга JSON статистики бирж:", e);
          statsData = null;
        }
      } else if (statsResult && !statsResult.ok) {
        try {
          const errorData = await statsResult.json().catch(async () => {
            const errorText = await statsResult.text().catch(() => "Unknown error");
            return { error: errorText };
          });
          console.error("Ошибка загрузки статистики бирж:", statsResult.status, errorData.detail || errorData.error || JSON.stringify(errorData));
        } catch (e) {
          console.error("Ошибка загрузки статистики бирж:", statsResult.status, "Unknown error");
        }
      }
      
      // Если нет критических данных, выходим
      if (!metricsData || !statsData) {
        console.warn("Не удалось загрузить критически важные данные. Метрики:", !!metricsData, "Статистика:", !!statsData);
        return;
      }
      
      // Получаем статус системы и общее количество детектов
      let uptimeSecondsValue: number | null = null;
      let totalDetectsValue = 0;
      let startTimeValue: number | null = null;
      
      if (statusResult && statusResult.ok) {
        try {
          const statusData = await statusResult.json();
          // Используем только alerts_since_start для детектов с момента запуска
          totalDetectsValue = statusData.alerts_since_start ?? 0;
          // Если uptime_seconds === null, значит main.py не запущен
          uptimeSecondsValue = statusData.uptime_seconds !== undefined ? statusData.uptime_seconds : null;
          startTimeValue = statusData.start_time !== undefined ? statusData.start_time : null;
        } catch (e) {
          console.warn("Не удалось получить статус системы:", e);
        }
      }
      
      // Устанавливаем значения
      setTotalDetects(totalDetectsValue);
      setUptimeSeconds(uptimeSecondsValue);
      setStartTime(startTimeValue);
      
      // Используем значение для расчетов
      const uptimeSeconds = uptimeSecondsValue;
      
      console.log("Metrics data:", metricsData);
      console.log("Exchanges stats:", statsData);
      
      // Если нет данных, показываем сообщение
      if (!metricsData || !metricsData.metrics) {
        console.warn("Метрики не получены или пусты. Убедитесь что:");
        console.warn("1. FastAPI сервер запущен (python api_server.py)");
        console.warn("2. Основной детектор запущен (python main.py)");
        console.warn("3. В базе данных есть записи в таблице spikes");
        return;
      }
      
      if (!statsData || !statsData.exchanges) {
        console.warn("Статистика бирж не получена или пуста. Убедитесь что:");
        console.warn("1. FastAPI сервер запущен (python api_server.py)");
        console.warn("2. Основной детектор запущен (python main.py)");
        console.warn("3. В базе данных есть записи в таблице stats");
        return;
      }
      
      // Сохраняем лимиты из API (если есть)
      if (statsData.limits) {
        console.log("Загружены лимиты бирж:", statsData.limits);
        setExchangeLimits(statsData.limits);
      } else {
        console.warn("Лимиты бирж не получены из API");
      }
      
      // Обрабатываем данные даже если они частично пустые
      if (metricsData.metrics && statsData.exchanges) {
        // Создаем список всех бирж и их типов рынка
        const exchangeNames = ["Binance", "Bybit", "Gate.io", "Bitget", "Hyperliquid"];
        const markets: ("spot" | "linear")[] = ["spot", "linear"];
        
        const newExchanges: Exchange[] = [];
        
        for (const exchangeName of exchangeNames) {
          // Нормализуем имя биржи для поиска в метриках
          let nameKey = exchangeName.toLowerCase();
          // Gate.io в метриках хранится как "gate"
          if (nameKey === "gate.io") {
            nameKey = "gate";
          }
          
          // Получаем статистику WS для биржи
          const exchangeStats = statsData.exchanges[nameKey] || {
            spot: { active_connections: 0, reconnects: 0, active_symbols: 0 },
            linear: { active_connections: 0, reconnects: 0, active_symbols: 0 }
          };
          
          // Создаем отдельную запись для spot и linear
          for (const market of markets) {
            const marketStats = exchangeStats[market] || {};
            const wsConnections = marketStats.active_connections || 0;
            const symbols = marketStats.active_symbols || 0;
            const reconnects = marketStats.reconnects || 0;
            
            // Вычисляем ожидаемое количество WebSocket-соединений на основе лимитов из API
            const exchangeKey = nameKey.toLowerCase();
            const limits = exchangeLimits[exchangeKey];
            
            // Отладка: проверяем наличие лимитов
            if (!limits && Object.keys(exchangeLimits).length > 0) {
              console.warn(`Лимиты не найдены для биржи: ${exchangeKey}. Доступные ключи:`, Object.keys(exchangeLimits));
            }
            let expectedConnections = 0;
            
            // Вычисляем максимальное количество соединений на основе лимитов
            if (limits) {
              const limitPerConnection = market === "spot" ? limits.spot : limits.linear;
              if (limitPerConnection > 0) {
                // Вычисляем на основе количества символов
                if (symbols > 0) {
                  expectedConnections = Math.ceil(symbols / limitPerConnection);
                } else if (wsConnections > 0) {
                  // Если символов нет, но есть активные соединения, используем их как максимум
                  expectedConnections = wsConnections;
                }
              }
            }
            
            // Если не удалось вычислить на основе лимитов, но есть активные соединения,
            // используем текущее количество как максимум
            if (expectedConnections === 0 && wsConnections > 0) {
              expectedConnections = wsConnections;
            }
            
            // Формируем строку с информацией о WS в формате "текущее/максимальное"
            let wsInfo: string;
            if (expectedConnections > 0) {
              wsInfo = `${wsConnections}/${expectedConnections}`;
            } else {
              // Если нет данных вообще, показываем только текущее
              wsInfo = `${wsConnections} WS`;
            }
            
            // Получаем свечи для конкретного рынка - сначала из API, потом из метрик
            let candles = marketStats.candles || 0;
            if (candles === 0) {
              candles = metricsData.metrics[`candles_processed_${nameKey}_${market}`] || 0;
            }
            
            // Получаем время последнего обновления из метрик (last_candle_ts) - это основной источник
            // Получаем время последнего обновления из API (last_candle_time) или метрик (last_candle_ts)
            let lastUpdateTimestamp: number | undefined = undefined;
            let lastUpdate = "Нет данных";
            
            // Сначала пытаемся получить из API (last_candle_time в формате ISO строки)
            const lastCandleTime = marketStats.last_candle_time;
            if (lastCandleTime) {
              try {
                // Парсим ISO строку в Date и конвертируем в timestamp
                const date = new Date(lastCandleTime);
                if (!isNaN(date.getTime())) {
                  lastUpdateTimestamp = date.getTime();
                  lastUpdate = date.toLocaleString("ru-RU");
                }
              } catch (e) {
                console.warn(`Ошибка парсинга last_candle_time для ${nameKey} ${market}:`, e);
              }
            }
            
            // Fallback: если нет в API, пытаемся получить из метрик (last_candle_ts)
            if (!lastUpdateTimestamp) {
              const lastCandleTS = metricsData.metrics[`last_candle_ts_${nameKey}_${market}`] || 0;
              if (lastCandleTS > 0) {
                // Конвертируем timestamp в миллисекунды если в секундах
                const ts_sec = lastCandleTS < 1e10 ? lastCandleTS : Math.floor(lastCandleTS / 1000);
                lastUpdateTimestamp = ts_sec * 1000; // Конвертируем в миллисекунды
                lastUpdate = new Date(lastUpdateTimestamp).toLocaleString("ru-RU");
              }
            }
            
            // Получаем T/s (тики в секунду) из статистики биржи
            // Значение уже рассчитано на бэкенде и приходит из API
            const tps = marketStats.ticks_per_second || 0;
            
            // Определяем статус на основе времени последней свечи И количества переподключений
            // Если свеча не приходила 1 минуту - биржа отключена
            // Если свечи приходят, но много переподключений (>15) - биржа с проблемами
            let status: "active" | "inactive" | "problems" = "inactive";
            
            const now = Date.now();
            const oneMinuteAgo = now - 60 * 1000; // 1 минута в миллисекундах
            
            if (lastUpdateTimestamp && lastUpdateTimestamp >= oneMinuteAgo) {
              // Если свеча приходила менее минуты назад - проверяем количество переподключений
              if (reconnects > 15) {
                status = "problems";
              } else {
                status = "active";
              }
            } else {
              // Если timestamp отсутствует или последнее обновление было больше минуты назад - биржа отключена
              status = "inactive";
            }
            
            newExchanges.push({
              name: exchangeName,
              market: market,
              status: status,
              websocketInfo: wsInfo,
              candles: candles,
              lastUpdate: lastUpdate,
              lastUpdateTimestamp: lastUpdateTimestamp,
              wsConnections: wsConnections,
              reconnects: reconnects,
              tradingPairs: symbols,
              tps: tps
            });
          }
        }
        
        setExchanges(newExchanges);
      }
    } catch (err) {
      console.error("Ошибка загрузки метрик:", err);
      // Если ошибка, показываем предупреждение с деталями
      console.warn("Не удалось загрузить данные. Убедитесь что:");
      console.warn("1. FastAPI сервер запущен на http://localhost:8001");
      console.warn("2. Основной детектор запущен (python main.py)");
      console.warn("3. Сеть доступна и порты не заблокированы");
      if (err instanceof Error) {
        console.error("Детали ошибки:", err.message, err.stack);
      }
    }
  };


  useEffect(() => {
    // Проверяем авторизацию
    if (typeof window !== "undefined") {
      const token = localStorage.getItem("auth_token");
      const login = localStorage.getItem("user_login");
      
      if (!token) {
        router.push("/login");
        return;
      }

      setUserLogin(login || "");
    }
    
    fetchMetrics();
    setLoading(false);
    
    // Автообновление каждые 10 секунд
    const interval = setInterval(fetchMetrics, 10000);
    
    // Периодическая проверка статуса бирж на основе времени последней свечи
    // Если свеча не приходила 1 минуту - биржа отключена
    // Если свечи приходят, но много переподключений (>15) - биржа с проблемами
    const statusCheckInterval = setInterval(() => {
      setExchanges((prevExchanges) => {
        const now = Date.now();
        const oneMinuteAgo = now - 60 * 1000; // 1 минута в миллисекундах
        
        return prevExchanges.map((exchange) => {
          // Определяем статус на основе времени последней свечи И количества переподключений
          if (exchange.lastUpdateTimestamp && exchange.lastUpdateTimestamp >= oneMinuteAgo) {
            // Если свеча приходила менее минуты назад - проверяем переподключения
            if (exchange.reconnects > 15) {
              return {
                ...exchange,
                status: "problems" as const
              };
            } else {
              return {
                ...exchange,
                status: "active" as const
              };
            }
          } else {
            // Если timestamp отсутствует или последнее обновление было больше минуты назад - биржа отключена
            return {
              ...exchange,
              status: "inactive" as const
            };
          }
        });
      });
    }, 5000); // Проверяем каждые 5 секунд
    
    return () => {
      clearInterval(interval);
      clearInterval(statusCheckInterval);
    };
  }, [router]);

  // Загрузка статистики стрел при переключении на вкладку


  // Состояние для деталей по монете
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);
  const [symbolSpikes, setSymbolSpikes] = useState<any[]>([]);
  const [symbolSpikesLoading, setSymbolSpikesLoading] = useState(false);

  useEffect(() => {
    const fetchSpikesStats = async () => {
      if (activeTab === "statistics") {
        setSpikesStatsLoading(true);
        try {
          let url: string;
          if (statisticsMode === "personal") {
            // Личная статистика текущего пользователя
            url = `/api/users/${encodeURIComponent(userLogin)}/spikes/stats?days=${statisticsPeriod}`;
          } else {
            // Рыночная статистика (пользователь Stats)
            url = `/api/users/Stats/spikes/stats?days=${statisticsPeriod}`;
          }
          
          const res = await fetch(url);
          if (res.ok) {
            const data = await res.json();
            setSpikesStats(data);
          } else {
            console.error("Ошибка загрузки статистики стрел:", res.status);
            setSpikesStats(null);
          }
        } catch (error) {
          console.error("Ошибка загрузки статистики стрел:", error);
          setSpikesStats(null);
        } finally {
          setSpikesStatsLoading(false);
        }
      }
    };
    
    fetchSpikesStats();
  }, [activeTab, statisticsMode, statisticsPeriod, userLogin]);

  // Загрузка деталей по монете
  useEffect(() => {
    const fetchSymbolSpikes = async () => {
      if (selectedSymbol) {
        setSymbolSpikesLoading(true);
        try {
          let url: string;
          if (statisticsMode === "personal") {
            // Личная статистика текущего пользователя
            url = `/api/users/${encodeURIComponent(userLogin)}/spikes/by-symbol/${encodeURIComponent(selectedSymbol)}`;
          } else {
            // Рыночная статистика (пользователь Stats)
            url = `/api/users/Stats/spikes/by-symbol/${encodeURIComponent(selectedSymbol)}`;
          }
          
          const res = await fetch(url);
          if (res.ok) {
            const data = await res.json();
            setSymbolSpikes(data.spikes || []);
          } else {
            console.error("Ошибка загрузки деталей по монете:", res.status);
            setSymbolSpikes([]);
          }
        } catch (error) {
          console.error("Ошибка загрузки деталей по монете:", error);
          setSymbolSpikes([]);
        } finally {
          setSymbolSpikesLoading(false);
        }
      }
    };
    
    fetchSymbolSpikes();
  }, [selectedSymbol, statisticsMode, userLogin]);

  // Функция для очистки статистики стрел пользователя
  const handleDeleteSpikes = async () => {
    if (!userLogin) return;
    
    // Подтверждение очистки
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
        // Обновляем статистику после удаления - сбрасываем и перезагружаем
        setSpikesStats(null);
        // Перезагружаем статистику
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
        const errorData = await res.json().catch(() => ({ error: "Неизвестная ошибка" }));
        alert(`Ошибка при очистке статистики: ${errorData.error || errorData.detail || "Неизвестная ошибка"}`);
      }
    } catch (error) {
      console.error("Ошибка при очистке статистики:", error);
      alert("Ошибка при очистке статистики. Попробуйте позже.");
    } finally {
      setDeletingSpikes(false);
    }
  };

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center gradient-bg">
        <div className="flex flex-col items-center gap-4">
          <div className="w-16 h-16 border-4 border-emerald-500 border-t-transparent rounded-full animate-spin"></div>
          <div className="text-white text-xl animate-pulse-slow">Загрузка...</div>
        </div>
      </div>
    );
  }

  // Подсчитываем активные подключения (spot или linear считаются отдельно)
  // Активные - это все биржи, которые получают свечи (не "inactive")
  // Т.е. статус "active" или "problems" - оба считаются активными
  const activeExchanges = exchanges.filter(e => e.status !== "inactive").length;
  const totalCandles = exchanges.reduce((sum, e) => sum + e.candles, 0);

  const formatNumber = (num: number) => {
    return new Intl.NumberFormat("ru-RU").format(num);
  };

  // Форматирование времени работы программы
  const formatUptime = (seconds: number | null): string => {
    if (seconds === null || seconds === undefined) {
      return "не запущено";
    }
    if (seconds === 0) {
      return "неизвестно";
    }
    
    const days = Math.floor(seconds / 86400);
    const hours = Math.floor((seconds % 86400) / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;
    
    const parts: string[] = [];
    
    if (days > 0) {
      parts.push(`${days} ${days === 1 ? 'день' : days < 5 ? 'дня' : 'дней'}`);
    }
    if (hours > 0) {
      parts.push(`${hours} ${hours === 1 ? 'час' : hours < 5 ? 'часа' : 'часов'}`);
    }
    if (minutes > 0 && days === 0) {
      parts.push(`${minutes} ${minutes === 1 ? 'минуту' : minutes < 5 ? 'минуты' : 'минут'}`);
    }
    if (secs > 0 && days === 0 && hours === 0) {
      parts.push(`${secs} ${secs === 1 ? 'секунду' : secs < 5 ? 'секунды' : 'секунд'}`);
    }
    
    if (parts.length === 0) {
      return "менее секунды";
    }
    
    return parts.join(" ");
  };



  return (
    <div className="min-h-screen gradient-bg flex">
      {/* Mobile Menu Overlay */}
      {isMobileMenuOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-40 md:hidden"
          onClick={() => setIsMobileMenuOpen(false)}
        />
      )}

      {/* Sidebar */}
      <div className={`fixed md:static inset-y-0 left-0 z-50 w-96 glass-strong border-r border-zinc-800 flex flex-col animate-slide-in transform transition-transform duration-300 ease-in-out ${
        isMobileMenuOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0'
      }`}>
        {/* Header */}
        <div className="p-9 border-b border-zinc-800">
          <div className="flex items-center gap-[18px] mb-[18px]">
            <div className="w-12 h-12 bg-gradient-to-br from-emerald-500 to-emerald-600 rounded-lg flex items-center justify-center shadow-emerald hover-glow">
              <svg className="w-[30px] h-[30px] text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
              </svg>
            </div>
            <h1 className="text-3xl font-bold gradient-text">CRYPTO Monitor</h1>
          </div>
          <p className="text-base text-zinc-400">{userLogin || "user"}</p>
        </div>

        {/* Navigation */}
        <nav className="flex-1 p-6 space-y-3">
          <button
            onClick={() => {
              setActiveTab("monitoring");
              setIsMobileMenuOpen(false);
            }}
            className={`w-full flex items-center gap-[18px] px-6 py-5 rounded-lg smooth-transition ripple text-base ${
              activeTab === "monitoring"
                ? "bg-zinc-700 text-white nav-active"
                : "text-zinc-400 hover:text-white hover:bg-zinc-800/50 hover-glow"
            }`}
          >
            <svg className="w-[30px] h-[30px]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
            </svg>
            Мониторинг
          </button>

          <button
            onClick={() => {
              setActiveTab("statistics");
              setIsMobileMenuOpen(false);
            }}
            className={`w-full flex items-center gap-[18px] px-6 py-5 rounded-lg smooth-transition ripple text-base ${
              activeTab === "statistics"
                ? "bg-zinc-700 text-white nav-active"
                : "text-zinc-400 hover:text-white hover:bg-zinc-800/50 hover-glow"
            }`}
          >
            <svg className="w-[30px] h-[30px]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
            </svg>
            Статистика стрел
          </button>

          <div className="relative settings-dropdown-container">
            <button
              onClick={() => {
                setActiveTab("settings");
                // Если уже на вкладке настроек, переключаем меню, иначе открываем его
                if (activeTab === "settings") {
                  setIsSettingsDropdownOpen(!isSettingsDropdownOpen);
                } else {
                  setIsSettingsDropdownOpen(true);
                }
                setIsMobileMenuOpen(false);
              }}
              className={`w-full flex items-center justify-between gap-[18px] px-6 py-5 rounded-lg smooth-transition ripple text-base ${
                activeTab === "settings"
                  ? "bg-zinc-700 text-white nav-active"
                  : "text-zinc-400 hover:text-white hover:bg-zinc-800/50 hover-glow"
              }`}
            >
              <div className="flex items-center gap-[18px]">
                <svg className="w-[30px] h-[30px]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                </svg>
                Настройки
              </div>
              <svg 
                className={`w-5 h-5 transition-transform ${isSettingsDropdownOpen && activeTab === "settings" ? "rotate-180" : ""}`}
                fill="none" 
                stroke="currentColor" 
                viewBox="0 0 24 24"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
              </svg>
            </button>
            
            {/* Выпадающее меню подтем */}
            {isSettingsDropdownOpen && activeTab === "settings" && (
              <div className="mt-2 ml-6 space-y-1 bg-zinc-800/95 border border-zinc-700 rounded-lg p-2 shadow-xl z-50">
                <button
                  onClick={() => {
                    setActiveSettingsSubTab("spikes");
                    setIsMobileMenuOpen(false);
                  }}
                  className={`w-full text-left px-4 py-2 rounded-lg smooth-transition text-sm ${
                    activeSettingsSubTab === "spikes"
                      ? "bg-zinc-700 text-white"
                      : "text-zinc-400 hover:text-white hover:bg-zinc-800/50"
                  }`}
                >
                  Настройки прострелов
                </button>
                <button
                  onClick={() => {
                    setActiveSettingsSubTab("telegram");
                    setIsMobileMenuOpen(false);
                  }}
                  className={`w-full text-left px-4 py-2 rounded-lg smooth-transition text-sm ${
                    activeSettingsSubTab === "telegram"
                      ? "bg-zinc-700 text-white"
                      : "text-zinc-400 hover:text-white hover:bg-zinc-800/50"
                  }`}
                >
                  Настройка Телеграм
                </button>
                <button
                  onClick={() => {
                    setActiveSettingsSubTab("format");
                    setIsMobileMenuOpen(false);
                  }}
                  className={`w-full text-left px-4 py-2 rounded-lg smooth-transition text-sm ${
                    activeSettingsSubTab === "format"
                      ? "bg-zinc-700 text-white"
                      : "text-zinc-400 hover:text-white hover:bg-zinc-800/50"
                  }`}
                >
                  Формат сообщений
                </button>
                <button
                  onClick={() => {
                    setActiveSettingsSubTab("charts");
                    setIsMobileMenuOpen(false);
                  }}
                  className={`w-full text-left px-4 py-2 rounded-lg smooth-transition text-sm ${
                    activeSettingsSubTab === "charts"
                      ? "bg-zinc-700 text-white"
                      : "text-zinc-400 hover:text-white hover:bg-zinc-800/50"
                  }`}
                >
                  Отправка графиков
                </button>
                <button
                  onClick={() => {
                    setActiveSettingsSubTab("blacklist");
                    setIsMobileMenuOpen(false);
                  }}
                  className={`w-full text-left px-4 py-2 rounded-lg smooth-transition text-sm ${
                    activeSettingsSubTab === "blacklist"
                      ? "bg-zinc-700 text-white"
                      : "text-zinc-400 hover:text-white hover:bg-zinc-800/50"
                  }`}
                >
                  Чёрный список
                </button>
                <button
                  onClick={() => {
                    setActiveSettingsSubTab("strategies");
                    setIsMobileMenuOpen(false);
                  }}
                  className={`w-full text-left px-4 py-2 rounded-lg smooth-transition text-sm ${
                    activeSettingsSubTab === "strategies"
                      ? "bg-zinc-700 text-white"
                      : "text-zinc-400 hover:text-white hover:bg-zinc-800/50"
                  }`}
                >
                  Стратегии
                </button>
              </div>
            )}
          </div>

          {/* Админ панель - только для Влад */}
          {isAdmin && (
            <button
              onClick={() => {
                setActiveTab("admin");
                setIsMobileMenuOpen(false);
              }}
              className={`w-full flex items-center gap-[18px] px-6 py-5 rounded-lg smooth-transition ripple text-base ${
                activeTab === "admin"
                  ? "bg-zinc-700 text-white nav-active"
                  : "text-zinc-400 hover:text-white hover:bg-zinc-800/50 hover-glow"
              }`}
            >
              <svg className="w-[30px] h-[30px]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
              </svg>
              Админ панель
            </button>
          )}
        </nav>

        {/* Logout */}
        <div className="p-6 border-t border-zinc-800">
          <button
            onClick={() => {
              localStorage.removeItem("auth_token");
              localStorage.removeItem("user_login");
              router.push("/login");
            }}
            className="w-full flex items-center gap-[18px] px-6 py-5 rounded-lg text-base text-zinc-400 hover:text-white hover:bg-zinc-800/50 smooth-transition ripple hover-glow"
          >
            <svg className="w-[30px] h-[30px]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
            </svg>
            Выход
          </button>
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1 overflow-auto">
        <div className={`p-4 md:p-8 ${activeTab === "settings" ? "max-w-[1600px] mx-auto" : ""}`}>
          {/* Mobile Header with Hamburger */}
          <div className="md:hidden mb-4 flex items-center justify-between">
            <button
              onClick={() => setIsMobileMenuOpen(true)}
              className="p-2 glass rounded-lg hover:bg-zinc-800/50 smooth-transition ripple"
              aria-label="Открыть меню"
            >
              <svg className="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
              </svg>
            </button>
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 bg-gradient-to-br from-emerald-500 to-emerald-600 rounded-lg flex items-center justify-center shadow-emerald">
                <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                </svg>
              </div>
              <h1 className="text-lg font-bold gradient-text">CRYPTO Monitor</h1>
            </div>
          </div>

          {/* Conditional Content based on activeTab */}
          {activeTab === "monitoring" && (
            <MonitoringTab
              exchanges={exchanges}
              totalDetects={totalDetects}
              uptimeSeconds={uptimeSeconds}
              startTime={startTime}
            />
          )}

          {activeTab === "statistics" && (
            <StatisticsTab userLogin={userLogin} />
          )}

          {activeTab === "settings" && (
            <SettingsTab 
              userLogin={userLogin} 
              activeSubTab={activeSettingsSubTab}
              onSubTabChange={setActiveSettingsSubTab}
            />
          )}

          {/* Админ панель */}
          {activeTab === "admin" && isAdmin && (
            <AdminTab userLogin={userLogin} isAdmin={isAdmin} activeTab={activeTab} />
          )}
        </div>
      </div>
    </div>
  );
}



