"use client";

import { AdminUserSettings } from "./types";
import ExchangeSettingsEditor from "./ExchangeSettingsEditor";

interface UserSettingsEditorProps {
  userSettings: AdminUserSettings;
  onSave: () => void;
  onClose: () => void;
  loading: boolean;
  exchangeFilters: Record<string, boolean>;
  pairSettings: Record<string, { enabled: boolean; delta: string; volume: string; shadow: string }>;
  onExchangeFiltersChange: (filters: Record<string, boolean>) => void;
  onPairSettingsChange: (settings: Record<string, { enabled: boolean; delta: string; volume: string; shadow: string }>) => void;
  expandedExchanges: Record<string, boolean>;
  onExpandedExchangesChange: (expanded: Record<string, boolean>) => void;
  onUserSettingsChange: (settings: AdminUserSettings) => void;
}

export default function UserSettingsEditor({
  userSettings,
  onSave,
  onClose,
  loading,
  exchangeFilters,
  pairSettings,
  onExchangeFiltersChange,
  onPairSettingsChange,
  expandedExchanges,
  onExpandedExchangesChange,
  onUserSettingsChange,
}: UserSettingsEditorProps) {
  return (
    <div className="mb-8 bg-zinc-900 border border-zinc-800 rounded-xl p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-xl font-bold text-white">Настройки: {userSettings.user}</h2>
        <button
          onClick={onClose}
          className="px-3 py-1 bg-zinc-700 text-white rounded hover:bg-zinc-600 transition-colors"
        >
          Закрыть
        </button>
      </div>

      <div className="space-y-4">
        {/* Telegram */}
        <div className="border-t border-zinc-700 pt-4">
          <h3 className="text-lg font-semibold text-white mb-3">Telegram</h3>
          <div className="grid md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm text-zinc-400 mb-1">Chat ID</label>
              <input
                type="text"
                value={userSettings.chat_id || ""}
                onChange={(e) =>
                  onUserSettingsChange({
                    ...userSettings,
                    chat_id: e.target.value,
                  })
                }
                placeholder="Не настроен"
                className="w-full px-4 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div>
              <label className="block text-sm text-zinc-400 mb-1">Bot Token</label>
              <input
                type="text"
                value={userSettings.tg_token || ""}
                onChange={(e) =>
                  onUserSettingsChange({
                    ...userSettings,
                    tg_token: e.target.value,
                  })
                }
                placeholder="Не настроен"
                className="w-full px-4 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
          </div>
        </div>

        {/* Настройки бирж */}
        <div className="border-t border-zinc-700 pt-4">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-lg font-semibold text-white">Фильтры по биржам</h3>
            <button
              onClick={onSave}
              disabled={loading}
              className="px-4 py-2 bg-gradient-to-r from-emerald-500 to-emerald-600 hover:from-emerald-600 hover:to-emerald-700 text-white text-sm font-medium rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? "Сохранение..." : "Сохранить изменения"}
            </button>
          </div>
          <ExchangeSettingsEditor
            exchangeFilters={exchangeFilters}
            pairSettings={pairSettings}
            onExchangeFiltersChange={onExchangeFiltersChange}
            onPairSettingsChange={onPairSettingsChange}
            expandedExchanges={expandedExchanges}
            onExpandedExchangesChange={onExpandedExchangesChange}
          />
        </div>
      </div>
    </div>
  );
}

