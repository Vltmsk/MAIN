"use client";

import { ConditionalTemplate } from "../types";

interface ConditionEditorProps {
  condition: ConditionalTemplate["conditions"][0];
  index: number;
  onChange: (index: number, condition: ConditionalTemplate["conditions"][0]) => void;
  onDelete: (index: number) => void;
  canDelete: boolean;
  generateDescription?: (template: ConditionalTemplate) => string;
}

export default function ConditionEditor({
  condition,
  index,
  onChange,
  onDelete,
  canDelete,
}: ConditionEditorProps) {
  const handleChange = (updates: Partial<ConditionalTemplate["conditions"][0]>) => {
    onChange(index, { ...condition, ...updates });
  };

  const handleTypeChange = (newType: ConditionalTemplate["conditions"][0]["type"]) => {
    // Очищаем значения при смене типа
    const newCondition: ConditionalTemplate["conditions"][0] = { type: newType };

    if (newType === "series") {
      newCondition.count = 2;
      newCondition.timeWindowSeconds = 300;
    } else if (newType === "delta" || newType === "wick_pct") {
      newCondition.valueMin = 0;
      newCondition.valueMax = null;
    } else if (newType === "symbol") {
      newCondition.symbol = "";
    } else if (newType === "exchange_market") {
      newCondition.exchange_market = "binance_spot";
    } else if (newType === "direction") {
      newCondition.direction = "up";
    } else {
      newCondition.value = 0;
    }

    onChange(index, newCondition);
  };

  return (
    <div className="flex items-start gap-2 mb-3">
      <div className="flex-1">
        <select
          value={condition.type}
          onChange={(e) => handleTypeChange(e.target.value as ConditionalTemplate["conditions"][0]["type"])}
          className="w-48 px-3 py-2 bg-zinc-700 border border-zinc-600 rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
        >
          <option value="volume">Объём (USDT)</option>
          <option value="delta">Дельта (%)</option>
          <option value="wick_pct">Тень свечи (%)</option>
          <option value="series">Серия стрел</option>
          <option value="symbol">Символ (монета)</option>
          <option value="exchange_market">Биржа и тип рынка</option>
          <option value="direction">Направление стрелы</option>
        </select>
      </div>

      {/* Рендеринг полей ввода в зависимости от типа условия */}
      {condition.type === "series" && (
        <>
          <div className="flex-1">
            <label className="block text-xs text-zinc-400 mb-1">Количество стрел (≥)</label>
            <input
              type="number"
              min="2"
              step="1"
              value={condition.count || ""}
              onChange={(e) => {
                const val = e.target.value === "" ? 2 : parseInt(e.target.value);
                handleChange({ count: isNaN(val) ? 2 : Math.max(2, val) });
              }}
              className="w-full px-3 py-2.5 bg-zinc-700 border border-zinc-600 rounded-lg text-white text-sm text-center focus:outline-none focus:ring-2 focus:ring-emerald-500"
              placeholder="2"
            />
          </div>
          <div className="flex-1">
            <label className="block text-xs text-zinc-400 mb-1">Окно (секунды)</label>
            <input
              type="number"
              min="60"
              step="60"
              value={condition.timeWindowSeconds || ""}
              onChange={(e) => {
                const val = e.target.value === "" ? 300 : parseInt(e.target.value);
                handleChange({ timeWindowSeconds: isNaN(val) ? 300 : Math.max(60, val) });
              }}
              className="w-full px-3 py-2.5 bg-zinc-700 border border-zinc-600 rounded-lg text-white text-sm text-center focus:outline-none focus:ring-2 focus:ring-emerald-500"
              placeholder="300"
            />
          </div>
        </>
      )}

      {condition.type === "delta" && (
        <div className="flex-1">
          <label className="block text-xs text-zinc-400 mb-1">Дельта от (%)</label>
          <input
            type="number"
            step="0.1"
            min="0"
            value={condition.valueMin !== undefined ? condition.valueMin : condition.value !== undefined ? condition.value : ""}
            onChange={(e) => {
              const val = e.target.value === "" ? 0 : parseFloat(e.target.value);
              handleChange({ valueMin: isNaN(val) ? 0 : val, valueMax: null });
            }}
            className="w-full px-3 py-2.5 bg-zinc-700 border border-zinc-600 rounded-lg text-white text-sm text-center focus:outline-none focus:ring-2 focus:ring-emerald-500"
            placeholder="0"
          />
        </div>
      )}

      {condition.type === "symbol" && (
        <div className="flex-1">
          <label className="block text-xs text-zinc-400 mb-1">Символ (монета)</label>
          <input
            type="text"
            value={condition.symbol || ""}
            onChange={(e) => handleChange({ symbol: e.target.value.toUpperCase().trim() })}
            className="w-40 px-3 py-2 bg-zinc-700 border border-zinc-600 rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
            placeholder="ETH, BTC, ADA..."
          />
        </div>
      )}

      {condition.type === "wick_pct" && (
        <div className="flex-1">
          <label className="block text-xs text-zinc-400 mb-2">Диапазон (%)</label>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="block text-xs text-zinc-500 mb-1">От</label>
              <input
                type="number"
                step="0.1"
                min="0"
                max="100"
                value={condition.valueMin !== undefined ? condition.valueMin : ""}
                onChange={(e) => {
                  const val = e.target.value === "" ? 0 : parseFloat(e.target.value);
                  handleChange({ valueMin: isNaN(val) ? 0 : Math.max(0, Math.min(100, val)) });
                }}
                className="w-full px-3 py-2.5 bg-zinc-700 border border-zinc-600 rounded-lg text-white text-sm text-center focus:outline-none focus:ring-2 focus:ring-emerald-500"
                placeholder="0"
              />
            </div>
            <div>
              <label className="block text-xs text-zinc-500 mb-1">До</label>
              <input
                type="text"
                value={condition.valueMax === null || condition.valueMax === undefined ? "∞" : String(condition.valueMax)}
                onChange={(e) => {
                  if (e.target.value === "∞" || e.target.value === "" || e.target.value.trim() === "") {
                    handleChange({ valueMax: null });
                  } else {
                    const numValue = parseFloat(e.target.value);
                    if (!isNaN(numValue)) {
                      handleChange({ valueMax: Math.max(0, Math.min(100, numValue)) });
                    } else {
                      handleChange({ valueMax: null });
                    }
                  }
                }}
                className="w-full px-3 py-2.5 bg-zinc-700 border border-zinc-600 rounded-lg text-white text-sm text-center focus:outline-none focus:ring-2 focus:ring-emerald-500"
                placeholder="∞"
              />
            </div>
          </div>
        </div>
      )}

      {condition.type === "exchange_market" && (
        <div className="flex-1">
          <label className="block text-xs text-zinc-400 mb-1">Биржа и тип рынка</label>
          <select
            value={condition.exchange_market || "binance_spot"}
            onChange={(e) => handleChange({ exchange_market: e.target.value })}
            className="w-full px-3 py-2 bg-zinc-700 border border-zinc-600 rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
          >
            <option value="binance_spot">Binance Spot</option>
            <option value="binance_futures">Binance Futures</option>
            <option value="bybit_spot">Bybit Spot</option>
            <option value="bybit_futures">Bybit Futures</option>
            <option value="bitget_spot">Bitget Spot</option>
            <option value="bitget_futures">Bitget Futures</option>
            <option value="gate_spot">Gate Spot</option>
            <option value="gate_futures">Gate Futures</option>
            <option value="hyperliquid_spot">Hyperliquid Spot</option>
            <option value="hyperliquid_futures">Hyperliquid Futures</option>
          </select>
        </div>
      )}

      {condition.type === "direction" && (
        <div className="flex-1">
          <label className="block text-xs text-zinc-400 mb-1">Направление стрелы</label>
          <select
            value={condition.direction || "up"}
            onChange={(e) => handleChange({ direction: e.target.value as "up" | "down" })}
            className="w-40 px-3 py-2 bg-zinc-700 border border-zinc-600 rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
          >
            <option value="up">Вверх ⬆️</option>
            <option value="down">Вниз ⬇️</option>
          </select>
        </div>
      )}

      {(condition.type === "volume" || !["series", "delta", "symbol", "wick_pct", "exchange_market", "direction"].includes(condition.type)) && (
        <div className="w-full md:w-auto md:min-w-[220px]">
          <label className="block text-xs text-zinc-400 mb-1">Значение (≥)</label>
          <input
            type="number"
            step="0.01"
            value={condition.value || ""}
            onChange={(e) => {
              const val = e.target.value === "" ? 0 : parseFloat(e.target.value);
              handleChange({ value: isNaN(val) ? 0 : val });
            }}
            className="w-full px-3 py-2.5 bg-zinc-700 border border-zinc-600 rounded-lg text-white text-sm text-center focus:outline-none focus:ring-2 focus:ring-emerald-500"
            placeholder="0"
          />
        </div>
      )}

      {canDelete && (
        <button
          onClick={() => onDelete(index)}
          className="px-2 py-2 bg-red-600/50 hover:bg-red-600 text-white text-xs font-medium rounded transition-colors"
          title="Удалить условие"
        >
          ×
        </button>
      )}
    </div>
  );
}

