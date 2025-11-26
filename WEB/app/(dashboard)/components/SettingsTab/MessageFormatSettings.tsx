"use client";

import MessageTemplateEditor from "./components/MessageTemplateEditor";

interface MessageFormatSettingsProps {
  template: string;
  timezone: string;
  onTemplateChange: (template: string) => void;
  onTimezoneChange: (timezone: string) => void;
  isUserEditingRef?: React.MutableRefObject<boolean>;
  onSave: () => Promise<void>;
  saving?: boolean;
  setSaveMessage?: (message: { type: "success" | "error"; text: string } | null) => void;
}

export default function MessageFormatSettings({
  template,
  timezone,
  onTemplateChange,
  onTimezoneChange,
  isUserEditingRef,
  onSave,
  saving = false,
  setSaveMessage,
}: MessageFormatSettingsProps) {
  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6">
      <div className="flex items-center justify-between mb-1">
        <div className="flex items-center gap-2">
          <h2 className="text-xl font-bold text-white">Формат отправки детекта</h2>
        </div>
      </div>
      <p className="text-sm text-zinc-400 mb-6">
        Настройте формат сообщений, которые будут отправляться в Telegram при обнаружении стрелы. Используйте вставки ниже для добавления данных о детекте (дельта, объём, биржа и т.д.).
      </p>
      <MessageTemplateEditor
        template={template}
        timezone={timezone}
        onChange={onTemplateChange}
        onTimezoneChange={onTimezoneChange}
        isUserEditingRef={isUserEditingRef}
      />
      {/* Кнопка сохранения */}
      <div className="mt-6">
        <button
          onClick={async () => {
            try {
              await onSave();
            } catch (error) {
              // Ошибка будет обработана в onSave, но на всякий случай показываем уведомление
              if (setSaveMessage) {
                setSaveMessage({
                  type: "error",
                  text: error instanceof Error ? error.message : "Ошибка при сохранении формата сообщений"
                });
              } else {
                console.error("Ошибка при сохранении формата сообщений:", error);
              }
            }
          }}
          disabled={saving}
          className="w-full px-4 py-2 bg-gradient-to-r from-emerald-500 to-emerald-600 hover:from-emerald-600 hover:to-emerald-700 text-white font-medium rounded-lg smooth-transition ripple hover-glow shadow-emerald disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {saving ? "Сохранение..." : "Сохранить формат сообщений"}
        </button>
      </div>
    </div>
  );
}

