"use client";

type Exchange = {
  name: string;
  market: "spot" | "linear";
  status: "active" | "inactive" | "problems";
  websocketInfo: string;
  candles: number;
  lastUpdate: string;
  lastUpdateTimestamp?: number;
  wsConnections: number;
  reconnects: number;
  tradingPairs: number;
  tps: number;
};

interface MonitoringTabProps {
  exchanges: Exchange[];
  totalDetects: number;
  uptimeSeconds: number | null;
  startTime: number | null;
}

const formatNumber = (num: number) => {
  return new Intl.NumberFormat("ru-RU").format(num);
};

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
    parts.push(`${minutes} ${minutes === 1 ? 'минута' : minutes < 5 ? 'минуты' : 'минут'}`);
  }
  if (secs > 0 && days === 0 && hours === 0) {
    parts.push(`${secs} ${secs === 1 ? 'секунда' : secs < 5 ? 'секунды' : 'секунд'}`);
  }
  
  return parts.length > 0 ? parts.join(" ") : "0 секунд";
};

export default function MonitoringTab({
  exchanges,
  totalDetects,
  uptimeSeconds,
  startTime,
}: MonitoringTabProps) {
  const activeExchanges = exchanges.filter(e => e.status !== "inactive").length;
  const totalCandles = exchanges.reduce((sum, e) => sum + e.candles, 0);

  return (
    <>
      {/* Header */}
      <div className="mb-6 md:mb-8 animate-fade-in">
        <h1 className="text-2xl md:text-3xl font-bold gradient-text mb-2">Мониторинг бирж</h1>
        <p className="text-zinc-400">
          Статус подключения и статистика в реальном времени
        </p>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
        {/* Детекты */}
        <div className="glass-strong border border-zinc-800 rounded-xl p-6 relative overflow-hidden card-hover gradient-border float-animation shadow-emerald animate-scale-in">
          <div className="absolute top-4 right-4 text-emerald-500 opacity-20">
            <svg className="w-16 h-16" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
            </svg>
          </div>
          <div className="text-sm text-zinc-400 mb-2">Детекты</div>
          <div className="text-4xl font-bold text-white">{formatNumber(totalDetects)}</div>
          <div className="text-xs text-zinc-500 mt-2">Детектов с момента запуска</div>
        </div>

        {/* Активные */}
        <div className="glass-strong border border-zinc-800 rounded-xl p-6 relative overflow-hidden card-hover gradient-border float-animation shadow-blue animate-scale-in" style={{ animationDelay: '0.2s' }}>
          <div className="absolute top-4 right-4 text-blue-500 opacity-20">
            <svg className="w-16 h-16" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
            </svg>
          </div>
          <div className="text-sm text-zinc-400 mb-2">Активные</div>
          <div className="text-4xl font-bold text-blue-400">{activeExchanges}</div>
          <div className="text-xs text-zinc-500 mt-2">Активных подключений</div>
        </div>

        {/* Всего свечей */}
        <div className="glass-strong border border-zinc-800 rounded-xl p-6 relative overflow-hidden card-hover gradient-border float-animation shadow-purple animate-scale-in" style={{ animationDelay: '0.4s' }}>
          <div className="absolute top-4 right-4 text-purple-500 opacity-20">
            <svg className="w-16 h-16" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
          <div className="text-sm text-zinc-400 mb-2">Всего свечей</div>
          <div className="text-4xl font-bold text-white">{formatNumber(totalCandles)}</div>
        </div>

        {/* Время работы */}
        <div className="glass-strong border border-zinc-800 rounded-xl p-6 relative overflow-hidden card-hover gradient-border float-animation shadow-orange animate-scale-in" style={{ animationDelay: '0.6s' }}>
          <div className="absolute top-4 right-4 text-orange-500 opacity-20">
            <svg className="w-16 h-16" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
          <div className="text-sm text-zinc-400 mb-2">Время работы</div>
          <div className="text-4xl font-bold text-white">{formatUptime(uptimeSeconds)}</div>
          <div className="text-xs text-zinc-500 mt-2">
            {startTime ? new Date(startTime * 1000).toLocaleString('ru-RU', { 
              day: '2-digit', 
              month: '2-digit', 
              year: 'numeric', 
              hour: '2-digit', 
              minute: '2-digit' 
            }) : 'Не запущено'}
          </div>
        </div>
      </div>

      {/* Exchange Status Table */}
      <div className="glass-strong border border-zinc-800 rounded-xl overflow-hidden card-hover animate-fade-in">
        <div className="p-6 border-b border-zinc-800">
          <h2 className="text-xl font-bold gradient-text mb-1">Состояние бирж</h2>
          <p className="text-sm text-zinc-400">Детальная информация по каждой бирже</p>
        </div>

        <div className="overflow-x-auto table-responsive">
          <table className="w-full">
            <thead className="bg-zinc-800/50">
              <tr>
                <th className="px-3 md:px-6 py-3 md:py-4 text-left text-xs md:text-sm font-semibold text-zinc-300">Биржа</th>
                <th className="px-3 md:px-6 py-3 md:py-4 text-left text-xs md:text-sm font-semibold text-zinc-300">Статус</th>
                <th className="px-3 md:px-6 py-3 md:py-4 text-left text-xs md:text-sm font-semibold text-zinc-300">Торговые пары</th>
                <th className="px-3 md:px-6 py-3 md:py-4 text-left text-xs md:text-sm font-semibold text-zinc-300">WebSocket</th>
                <th className="px-3 md:px-6 py-3 md:py-4 text-left text-xs md:text-sm font-semibold text-zinc-300">Свечи 1s</th>
                <th className="px-3 md:px-6 py-3 md:py-4 text-left text-xs md:text-sm font-semibold text-zinc-300">Переподключения</th>
                <th className="px-3 md:px-6 py-3 md:py-4 text-left text-xs md:text-sm font-semibold text-zinc-300">T/s</th>
                <th className="px-3 md:px-6 py-3 md:py-4 text-left text-xs md:text-sm font-semibold text-zinc-300">Обновлено</th>
              </tr>
            </thead>
            <tbody>
              {exchanges.map((exchange) => (
                <tr key={`${exchange.name}-${exchange.market}`} className="border-t border-zinc-800 table-row-hover">
                  <td className="px-3 md:px-6 py-3 md:py-4 text-white font-medium text-sm">
                    {exchange.name} <span className="text-zinc-500 text-xs">({exchange.market})</span>
                  </td>
                  <td className="px-3 md:px-6 py-3 md:py-4">
                    <span
                      className={`px-2 md:px-3 py-1 rounded-full text-xs font-medium smooth-transition ${
                        exchange.status === "active"
                          ? "bg-green-500/20 text-green-400 border border-green-500/50 status-pulse"
                          : exchange.status === "problems"
                          ? "bg-yellow-500/20 text-yellow-400 border border-yellow-500/50"
                          : "bg-red-500/20 text-red-400 border border-red-500/50"
                      }`}
                    >
                      {exchange.status === "active" ? "Активна" : exchange.status === "problems" ? "Проблемы" : "Отключена"}
                    </span>
                  </td>
                  <td className="px-3 md:px-6 py-3 md:py-4 text-zinc-300 text-sm">{formatNumber(exchange.tradingPairs)}</td>
                  <td className="px-3 md:px-6 py-3 md:py-4 text-zinc-300 text-xs md:text-sm">{exchange.websocketInfo}</td>
                  <td className="px-3 md:px-6 py-3 md:py-4 text-zinc-300 text-sm">{formatNumber(exchange.candles)}</td>
                  <td className="px-3 md:px-6 py-3 md:py-4 text-zinc-300 text-sm">{formatNumber(exchange.reconnects)}</td>
                  <td className="px-3 md:px-6 py-3 md:py-4 text-zinc-300 text-sm">{exchange.tps > 0 ? exchange.tps.toFixed(2) : "0"}</td>
                  <td className="px-3 md:px-6 py-3 md:py-4 text-zinc-400 text-xs md:text-sm">{exchange.lastUpdate || "Нет данных"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}

