"use client";

import { ConditionalTemplate } from "../types";
import ConditionEditor from "./ConditionEditor";

interface StrategyEditorProps {
  strategy: ConditionalTemplate;
  index: number;
  onChange: (index: number, strategy: ConditionalTemplate) => void;
  onDelete: (index: number) => void;
  validationError?: { hasError: boolean; missingFields: string[]; message: string };
  generateTemplateDescription: (template: ConditionalTemplate) => string;
  convertToTechnicalKeys: (template: string) => string;
  convertToFriendlyNames: (template: string) => string;
}

export default function StrategyEditor({
  strategy,
  index,
  onChange,
  onDelete,
  validationError,
  generateTemplateDescription,
  convertToTechnicalKeys,
  convertToFriendlyNames,
}: StrategyEditorProps) {
  const handleChange = (updates: Partial<ConditionalTemplate>) => {
    const updated = { ...strategy, ...updates };
    if (updates.conditions !== undefined) {
      updated.description = generateTemplateDescription(updated);
    }
    onChange(index, updated);
  };

  const handleConditionChange = (conditionIndex: number, condition: ConditionalTemplate["conditions"][0]) => {
    const newConditions = [...strategy.conditions];
    newConditions[conditionIndex] = condition;
    handleChange({ conditions: newConditions });
  };

  const handleConditionDelete = (conditionIndex: number) => {
    const newConditions = strategy.conditions.filter((_, i) => i !== conditionIndex);
    handleChange({ conditions: newConditions });
  };

  const addCondition = () => {
    handleChange({
      conditions: [...strategy.conditions, { type: "volume", value: 0 }],
    });
  };

  return (
    <div className={`bg-zinc-800 border rounded-lg p-4 ${strategy.enabled !== false ? 'border-zinc-700' : 'border-zinc-600/50 opacity-75'}`}>
      <div className="flex items-start justify-between mb-3">
        <div className="flex-1">
          <input
            type="text"
            value={strategy.name || ""}
            onChange={(e) => handleChange({ name: e.target.value.trim() || undefined })}
            placeholder={`Стратегия #${index + 1}`}
            className="w-full px-3 py-1.5 bg-zinc-700 border border-zinc-600 rounded-lg text-white text-sm font-medium focus:outline-none focus:ring-2 focus:ring-emerald-500 mb-2"
          />
          <p className="text-xs text-zinc-400 italic">
            {generateTemplateDescription(strategy)}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={strategy.enabled !== false}
              onChange={(e) => handleChange({ enabled: e.target.checked })}
              className="w-4 h-4 text-emerald-600 bg-zinc-700 border-zinc-600 rounded focus:ring-emerald-500 focus:ring-2"
            />
            <span className="text-xs text-zinc-300">
              {strategy.enabled !== false ? "Включена" : "Выключена"}
            </span>
          </label>
          <button
            onClick={() => onDelete(index)}
            className="px-2 py-1 bg-red-600 hover:bg-red-700 text-white text-xs font-medium rounded transition-colors"
          >
            Удалить
          </button>
        </div>
      </div>

      {/* Галочка useGlobalFilters */}
      <div className="mb-4 p-3 bg-zinc-900/50 border border-zinc-700/50 rounded-lg">
        <label className="flex items-start gap-3 cursor-pointer">
          <input
            type="checkbox"
            checked={strategy.useGlobalFilters !== false}
            onChange={(e) => handleChange({ useGlobalFilters: e.target.checked })}
            className="mt-0.5 w-4 h-4 text-emerald-600 bg-zinc-700 border-zinc-600 rounded focus:ring-emerald-500 focus:ring-2"
          />
          <div className="flex-1">
            <span className="text-sm font-medium text-zinc-200">
              Использовать мои фильтры из глобальных настроек (дельта, объём, тень)
            </span>
            <p className="text-xs text-zinc-500 mt-1.5">
              {strategy.useGlobalFilters !== false
                ? "Стратегия будет использовать фильтры из ваших глобальных настроек прострела для дельты, объёма и тени."
                : "Укажите значения для дельты, объёма и тени в условиях стратегии ниже."}
            </p>
          </div>
        </label>
      </div>

      {/* Базовые фильтры, если useGlobalFilters = false */}
      {strategy.useGlobalFilters === false && validationError?.hasError && (
        <div className="mb-4 p-3 bg-red-900/30 border border-red-600/50 rounded-lg">
          <p className="text-xs text-red-300">{validationError.message}</p>
        </div>
      )}

      {/* Условия */}
      <div className="mb-4">
        <div className="flex items-center justify-between mb-2">
          <h4 className="text-sm font-medium text-zinc-300">Условия</h4>
          <button
            onClick={addCondition}
            className="px-3 py-1 bg-zinc-700 hover:bg-zinc-600 text-white text-xs font-medium rounded transition-colors"
          >
            + Добавить условие
          </button>
        </div>
        {strategy.conditions.map((condition, condIndex) => (
          <ConditionEditor
            key={condIndex}
            condition={condition}
            index={condIndex}
            onChange={handleConditionChange}
            onDelete={handleConditionDelete}
            canDelete={strategy.conditions.length > 1}
            generateDescription={generateTemplateDescription}
          />
        ))}
      </div>

      {/* Редактор шаблона сообщения (упрощённый) */}
      <div className="mb-4">
        <label className="block text-xs text-zinc-400 mb-2">Шаблон сообщения</label>
        <textarea
          value={convertToFriendlyNames(strategy.template)}
          onChange={(e) => handleChange({ template: convertToTechnicalKeys(e.target.value) })}
          className="w-full min-h-32 px-4 py-3 bg-zinc-800 border-2 border-zinc-600 rounded-lg text-white font-mono text-sm focus:outline-none focus:ring-2 focus:border-emerald-500"
          style={{ whiteSpace: 'pre-wrap' }}
        />
      </div>
    </div>
  );
}

