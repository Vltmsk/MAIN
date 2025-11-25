"use client";

import { formatNumberCompact } from "../utils/formatters";

interface PairSettings {
  enabled: boolean;
  delta: string;
  volume: string;
  shadow: string;
  sendChart?: boolean;
}

interface PairSettingsEditorProps {
  pair: string;
  pairKey: string; // например "binance_spot_BTC"
  settings: PairSettings;
  onChange: (pairKey: string, settings: PairSettings) => void;
}

export default function PairSettingsEditor({
  pair,
  pairKey,
  settings,
  onChange,
}: PairSettingsEditorProps) {
  const handleChange = (field: keyof PairSettings, value: boolean | string) => {
    onChange(pairKey, {
      ...settings,
      [field]: value,
    });
  };

  return (
    <div className="bg-zinc-800/50 rounded-lg p-4 space-y-3">
      <div className="flex items-center justify-between mb-3">
        <div>
          <h3 className="text-white font-medium">{pair}</h3>
          <p className="text-xs text-zinc-400">Торговая пара</p>
        </div>
        <div
          className={`w-12 h-6 rounded-full transition-colors cursor-pointer ${
            settings.enabled ? "bg-emerald-500" : "bg-zinc-600"
          }`}
          onClick={() => handleChange("enabled", !settings.enabled)}
        >
          <div
            className={`w-5 h-5 bg-white rounded-full transition-transform mt-0.5 ${
              settings.enabled ? "translate-x-6" : "translate-x-1"
            }`}
          />
        </div>
      </div>

      <div className="grid grid-cols-3 gap-3">
        <div>
          <label className="block text-xs text-zinc-400 mb-1">Дельта (%)</label>
          <input
            type="number"
            min="0"
            step="any"
            value={settings.delta}
            onChange={(e) => {
              const value = e.target.value;
              if (value === "" || !value.startsWith("-")) {
                if (value === "") {
                  handleChange("delta", value);
                } else {
                  const numValue = parseFloat(value);
                  if (numValue >= 0 && !isNaN(numValue)) {
                    handleChange("delta", value);
                  }
                }
              }
            }}
            className="w-full px-2 py-1 bg-zinc-700 border border-zinc-600 rounded text-white text-xs focus:outline-none focus:ring-1 focus:ring-emerald-500"
            placeholder="0"
          />
        </div>

        <div>
          <label className="block text-xs text-zinc-400 mb-1">Объём (USDT)</label>
          <input
            type="number"
            min="0"
            step="any"
            value={settings.volume}
            onChange={(e) => {
              const value = e.target.value;
              if (value === "" || !value.startsWith("-")) {
                if (value === "") {
                  handleChange("volume", value);
                } else {
                  const numValue = parseFloat(value);
                  if (numValue >= 0 && !isNaN(numValue)) {
                    handleChange("volume", value);
                  }
                }
              }
            }}
            className="w-full px-2 py-1 bg-zinc-700 border border-zinc-600 rounded text-white text-xs focus:outline-none focus:ring-1 focus:ring-emerald-500"
            placeholder="0"
          />
        </div>

        <div>
          <label className="block text-xs text-zinc-400 mb-1">Тень (%)</label>
          <input
            type="number"
            min="0"
            step="any"
            value={settings.shadow}
            onChange={(e) => {
              const value = e.target.value;
              if (value === "" || !value.startsWith("-")) {
                if (value === "") {
                  handleChange("shadow", value);
                } else {
                  const numValue = parseFloat(value);
                  if (numValue >= 0 && !isNaN(numValue)) {
                    handleChange("shadow", value);
                  }
                }
              }
            }}
            className="w-full px-2 py-1 bg-zinc-700 border border-zinc-600 rounded text-white text-xs focus:outline-none focus:ring-1 focus:ring-emerald-500"
            placeholder="0"
          />
        </div>
      </div>

      {settings.sendChart !== undefined && (
        <div className="flex items-center gap-2 mt-3">
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={settings.sendChart}
              onChange={(e) => handleChange("sendChart", e.target.checked)}
              className="w-4 h-4 text-emerald-600 bg-zinc-700 border-zinc-600 rounded focus:ring-emerald-500 focus:ring-2"
            />
            <span className="text-xs text-zinc-300">Отправлять график</span>
          </label>
        </div>
      )}
    </div>
  );
}

