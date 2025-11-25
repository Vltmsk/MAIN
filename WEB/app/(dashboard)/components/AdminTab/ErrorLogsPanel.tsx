"use client";

import { ErrorLog } from "./types";

interface ErrorLogsPanelProps {
  errorLogs: ErrorLog[];
  loading: boolean;
  filter: {
    exchange?: string;
    error_type?: string;
    limit: number;
  };
  onFilterChange: (filter: {
    exchange?: string;
    error_type?: string;
    limit: number;
  }) => void;
  onRefresh: () => void;
  onDelete: (errorId: number) => void;
  onDeleteAll: () => void;
  isAdmin: boolean;
}

export default function ErrorLogsPanel({
  errorLogs,
  loading,
  filter,
  onFilterChange,
  onRefresh,
  onDelete,
  onDeleteAll,
  isAdmin,
}: ErrorLogsPanelProps) {
  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-xl font-bold text-white">Логи ошибок</h2>
        <div className="flex gap-2">
          {isAdmin && (
            <button
              onClick={onDeleteAll}
              disabled={loading}
              className="px-4 py-2 bg-red-500 text-white rounded-lg hover:bg-red-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed text-sm"
              title="Удалить все логи ошибок"
            >
              Удалить все
            </button>
          )}
          <button
            onClick={onRefresh}
            disabled={loading}
            className="px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed text-sm"
          >
            {loading ? "Загрузка..." : "Обновить"}
          </button>
        </div>
      </div>

      {/* Фильтры */}
      <div className="grid md:grid-cols-4 gap-4 mb-4">
        <div>
          <label className="block text-sm text-zinc-400 mb-1">Биржа</label>
          <select
            value={filter.exchange || ""}
            onChange={(e) =>
              onFilterChange({
                ...filter,
                exchange: e.target.value || undefined,
              })
            }
            className="w-full px-4 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="">Все биржи</option>
            <option value="binance">Binance</option>
            <option value="bybit">Bybit</option>
            <option value="bitget">Bitget</option>
            <option value="gate">Gate.io</option>
          </select>
        </div>
        <div>
          <label className="block text-sm text-zinc-400 mb-1">Тип ошибки</label>
          <select
            value={filter.error_type || ""}
            onChange={(e) =>
              onFilterChange({
                ...filter,
                error_type: e.target.value || undefined,
              })
            }
            className="w-full px-4 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="">Все типы</option>
            <option value="reconnect">Reconnect</option>
            <option value="websocket_error">WebSocket Error</option>
            <option value="critical">Critical</option>
            <option value="connection_error">Connection Error</option>
            <option value="telegram_error">Telegram Error</option>
          </select>
        </div>
        <div>
          <label className="block text-sm text-zinc-400 mb-1">Лимит записей</label>
          <input
            type="number"
            min="10"
            max="1000"
            step="10"
            value={filter.limit}
            onChange={(e) =>
              onFilterChange({
                ...filter,
                limit: parseInt(e.target.value) || 100,
              })
            }
            className="w-full px-4 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
        <div className="flex items-end">
          <button
            onClick={() => {
              onFilterChange({ limit: 100 });
            }}
            className="w-full px-4 py-2 bg-zinc-700 text-white rounded-lg hover:bg-zinc-600 transition-colors text-sm"
          >
            Сбросить фильтры
          </button>
        </div>
      </div>

      {/* Таблица логов */}
      <div className="overflow-x-auto">
        {loading ? (
          <div className="text-center py-8 text-zinc-400">Загрузка логов...</div>
        ) : errorLogs.length === 0 ? (
          <div className="text-center py-8 text-zinc-400">Логи отсутствуют</div>
        ) : (
          <div className="space-y-2 max-h-96 overflow-y-auto">
            {errorLogs.map((error) => (
              <div
                key={error.id}
                className="bg-zinc-800 border border-zinc-700 rounded-lg p-4 hover:bg-zinc-750 transition-colors"
              >
                <div className="flex items-start justify-between mb-2">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="px-2 py-1 bg-red-900/30 text-red-400 rounded text-xs font-medium">
                      {error.error_type}
                    </span>
                    {error.exchange && (
                      <span className="px-2 py-1 bg-blue-900/30 text-blue-400 rounded text-xs">
                        {error.exchange}
                      </span>
                    )}
                    {error.market && (
                      <span className="px-2 py-1 bg-purple-900/30 text-purple-400 rounded text-xs">
                        {error.market}
                      </span>
                    )}
                    {error.symbol && (
                      <span className="px-2 py-1 bg-emerald-900/30 text-emerald-400 rounded text-xs">
                        {error.symbol}
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-zinc-500">
                      {new Date(error.timestamp).toLocaleString("ru-RU")}
                    </span>
                    {isAdmin && (
                      <button
                        onClick={() => onDelete(error.id)}
                        className="px-2 py-1 bg-red-500/20 text-red-400 rounded text-xs hover:bg-red-500/30 transition-colors"
                        title="Удалить этот лог"
                      >
                        ✕
                      </button>
                    )}
                  </div>
                </div>
                <div className="text-sm text-white mb-2">{error.error_message}</div>
                {error.connection_id && (
                  <div className="text-xs text-zinc-500 mb-1">Connection ID: {error.connection_id}</div>
                )}
                {error.stack_trace && (
                  <details className="mt-2">
                    <summary className="text-xs text-zinc-400 cursor-pointer hover:text-zinc-300">
                      Показать стек трейс
                    </summary>
                    <pre className="mt-2 p-2 bg-zinc-900 rounded text-xs text-zinc-300 overflow-x-auto">
                      {error.stack_trace}
                    </pre>
                  </details>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

