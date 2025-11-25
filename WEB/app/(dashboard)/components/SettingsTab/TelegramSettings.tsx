"use client";

import ChatIdHelp from "@/components/ChatIdHelp";

interface TelegramSettingsProps {
  chatId: string;
  botToken: string;
  isConfigured: boolean;
  isEditing: boolean;
  chatIdError: string;
  botTokenError: string;
  testing: boolean;
  onChatIdChange: (chatId: string) => void;
  onBotTokenChange: (token: string) => void;
  onTest: () => Promise<void>;
  onToggleEdit: () => void;
  onSave: () => Promise<void>;
  saving: boolean;
}

export default function TelegramSettings({
  chatId,
  botToken,
  isConfigured,
  isEditing,
  chatIdError,
  botTokenError,
  testing,
  onChatIdChange,
  onBotTokenChange,
  onTest,
  onToggleEdit,
  onSave,
  saving,
}: TelegramSettingsProps) {
  if (isConfigured && !isEditing) {
    return (
      <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4">
        <div className="flex items-center gap-2 mb-1">
          <h2 className="text-xl font-bold text-white">Интеграция с Telegram</h2>
        </div>
        <p className="text-sm text-zinc-400 mb-4">
          Telegram настроен. Вы будете получать уведомления о найденных стрелах.
        </p>
        <div className="flex gap-3">
          <button
            onClick={onTest}
            disabled={testing || !botToken || !chatId}
            className="flex-1 px-4 py-2 glass hover:bg-zinc-700/50 text-white font-medium rounded-lg smooth-transition ripple hover-glow disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
          >
            {testing ? "Отправка..." : (
              <>
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                </svg>
                Отправить тест
              </>
            )}
          </button>
          <button
            onClick={onToggleEdit}
            className="flex-1 px-4 py-2 bg-gradient-to-r from-emerald-500 to-emerald-600 hover:from-emerald-600 hover:to-emerald-700 text-white font-medium rounded-lg smooth-transition ripple hover-glow shadow-emerald flex items-center justify-center gap-2"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
            </svg>
            Изменить
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6">
      <div className="flex items-center gap-2 mb-1">
        <h2 className="text-xl font-bold text-white">Интеграция с Telegram</h2>
      </div>
      <p className="text-sm text-zinc-400 mb-6">
        Настройте уведомления через Telegram бота. Укажите Chat ID и Bot Token для получения сообщений о найденных стрелах.
      </p>
      <div className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-zinc-300 mb-2">Chat ID</label>
          <input
            type="text"
            value={chatId}
            onChange={(e) => onChatIdChange(e.target.value)}
            placeholder="123456789"
            className={`w-full px-4 py-2 bg-zinc-800 border rounded-lg text-white placeholder-zinc-500 focus:outline-none focus:ring-2 focus:border-transparent ${
              chatIdError
                ? "border-red-500 focus:ring-red-500"
                : "border-zinc-700 focus:ring-emerald-500"
            }`}
          />
          {chatIdError ? (
            <div className="mt-1">
              <p className="text-xs text-red-400">{chatIdError}</p>
              <ChatIdHelp variant="compact" />
            </div>
          ) : (
            <ChatIdHelp />
          )}
        </div>
        <div>
          <label className="block text-sm font-medium text-zinc-300 mb-2">Bot Token</label>
          <input
            type="password"
            value={botToken}
            onChange={(e) => onBotTokenChange(e.target.value)}
            placeholder="1234567890:ABCdefGHIjkIMNOpqrsTUVwxyz"
            className={`w-full px-4 py-2 bg-zinc-800 border rounded-lg text-white placeholder-zinc-500 focus:outline-none focus:ring-2 focus:border-transparent ${
              botTokenError
                ? "border-red-500 focus:ring-red-500"
                : "border-zinc-700 focus:ring-emerald-500"
            }`}
          />
          {botTokenError ? (
            <p className="mt-1 text-xs text-red-400">{botTokenError}</p>
          ) : (
            <div className="mt-1">
              <ChatIdHelp showBotTokenWarning={true} forBotToken={true} />
            </div>
          )}
        </div>
        <div className="flex gap-3 pt-2">
          <button
            onClick={onSave}
            disabled={saving || !!chatIdError || !!botTokenError}
            className="flex-1 px-4 py-2 bg-gradient-to-r from-emerald-500 to-emerald-600 hover:from-emerald-600 hover:to-emerald-700 text-white font-medium rounded-lg smooth-transition ripple hover-glow shadow-emerald disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {saving ? "Сохранение..." : "Сохранить"}
          </button>
          <button
            onClick={onTest}
            disabled={testing || saving || !botToken || !chatId || !!chatIdError || !!botTokenError}
            className="flex-1 px-4 py-2 glass hover:bg-zinc-700/50 text-white font-medium rounded-lg smooth-transition ripple hover-glow disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
          >
            {testing ? "Отправка..." : (
              <>
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                </svg>
                Отправить тест
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

