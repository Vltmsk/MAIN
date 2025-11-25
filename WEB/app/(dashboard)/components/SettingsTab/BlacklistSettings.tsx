"use client";

import { useState } from "react";

interface BlacklistSettingsProps {
  blacklist: string[];
  onBlacklistChange: (blacklist: string[]) => void;
}

export default function BlacklistSettings({ blacklist, onBlacklistChange }: BlacklistSettingsProps) {
  const [newSymbol, setNewSymbol] = useState("");

  const handleAdd = () => {
    if (!newSymbol.trim()) return;
    const symbol = newSymbol.trim().toUpperCase();
    if (!blacklist.includes(symbol)) {
      onBlacklistChange([...blacklist, symbol]);
      setNewSymbol("");
    }
  };

  const handleRemove = (symbol: string) => {
    onBlacklistChange(blacklist.filter((s) => s !== symbol));
  };

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6">
      <div className="flex items-center gap-2 mb-1">
        <h2 className="text-xl font-bold text-white">Чёрный список монет</h2>
      </div>
      <p className="text-sm text-zinc-400 mb-6">
        Исключите монеты из детектирования. Монеты из чёрного списка не будут отслеживаться системой.
      </p>
      <div className="space-y-4">
        <div className="flex gap-3">
          <input
            type="text"
            value={newSymbol}
            onChange={(e) => setNewSymbol(e.target.value.toUpperCase())}
            placeholder="Символ монеты (например, BTC или ETHUSDT)"
            className="flex-1 px-4 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent"
          />
          <button
            onClick={handleAdd}
            className="px-4 py-2 bg-emerald-500 hover:bg-emerald-600 text-white font-medium rounded-lg transition-colors"
          >
            + Добавить
          </button>
        </div>
        {blacklist.length > 0 ? (
          <div className="flex flex-wrap gap-2">
            {blacklist.map((symbol) => (
              <div
                key={symbol}
                className="flex items-center gap-2 px-3 py-1 bg-zinc-800 rounded-lg"
              >
                <span className="text-white">{symbol}</span>
                <button
                  onClick={() => handleRemove(symbol)}
                  className="text-zinc-400 hover:text-red-400 transition-colors"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-zinc-500 text-sm">Черный список пуст</p>
        )}
      </div>
    </div>
  );
}

