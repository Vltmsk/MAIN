"use client";

interface SettingsNavigationProps {
  activeSection: "telegram" | "format" | "charts" | "spikes" | "blacklist" | "strategies";
  onSectionChange: (section: "telegram" | "format" | "charts" | "spikes" | "blacklist" | "strategies") => void;
}

export default function SettingsNavigation({ activeSection, onSectionChange }: SettingsNavigationProps) {
  return (
    <div className="mb-6">
      <div className="flex flex-wrap gap-3 bg-zinc-900 border border-zinc-800 rounded-xl p-2">
        <button
          onClick={() => onSectionChange("spikes")}
          className={`flex-1 min-w-[200px] px-6 py-3 rounded-lg font-medium smooth-transition ripple ${
            activeSection === "spikes"
              ? "bg-zinc-700 text-white"
              : "text-zinc-400 hover:text-white hover:bg-zinc-800/50"
          }`}
        >
          Настройки прострелов
        </button>
        <button
          onClick={() => onSectionChange("telegram")}
          className={`flex-1 min-w-[200px] px-6 py-3 rounded-lg font-medium smooth-transition ripple ${
            activeSection === "telegram"
              ? "bg-zinc-700 text-white"
              : "text-zinc-400 hover:text-white hover:bg-zinc-800/50"
          }`}
        >
          Настройка Телеграм
        </button>
        <button
          onClick={() => onSectionChange("format")}
          className={`flex-1 min-w-[200px] px-6 py-3 rounded-lg font-medium smooth-transition ripple ${
            activeSection === "format"
              ? "bg-zinc-700 text-white"
              : "text-zinc-400 hover:text-white hover:bg-zinc-800/50"
          }`}
        >
          Формат сообщений
        </button>
        <button
          onClick={() => onSectionChange("charts")}
          className={`flex-1 min-w-[200px] px-6 py-3 rounded-lg font-medium smooth-transition ripple ${
            activeSection === "charts"
              ? "bg-zinc-700 text-white"
              : "text-zinc-400 hover:text-white hover:bg-zinc-800/50"
          }`}
        >
          Отправка графиков
        </button>
        <button
          onClick={() => onSectionChange("blacklist")}
          className={`flex-1 min-w-[200px] px-6 py-3 rounded-lg font-medium smooth-transition ripple ${
            activeSection === "blacklist"
              ? "bg-zinc-700 text-white"
              : "text-zinc-400 hover:text-white hover:bg-zinc-800/50"
          }`}
        >
          Чёрный список
        </button>
        <button
          onClick={() => onSectionChange("strategies")}
          className={`flex-1 min-w-[200px] px-6 py-3 rounded-lg font-medium smooth-transition ripple ${
            activeSection === "strategies"
              ? "bg-zinc-700 text-white"
              : "text-zinc-400 hover:text-white hover:bg-zinc-800/50"
          }`}
        >
          Стратегии
        </button>
      </div>
    </div>
  );
}

