"use client";

import MessageTemplateEditor from "./components/MessageTemplateEditor";

interface MessageFormatSettingsProps {
  template: string;
  timezone: string;
  onTemplateChange: (template: string) => void;
  onTimezoneChange: (timezone: string) => void;
  isUserEditingRef?: React.MutableRefObject<boolean>;
}

export default function MessageFormatSettings({
  template,
  timezone,
  onTemplateChange,
  onTimezoneChange,
  isUserEditingRef,
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
    </div>
  );
}

