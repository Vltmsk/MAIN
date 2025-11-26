"use client";

import { useState, useMemo } from "react";
import { ConditionalTemplate } from "./types";

interface StrategiesTreeViewProps {
  strategies: ConditionalTemplate[];
  selectedStrategyIndex: number | null;
  selectedStrategies: Set<number>;
  filterText: string;
  onStrategySelect: (index: number) => void;
  onStrategyToggle: (index: number) => void;
  onFilterChange: (text: string) => void;
  onStrategyCommentChange?: (index: number, comment: string) => void;
  generateTemplateDescription: (template: ConditionalTemplate) => string;
}

export default function StrategiesTreeView({
  strategies,
  selectedStrategyIndex,
  selectedStrategies,
  filterText,
  onStrategySelect,
  onStrategyToggle,
  onFilterChange,
  onStrategyCommentChange,
  generateTemplateDescription,
}: StrategiesTreeViewProps) {
  // Фильтрация стратегий
  const filteredStrategies = useMemo(() => {
    if (!filterText.trim()) {
      return strategies;
    }
    
    const searchLower = filterText.toLowerCase();
    return strategies.filter((strategy, index) => {
      const name = strategy.name?.toLowerCase() || "";
      const description = generateTemplateDescription(strategy).toLowerCase();
      const number = `#${index + 1}`.toLowerCase();
      
      return (
        name.includes(searchLower) ||
        description.includes(searchLower) ||
        number.includes(searchLower)
      );
    });
  }, [strategies, filterText, generateTemplateDescription]);

  return (
    <div className="h-full flex flex-col bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden">
      {/* Заголовок */}
      <div className="px-4 py-3 border-b border-zinc-800 flex items-center gap-2">
        <svg
          className="w-5 h-5 text-emerald-500"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"
          />
        </svg>
        <h2 className="text-lg font-bold text-white">Стратегии</h2>
      </div>

      {/* Фильтр */}
      <div className="px-4 py-3 border-b border-zinc-800">
        <div className="relative">
          <svg
            className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-zinc-400"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
            />
          </svg>
          <input
            type="text"
            value={filterText}
            onChange={(e) => onFilterChange(e.target.value)}
            placeholder="Поиск стратегий..."
            className="w-full pl-10 pr-4 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white text-sm placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-emerald-500"
          />
        </div>
      </div>

      {/* Дерево стратегий */}
      <div className="flex-1 overflow-y-auto">
        {filteredStrategies.length === 0 ? (
          <div className="px-4 py-8 text-center">
            <p className="text-sm text-zinc-400">
              {filterText.trim() ? "Стратегии не найдены" : "Нет стратегий"}
            </p>
          </div>
        ) : (
          <div className="p-2 space-y-1">
            {filteredStrategies.map((strategy, originalIndex) => {
              // Находим оригинальный индекс в полном списке
              const actualIndex = strategies.findIndex((s) => s === strategy);
              const isSelected = selectedStrategyIndex === actualIndex;
              const isChecked = selectedStrategies.has(actualIndex);
              const isEnabled = strategy.enabled !== false;
              const hasName = !!strategy.name;

              return (
                <div
                  key={actualIndex}
                  onClick={() => onStrategySelect(actualIndex)}
                  className={`
                    relative flex items-start gap-2 p-3 rounded-lg cursor-pointer transition-all
                    ${
                      isSelected
                        ? "bg-blue-600/20 border border-blue-500/50"
                        : "bg-zinc-800/50 border border-zinc-700/50 hover:bg-zinc-800 hover:border-zinc-600"
                    }
                    ${!isEnabled ? "opacity-60" : ""}
                  `}
                >
                  {/* Чекбокс для массового выбора */}
                  <input
                    type="checkbox"
                    checked={isChecked}
                    onChange={(e) => {
                      e.stopPropagation();
                      onStrategyToggle(actualIndex);
                    }}
                    onClick={(e) => e.stopPropagation()}
                    className="mt-1 w-4 h-4 text-emerald-600 bg-zinc-700 border-zinc-600 rounded focus:ring-emerald-500 focus:ring-2 cursor-pointer"
                  />

                  {/* Контент стратегии */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-xs font-medium text-zinc-400">
                        #{actualIndex + 1}
                      </span>
                      {isEnabled && (
                        <svg
                          className="w-4 h-4 text-emerald-500 flex-shrink-0"
                          fill="currentColor"
                          viewBox="0 0 20 20"
                        >
                          <path
                            fillRule="evenodd"
                            d="M11.3 1.046A1 1 0 0112 2v5h4a1 1 0 01.82 1.573l-7 10A1 1 0 018 18v-5H4a1 1 0 01-.82-1.573l7-10a1 1 0 011.12-.38z"
                            clipRule="evenodd"
                          />
                        </svg>
                      )}
                      <span
                        className={`text-sm font-medium truncate ${
                          isSelected ? "text-white" : "text-zinc-200"
                        }`}
                      >
                        {strategy.name || `Стратегия #${actualIndex + 1}`}
                      </span>
                      {!hasName && (
                        <span className="text-xs text-amber-500">(без названия)</span>
                      )}
                    </div>
                    <p className="text-xs text-zinc-400 line-clamp-2">
                      {generateTemplateDescription(strategy) || "Нет условий"}
                    </p>
                  </div>

                  {/* Индикатор статуса */}
                  <div className="flex flex-col items-center gap-1 flex-shrink-0">
                    {isEnabled ? (
                      <div className="w-2 h-2 rounded-full bg-emerald-500" />
                    ) : (
                      <div className="w-2 h-2 rounded-full bg-zinc-600" />
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Дополнительное поле для комментария (опционально) */}
      {selectedStrategyIndex !== null && (
        <div className="px-4 py-3 border-t border-zinc-800">
          <textarea
            value={strategies[selectedStrategyIndex]?.comment || ""}
            onChange={(e) => {
              if (onStrategyCommentChange) {
                onStrategyCommentChange(selectedStrategyIndex, e.target.value);
              }
            }}
            placeholder="Дополнительный комментарий к стратегии, параметр не обязателен"
            className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white text-xs placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-emerald-500 resize-none"
            rows={2}
          />
        </div>
      )}
    </div>
  );
}

