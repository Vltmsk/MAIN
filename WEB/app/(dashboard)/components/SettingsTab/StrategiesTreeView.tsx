"use client";

import { ConditionalTemplate } from "./types";

interface StrategiesTreeViewProps {
  strategies: ConditionalTemplate[];
  selectedStrategyIndex: number | null;
  selectedStrategies: Set<number>;
  onStrategySelect: (index: number) => void;
  onStrategyToggle: (index: number) => void;
  generateTemplateDescription: (template: ConditionalTemplate) => string;
}

export default function StrategiesTreeView({
  strategies,
  selectedStrategyIndex,
  selectedStrategies,
  onStrategySelect,
  onStrategyToggle,
  generateTemplateDescription,
}: StrategiesTreeViewProps) {

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

      {/* Дерево стратегий */}
      <div className="flex-1 overflow-y-auto">
        {strategies.length === 0 ? (
          <div className="px-4 py-8 text-center">
            <p className="text-sm text-zinc-400">
              Нет стратегий
            </p>
          </div>
        ) : (
          <div className="p-2 space-y-1">
            {strategies.map((strategy, actualIndex) => {
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
                        ? "bg-blue-600/20 border-2 border-blue-500/50"
                        : isEnabled
                        ? "bg-zinc-800/50 border-2 border-emerald-500/50 hover:bg-zinc-800 hover:border-emerald-500/70"
                        : "bg-zinc-800/50 border-2 border-red-500/50 hover:bg-zinc-800 hover:border-red-500/70"
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

    </div>
  );
}

