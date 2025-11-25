"use client";

import { useEffect, useState } from "react";

type MetricsSetting = {
  user_id: number;
  user_name: string;
  enable_metrics: boolean;
  created_at?: string;
  updated_at?: string;
};

interface MetricsAdminTabProps {
  isAdmin: boolean;
}

export default function MetricsAdminTab({ isAdmin }: MetricsAdminTabProps) {
  const [metricsSettings, setMetricsSettings] = useState<MetricsSetting[]>([]);
  const [loading, setLoading] = useState(false);
  const [updating, setUpdating] = useState<Record<number, boolean>>({});
  const [message, setMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);

  // Загружаем настройки метрик
  const loadMetricsSettings = async () => {
    if (!isAdmin) return;
    
    setLoading(true);
    try {
      const res = await fetch("/api/users/metrics");
      if (!res.ok) {
        throw new Error("Failed to fetch metrics settings");
      }
      const data = await res.json();
      setMetricsSettings(data.settings || []);
    } catch (error) {
      console.error("Error loading metrics settings:", error);
      setMessage({ type: "error", text: "Ошибка загрузки настроек метрик" });
    } finally {
      setLoading(false);
    }
  };

  // Обновляем настройку метрик для пользователя
  const updateUserMetrics = async (userName: string, userId: number, enabled: boolean) => {
    setUpdating(prev => ({ ...prev, [userId]: true }));
    try {
      const encodedUser = encodeURIComponent(userName);
      const res = await fetch(`/api/users/${encodedUser}/metrics`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ enabled }),
      });

      if (!res.ok) {
        const errorData = await res.json().catch(() => ({ error: "Unknown error" }));
        throw new Error(errorData.error || "Failed to update metrics settings");
      }

      // Обновляем локальное состояние
      setMetricsSettings(prev =>
        prev.map(setting =>
          setting.user_id === userId
            ? { ...setting, enable_metrics: enabled }
            : setting
        )
      );

      setMessage({ type: "success", text: `Метрики для ${userName} ${enabled ? "включены" : "выключены"}` });
      setTimeout(() => setMessage(null), 3000);
    } catch (error) {
      console.error("Error updating metrics settings:", error);
      setMessage({
        type: "error",
        text: error instanceof Error ? error.message : "Ошибка обновления настроек метрик",
      });
      setTimeout(() => setMessage(null), 5000);
    } finally {
      setUpdating(prev => {
        const newState = { ...prev };
        delete newState[userId];
        return newState;
      });
    }
  };

  useEffect(() => {
    if (isAdmin) {
      loadMetricsSettings();
    }
  }, [isAdmin]);

  if (!isAdmin) {
    return null;
  }

  return (
    <div className="mb-8 bg-zinc-900 border border-zinc-800 rounded-xl p-6">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-xl font-bold text-white mb-2">Метрики производительности</h2>
          <p className="text-sm text-zinc-400">
            Управление настройками метрик производительности для пользователей
          </p>
        </div>
        <button
          onClick={loadMetricsSettings}
          disabled={loading}
          className="px-4 py-2 bg-zinc-700 text-white rounded-lg hover:bg-zinc-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {loading ? "Загрузка..." : "Обновить"}
        </button>
      </div>

      {/* Сообщение об успехе/ошибке */}
      {message && (
        <div
          className={`mb-4 p-3 rounded-lg ${
            message.type === "success"
              ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40"
              : "bg-red-500/20 text-red-300 border border-red-500/40"
          }`}
        >
          {message.text}
        </div>
      )}

      {loading ? (
        <div className="text-center py-8 text-zinc-400">Загрузка настроек метрик...</div>
      ) : metricsSettings.length === 0 ? (
        <div className="text-center py-8 text-zinc-400">
          Нет пользователей в системе.
        </div>
      ) : (
        <div className="space-y-2">
          {metricsSettings.map((setting) => {
            const isEnabled = Boolean(setting.enable_metrics);
            return (
              <div
                key={setting.user_id}
                className="flex items-center justify-between p-4 bg-zinc-800 rounded-lg hover:bg-zinc-750 transition-colors"
              >
                <div className="flex items-center gap-3 flex-wrap">
                  <span className="font-medium text-white">{setting.user_name}</span>
                  <span
                    className={`px-2 py-1 border rounded text-xs ${
                      isEnabled
                        ? "bg-emerald-500/20 text-emerald-300 border-emerald-400/60"
                        : "bg-red-500/20 text-red-300 border-red-500/50"
                    }`}
                  >
                    Метрики: {isEnabled ? "ВКЛ" : "ВЫКЛ"}
                  </span>
                  {setting.updated_at && (
                    <span className="text-xs text-zinc-500">
                      Обновлено: {new Date(setting.updated_at).toLocaleString("ru-RU")}
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => updateUserMetrics(setting.user_name, setting.user_id, !isEnabled)}
                    disabled={updating[setting.user_id]}
                    className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                      isEnabled
                        ? "bg-red-600 hover:bg-red-700 text-white"
                        : "bg-emerald-600 hover:bg-emerald-700 text-white"
                    } disabled:opacity-50 disabled:cursor-not-allowed`}
                  >
                    {updating[setting.user_id] ? (
                      <span className="flex items-center gap-2">
                        <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></span>
                        Обновление...
                      </span>
                    ) : isEnabled ? (
                      "Выключить"
                    ) : (
                      "Включить"
                    )}
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      <div className="mt-4 p-3 bg-zinc-800/50 rounded-lg border border-zinc-700">
        <p className="text-xs text-zinc-400">
          <strong>Примечание:</strong> Когда метрики включены, пользователь будет получать статистику производительности
          сразу после каждого сигнала. Метрики включают время выполнения этапов: детект, получение данных пользователя,
          сохранение в БД, форматирование сообщения, генерация графика и отправка в Telegram.
        </p>
      </div>
    </div>
  );
}

