"use client";

import { useState, useEffect, useRef } from "react";
import { ConditionalTemplate } from "./types";
import { convertToTechnicalKeys, convertToFriendlyKeys, generateMessagePreview } from "./utils/templateUtils";
import { placeholderMap } from "./utils/placeholderMap";

interface StrategyDetailsPanelProps {
  strategy: ConditionalTemplate;
  strategyIndex: number;
  strategyValidationErrors?: { hasError: boolean; missingFields: string[]; message: string };
  isConditionalUserEditingRef: { current: boolean };
  onStrategyChange: (strategy: ConditionalTemplate) => void;
  onValidationErrorsChange?: (errors: { hasError: boolean; missingFields: string[]; message: string } | null) => void;
  generateTemplateDescription: (template: ConditionalTemplate) => string;
  onUnsavedChanges?: () => void;
}

// Компонент Tooltip
const Tooltip = ({ text, children }: { text: string; children: React.ReactNode }) => {
  const [show, setShow] = useState(false);
  const [position, setPosition] = useState<{ top: number; left: number } | null>(null);
  const tooltipRef = useRef<HTMLDivElement>(null);

  const handleMouseEnter = (e: React.MouseEvent) => {
    const rect = e.currentTarget.getBoundingClientRect();
    setPosition({
      top: rect.top + window.scrollY,
      left: rect.right + 10 + window.scrollX,
    });
    setShow(true);
  };

  const handleMouseLeave = () => {
    setShow(false);
  };

  return (
    <div className="relative inline-block">
      <div onMouseEnter={handleMouseEnter} onMouseLeave={handleMouseLeave} className="inline-flex items-center gap-1">
        {children}
      </div>
      {show && position && (
        <div
          ref={tooltipRef}
          className="fixed z-50 px-3 py-2 bg-zinc-800 border border-emerald-500/50 rounded-lg shadow-xl text-sm text-zinc-200 max-w-xs pointer-events-none"
          style={{
            top: `${position.top}px`,
            left: `${position.left}px`,
          }}
        >
          {text}
          <div className="absolute left-0 top-1/2 transform -translate-y-1/2 -translate-x-full w-0 h-0 border-t-4 border-t-transparent border-r-4 border-r-emerald-500/50 border-b-4 border-b-transparent" />
        </div>
      )}
    </div>
  );
};

export default function StrategyDetailsPanel({
  strategy,
  strategyIndex,
  strategyValidationErrors,
  isConditionalUserEditingRef,
  onStrategyChange,
  onValidationErrorsChange,
  generateTemplateDescription,
  onUnsavedChanges,
}: StrategyDetailsPanelProps) {
  // Для новых стратегий (без имени) скрываем секцию "template", для остальных тоже скрываем по умолчанию
  const [expandedSections, setExpandedSections] = useState<Set<string>>(new Set(["main", "filters", "conditions"]));

  // Обновление описания при изменении условий
  useEffect(() => {
    const updatedDescription = generateTemplateDescription(strategy);
    if (strategy.description !== updatedDescription) {
      onStrategyChange({
        ...strategy,
        description: updatedDescription,
      });
    }
  }, [strategy.conditions]);

  const toggleSection = (section: string) => {
    setExpandedSections((prev) => {
      const newSet = new Set(prev);
      if (newSet.has(section)) {
        newSet.delete(section);
      } else {
        newSet.add(section);
      }
      return newSet;
    });
  };

  const handleStrategyUpdate = (updates: Partial<ConditionalTemplate>) => {
    onStrategyChange({ ...strategy, ...updates });
    onUnsavedChanges?.();
  };

  const convertTemplateToHTML = (template: string): string => {
    let html = template;
    const friendlyToLabel: Record<string, string> = {
      "[[Дельта стрелы]]": "Дельта стрелы",
      "[[Направление]]": "Направление",
      "[[Биржа и тип рынка]]": "Биржа и тип рынка",
      "[[Торговая пара]]": "Торговая пара",
      "[[Объём стрелы]]": "Объём стрелы",
      "[[Тень свечи]]": "Тень свечи",
      "[[Время детекта]]": "Время детекта",
      "[[Временная метка]]": "Временная метка",
    };
    
    Object.entries(placeholderMap).forEach(([friendly, technical]) => {
      const label = friendlyToLabel[friendly] || friendly.replace('[[', '').replace(']]', '');
      const blockHTML = `<span class="inline-flex items-center gap-1.5 px-2 py-1 mx-0.5 bg-emerald-500/20 border border-emerald-500/50 rounded text-emerald-300 text-xs font-medium cursor-default" data-placeholder-key="${friendly}" contenteditable="false"><svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 8h10M7 12h4m1 8l-4-4H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-3l-4 4z"></path></svg><span>${label}</span></span>`;
      html = html.replace(new RegExp(friendly.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'g'), blockHTML);
    });
    html = html.replace(/\n/g, '<br>');
    return html;
  };

  const insertPlaceholder = (placeholder: string) => {
    const editor = document.getElementById(`conditionalTemplate_${strategyIndex}`) as HTMLElement;
    if (!editor) return;
    
    const selection = window.getSelection();
    if (selection && selection.rangeCount > 0) {
      const range = selection.getRangeAt(0);
      range.deleteContents();

      const friendlyToLabel: Record<string, string> = {
        "[[Дельта стрелы]]": "Дельта стрелы",
        "[[Направление]]": "Направление",
        "[[Биржа и тип рынка]]": "Биржа и тип рынка",
        "[[Торговая пара]]": "Торговая пара",
        "[[Объём стрелы]]": "Объём стрелы",
        "[[Тень свечи]]": "Тень свечи",
        "[[Время детекта]]": "Время детекта",
        "[[Временная метка]]": "Временная метка",
      };
      
      const label = friendlyToLabel[placeholder] || placeholder.replace('[[', '').replace(']]', '');
      const block = document.createElement("span");
      block.className = "inline-flex items-center gap-1.5 px-2 py-1 mx-0.5 bg-emerald-500/20 border border-emerald-500/50 rounded text-emerald-300 text-xs font-medium cursor-default";
      block.setAttribute("data-placeholder-key", placeholder);
      block.setAttribute("contenteditable", "false");
      block.innerHTML = `<svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 8h10M7 12h4m1 8l-4-4H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-3l-4 4z"></path></svg><span>${label}</span>`;

      range.insertNode(block);
      const newRange = document.createRange();
      newRange.setStartAfter(block);
      newRange.collapse(true);
      selection.removeAllRanges();
      selection.addRange(newRange);

      const updatedContent = editor.innerHTML;
      const tempDiv = document.createElement("div");
      tempDiv.innerHTML = updatedContent;
      const blocks = tempDiv.querySelectorAll("[data-placeholder-key]");
      let textContent = updatedContent;
      blocks.forEach((b) => {
        const key = b.getAttribute("data-placeholder-key");
        if (key) {
          textContent = textContent.replace(b.outerHTML, key);
        }
      });

      handleStrategyUpdate({
        template: convertToTechnicalKeys(textContent.replace(/<br\s*\/?>/gi, "\n")),
      });
      onUnsavedChanges?.();
    }
  };

  // Инициализация редактора шаблона
  useEffect(() => {
    const timer = setTimeout(() => {
      if (!isConditionalUserEditingRef.current) {
        const editorId = `conditionalTemplate_${strategyIndex}`;
        const editor = document.getElementById(editorId) as HTMLElement;
        if (editor) {
          const html = convertTemplateToHTML(convertToFriendlyKeys(strategy.template));
          if (editor.innerHTML !== html) {
            editor.innerHTML = html;
          }
        }
      }
    }, 100);
    return () => clearTimeout(timer);
  }, [strategy.template, strategyIndex, isConditionalUserEditingRef]);

  return (
    <div className="h-full overflow-y-auto">
      {/* Заголовок */}
      <div className="mb-6">
        <h3 className="text-xl font-bold text-white mb-2">
          {strategy.name || `Стратегия #${strategyIndex + 1}`}
        </h3>
        {strategy.description && (
          <p className="text-sm text-zinc-400">{strategy.description}</p>
        )}
      </div>

      {/* Основная секция "Main" */}
      <div className="mb-6 bg-zinc-800/50 border border-zinc-700 rounded-lg p-4">
        <button
          onClick={() => toggleSection("main")}
          className="w-full flex items-center justify-between mb-4"
        >
          <h4 className="text-lg font-semibold text-white">Main</h4>
          <svg
            className={`w-5 h-5 text-zinc-400 transition-transform ${expandedSections.has("main") ? "rotate-180" : ""}`}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </button>

        {expandedSections.has("main") && (
          <>

          {/* Таблица параметров */}
          <div className="space-y-3">
            {/* Название стратегии */}
            <div className="flex items-center gap-4">
              <div className="w-1/3 text-sm font-medium text-zinc-300 flex items-center gap-2">
                <Tooltip text="Уникальное название стратегии. Обязательное поле для сохранения.">
                  <span className={!strategy.name || strategy.name.trim() === "" ? "text-red-300" : ""}>Название стратегии</span>
                  <svg className="w-4 h-4 text-zinc-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                </Tooltip>
                <span className="text-red-400">*</span>
              </div>
              <div className="flex-1">
                <input
                  type="text"
                  value={strategy.name || ""}
                  onChange={(e) => handleStrategyUpdate({ name: e.target.value.trim() || undefined })}
                  placeholder={`Стратегия #${strategyIndex + 1}`}
                  className={`w-full px-3 py-2 bg-zinc-700 border rounded-lg text-white text-sm focus:outline-none focus:ring-2 ${
                    !strategy.name || strategy.name.trim() === ""
                      ? "border-red-500 focus:ring-red-500 focus:border-red-500"
                      : "border-zinc-600 focus:ring-emerald-500"
                  }`}
                />
                {(!strategy.name || strategy.name.trim() === "") && (
                  <p className="text-xs text-red-400 mt-1">Необходимо указать название стратегии для сохранения</p>
                )}
              </div>
            </div>

            {/* Описание */}
            <div className="flex items-center gap-4">
              <div className="w-1/3 text-sm font-medium text-zinc-300 flex items-center gap-2">
                <Tooltip text="Автоматически генерируемое описание стратегии на основе заданных условий. Обновляется при изменении условий.">
                  <span>Описание</span>
                  <svg className="w-4 h-4 text-zinc-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                </Tooltip>
              </div>
              <div className="flex-1">
                <input
                  type="text"
                  value={strategy.description || ""}
                  readOnly
                  className="w-full px-3 py-2 bg-zinc-800/50 border border-zinc-700 rounded-lg text-zinc-400 text-sm cursor-not-allowed"
                />
              </div>
            </div>

            {/* Chat ID */}
            <div className="flex items-center gap-4">
              <div className="w-1/3 text-sm font-medium text-zinc-300 flex items-center gap-2">
                <Tooltip text="Опциональный Chat ID для отправки уведомлений в отдельный Telegram чат. Если не указан, используется глобальный Chat ID из настроек.">
                  <span>Chat ID</span>
                  <svg className="w-4 h-4 text-zinc-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                </Tooltip>
              </div>
              <div className="flex-1">
                <input
                  type="text"
                  value={strategy.chatId || ""}
                  onChange={(e) => handleStrategyUpdate({ chatId: e.target.value.trim() || undefined })}
                  placeholder="Опционально"
                  className="w-full px-3 py-2 bg-zinc-700 border border-zinc-600 rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                />
              </div>
            </div>
          </div>
          </>
        )}
      </div>

      {/* Секция "Использовать глобальные фильтры" */}
      <div className="mb-6 bg-zinc-800/50 border border-zinc-700 rounded-lg p-4">
        <button
          onClick={() => toggleSection("filters")}
          className="w-full flex items-center justify-between mb-4"
        >
          <h4 className="text-lg font-semibold text-white">Фильтры</h4>
          <svg
            className={`w-5 h-5 text-zinc-400 transition-transform ${expandedSections.has("filters") ? "rotate-180" : ""}`}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </button>

        {expandedSections.has("filters") && (
          <>

          <div className="mb-4 p-3 bg-zinc-900/50 border border-zinc-700/50 rounded-lg">
            <label className="flex items-start gap-3 cursor-pointer group">
              <input
                type="checkbox"
                checked={strategy.useGlobalFilters !== false}
                onChange={(e) => {
                  const useGlobalFilters = e.target.checked;
                  const updatedConditions = useGlobalFilters
                    ? strategy.conditions.filter(
                        (c) => c.type !== "delta" && c.type !== "volume" && c.type !== "wick_pct"
                      )
                    : strategy.conditions;
                  
                  handleStrategyUpdate({
                    useGlobalFilters,
                    conditions: updatedConditions,
                  });
                  
                  if (useGlobalFilters && onValidationErrorsChange) {
                    onValidationErrorsChange(null);
                  }
                }}
                className="mt-0.5 w-4 h-4 text-emerald-600 bg-zinc-700 border-zinc-600 rounded focus:ring-emerald-500 focus:ring-2"
              />
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-zinc-200 group-hover:text-white">
                    Использовать мои фильтры из глобальных настроек (дельта, объём, тень)
                  </span>
                </div>
                <p className="text-xs text-zinc-500 mt-1.5">
                  {strategy.useGlobalFilters !== false
                    ? "Стратегия будет использовать фильтры из ваших глобальных настроек прострела для дельты, объёма и тени."
                    : "Укажите значения для дельты, объёма и тени в базовых фильтрах ниже. Эти поля обязательны для работы стратегии."}
                </p>
              </div>
            </label>
          </div>

          {/* Базовые фильтры (показываются только если useGlobalFilters = false) */}
          {strategy.useGlobalFilters === false && (
            <div
              className={`p-4 rounded-lg transition-colors ${
                strategyValidationErrors?.hasError
                  ? "bg-red-900/20 border-2 border-red-600/70"
                  : "bg-zinc-900/50 border border-zinc-700"
              }`}
            >
              <div className="flex items-center gap-2 mb-3">
                <svg
                  className={`w-5 h-5 ${strategyValidationErrors?.hasError ? "text-red-400" : "text-zinc-400"}`}
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
                <h3
                  className={`text-sm font-semibold ${strategyValidationErrors?.hasError ? "text-red-300" : "text-zinc-300"}`}
                >
                  Базовые фильтры (обязательны)
                </h3>
              </div>
              {strategyValidationErrors?.hasError && (
                <div className="mb-4 p-3 bg-red-900/30 border border-red-600/50 rounded-lg">
                  <p className="text-xs text-red-200 font-medium mb-1">⚠️ Ошибка валидации</p>
                  <p className="text-xs text-red-300/90">{strategyValidationErrors.message}</p>
                </div>
              )}
              <p className="text-xs text-zinc-400 mb-4">
                Для работы стратегии необходимо указать значения для дельты, объёма и тени. Эти фильтры будут использоваться вместо глобальных настроек.
              </p>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {/* Дельта */}
                <div>
                  <label
                    className={`block text-xs font-medium mb-2 ${
                      strategyValidationErrors?.missingFields?.includes("Дельта")
                        ? "text-red-300"
                        : "text-zinc-300"
                    }`}
                  >
                    Дельта (%) <span className="text-red-400">*</span>
                  </label>
                  <input
                    type="number"
                    step="0.1"
                    min="0.01"
                    max="100"
                    value={
                      strategy.conditions.find((c) => c.type === "delta")?.valueMin !== undefined
                        ? strategy.conditions.find((c) => c.type === "delta")?.valueMin
                        : ""
                    }
                    onChange={(e) => {
                      const val = e.target.value === "" ? undefined : parseFloat(e.target.value);
                      const updatedConditions = [...strategy.conditions];
                      const deltaIndex = updatedConditions.findIndex((c) => c.type === "delta");
                      
                      if (deltaIndex >= 0) {
                        updatedConditions[deltaIndex] = {
                          ...updatedConditions[deltaIndex],
                          valueMin: val !== undefined && !isNaN(val) ? Math.max(0.01, Math.min(100, val)) : undefined,
                          valueMax: null,
                        };
                      } else {
                        updatedConditions.unshift({
                          type: "delta",
                          valueMin: val !== undefined && !isNaN(val) ? Math.max(0.01, Math.min(100, val)) : undefined,
                          valueMax: null,
                        });
                      }
                      
                      handleStrategyUpdate({ conditions: updatedConditions });
                    }}
                    className={`w-full px-3 py-2.5 bg-zinc-800 rounded-lg text-white text-sm focus:outline-none focus:ring-2 ${
                      strategyValidationErrors?.missingFields?.includes("Дельта")
                        ? "border-2 border-red-500 focus:ring-red-500 focus:border-red-500"
                        : "border border-zinc-600 focus:ring-emerald-500 focus:border-emerald-500"
                    }`}
                    placeholder="0.3"
                  />
                  <Tooltip text="Минимальная дельта стрелы в процентах. Используется для фильтрации стрел по размеру изменения цены. Значение от 0.01% до 100%.">
                    <p
                      className={`text-[11px] mt-1 cursor-help ${
                        strategyValidationErrors?.missingFields?.includes("Дельта")
                          ? "text-red-300/70"
                          : "text-zinc-400"
                      }`}
                    >
                      Минимальная дельта стрелы (от 0.01% до 100%)
                    </p>
                  </Tooltip>
                </div>

                {/* Объём */}
                <div>
                  <label
                    className={`block text-xs font-medium mb-2 ${
                      strategyValidationErrors?.missingFields?.includes("Объём")
                        ? "text-red-300"
                        : "text-zinc-300"
                    }`}
                  >
                    Объём (USDT) <span className="text-red-400">*</span>
                  </label>
                  <input
                    type="number"
                    step="0.01"
                    min="1"
                    value={
                      strategy.conditions.find((c) => c.type === "volume")?.value !== undefined
                        ? strategy.conditions.find((c) => c.type === "volume")?.value
                        : ""
                    }
                    onChange={(e) => {
                      const val = e.target.value === "" ? undefined : parseFloat(e.target.value);
                      const updatedConditions = [...strategy.conditions];
                      const volumeIndex = updatedConditions.findIndex((c) => c.type === "volume");
                      
                      if (volumeIndex >= 0) {
                        updatedConditions[volumeIndex] = {
                          ...updatedConditions[volumeIndex],
                          value: val !== undefined && !isNaN(val) ? Math.max(1, val) : undefined,
                        };
                      } else {
                        updatedConditions.unshift({
                          type: "volume",
                          value: val !== undefined && !isNaN(val) ? Math.max(1, val) : undefined,
                        });
                      }
                      
                      handleStrategyUpdate({ conditions: updatedConditions });
                    }}
                    className={`w-full px-3 py-2.5 bg-zinc-800 rounded-lg text-white text-sm focus:outline-none focus:ring-2 ${
                      strategyValidationErrors?.missingFields?.includes("Объём")
                        ? "border-2 border-red-500 focus:ring-red-500 focus:border-red-500"
                        : "border border-zinc-600 focus:ring-emerald-500 focus:border-emerald-500"
                    }`}
                    placeholder="1000000"
                  />
                  <Tooltip text="Минимальный объём стрелы в USDT. Используется для фильтрации стрел по объёму торгов. Значение от 1 USDT.">
                    <p
                      className={`text-[11px] mt-1 cursor-help ${
                        strategyValidationErrors?.missingFields?.includes("Объём")
                          ? "text-red-300/70"
                          : "text-zinc-400"
                      }`}
                    >
                      Минимальный объём стрелы (от 1 USDT)
                    </p>
                  </Tooltip>
                </div>

                {/* Тень */}
                <div>
                  <label
                    className={`block text-xs font-medium mb-2 ${
                      strategyValidationErrors?.missingFields?.includes("Тень")
                        ? "text-red-300"
                        : "text-zinc-300"
                    }`}
                  >
                    Тень (%) <span className="text-red-400">*</span>
                  </label>
                  <input
                    type="number"
                    step="0.1"
                    min="0"
                    max="100"
                    value={
                      strategy.conditions.find((c) => c.type === "wick_pct")?.valueMin !== undefined
                        ? strategy.conditions.find((c) => c.type === "wick_pct")?.valueMin
                        : ""
                    }
                    onChange={(e) => {
                      const val = e.target.value === "" ? undefined : parseFloat(e.target.value);
                      const updatedConditions = [...strategy.conditions];
                      const wickIndex = updatedConditions.findIndex((c) => c.type === "wick_pct");
                      
                      if (wickIndex >= 0) {
                        updatedConditions[wickIndex] = {
                          ...updatedConditions[wickIndex],
                          valueMin: val !== undefined && !isNaN(val) ? Math.max(0, Math.min(100, val)) : undefined,
                          valueMax: null,
                        };
                      } else {
                        updatedConditions.unshift({
                          type: "wick_pct",
                          valueMin: val !== undefined && !isNaN(val) ? Math.max(0, Math.min(100, val)) : undefined,
                          valueMax: null,
                        });
                      }
                      
                      handleStrategyUpdate({ conditions: updatedConditions });
                    }}
                    className={`w-full px-3 py-2.5 rounded-lg text-white text-sm focus:outline-none focus:ring-2 ${
                      strategyValidationErrors?.missingFields?.includes("Тень")
                        ? "bg-zinc-800 border-2 border-red-500 focus:ring-red-500 focus:border-red-500"
                        : "bg-zinc-800 border border-zinc-600 focus:ring-emerald-500 focus:border-emerald-500"
                    }`}
                    placeholder="0"
                  />
                  <Tooltip text="Минимальная тень свечи в процентах. Определяет минимальный процент тени (верхней или нижней части свечи) для фильтрации стрел.">
                    <p
                      className={`text-[11px] mt-1 cursor-help ${
                        strategyValidationErrors?.missingFields?.includes("Тень")
                          ? "text-red-300/70"
                          : "text-zinc-400"
                      }`}
                    >
                      Минимальная тень свечи (от 0% до 100%)
                    </p>
                  </Tooltip>
                </div>
              </div>
            </div>
          )}
          </>
        )}
      </div>

      {/* Секция "Условия" */}
      <div className="mb-6 bg-zinc-800/50 border border-zinc-700 rounded-lg p-4">
        <button
          onClick={() => toggleSection("conditions")}
          className="w-full flex items-center justify-between mb-4"
        >
          <h4 className="text-lg font-semibold text-white">
            Условия <span className="text-sm font-normal text-zinc-400">(все должны выполняться)</span>
          </h4>
          <svg
            className={`w-5 h-5 text-zinc-400 transition-transform ${expandedSections.has("conditions") ? "rotate-180" : ""}`}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </button>

        {expandedSections.has("conditions") && (
          <>

          <p className="text-xs text-zinc-500 mb-4">
            Можно добавить несколько строк с разными параметрами (серия, символ, биржа и т.д.).
          </p>

          <div className="space-y-3 mb-4">
            {strategy.conditions
              .map((condition, actualIndex) => {
                // Пропускаем базовые фильтры (объём, дельта, тень) - они всегда показываются только в секции фильтров
                if (condition.type === "delta" || condition.type === "volume" || condition.type === "wick_pct") {
                  return null;
                }

                const handleConditionChange = (updates: Partial<typeof condition>) => {
                  const updatedConditions = [...strategy.conditions];
                  updatedConditions[actualIndex] = { ...updatedConditions[actualIndex], ...updates };
                  handleStrategyUpdate({ conditions: updatedConditions });
                };

                const handleConditionDelete = () => {
                  const updatedConditions = strategy.conditions.filter((_, i) => i !== actualIndex);
                  handleStrategyUpdate({ conditions: updatedConditions });
                };

                return (
                  <div key={actualIndex} className="bg-zinc-900/50 border border-zinc-700/50 rounded-lg p-3 md:p-4">
                    <div className="flex gap-2 items-end mb-2">
                      <div className="w-full md:w-56">
                        <label className="block text-xs text-zinc-400 mb-1">Параметр</label>
                        <select
                          value={condition.type}
                          onChange={(e) => {
                            const newType = e.target.value as ConditionalTemplate["conditions"][0]["type"];
                            const newCondition: ConditionalTemplate["conditions"][0] = { type: newType };

                            if (newType === "series") {
                              newCondition.count = 2;
                              newCondition.timeWindowSeconds = 300;
                            } else if (newType === "symbol") {
                              newCondition.symbol = "";
                            } else if (newType === "exchange_market") {
                              newCondition.exchange_market = "binance_spot";
                            } else if (newType === "direction") {
                              newCondition.direction = "up";
                            } else {
                              newCondition.value = 0;
                            }

                            handleConditionChange(newCondition);
                          }}
                          className="w-full px-3 py-2 bg-zinc-700 border border-zinc-600 rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                        >
                          <option value="series">Серия стрел</option>
                          <option value="symbol">Символ (монета)</option>
                          <option value="exchange_market">Биржа и тип рынка</option>
                          <option value="direction">Направление стрелы</option>
                        </select>
                      </div>

                      {/* Рендеринг полей в зависимости от типа условия */}
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
                                handleConditionChange({ count: isNaN(val) ? 2 : Math.max(2, val) });
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
                                handleConditionChange({ timeWindowSeconds: isNaN(val) ? 300 : Math.max(60, val) });
                              }}
                              className="w-full px-3 py-2.5 bg-zinc-700 border border-zinc-600 rounded-lg text-white text-sm text-center focus:outline-none focus:ring-2 focus:ring-emerald-500"
                              placeholder="300"
                            />
                          </div>
                        </>
                      )}


                      {condition.type === "symbol" && (
                        <div className="flex-1">
                          <label className="block text-xs text-zinc-400 mb-1">Символ (монета)</label>
                          <input
                            type="text"
                            value={condition.symbol || ""}
                            onChange={(e) => handleConditionChange({ symbol: e.target.value.toUpperCase().trim() })}
                            className="w-40 px-3 py-2 bg-zinc-700 border border-zinc-600 rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                            placeholder="ETH, BTC, ADA..."
                          />
                        </div>
                      )}


                      {condition.type === "exchange_market" && (
                        <div className="flex-1">
                          <label className="block text-xs text-zinc-400 mb-1">Биржа и тип рынка</label>
                          <select
                            value={condition.exchange_market || "binance_spot"}
                            onChange={(e) => handleConditionChange({ exchange_market: e.target.value })}
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
                            onChange={(e) => handleConditionChange({ direction: e.target.value as "up" | "down" })}
                            className="w-40 px-3 py-2 bg-zinc-700 border border-zinc-600 rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                          >
                            <option value="up">Вверх ⬆️</option>
                            <option value="down">Вниз ⬇️</option>
                          </select>
                        </div>
                      )}

                      {(!["series", "symbol", "exchange_market", "direction"].includes(condition.type)) && (
                        <div className="w-full md:w-auto md:min-w-[220px]">
                          <label className="block text-xs text-zinc-400 mb-1">Значение (≥)</label>
                          <input
                            type="number"
                            step="0.01"
                            value={condition.value || ""}
                            onChange={(e) => {
                              const val = e.target.value === "" ? 0 : parseFloat(e.target.value);
                              handleConditionChange({ value: isNaN(val) ? 0 : val });
                            }}
                            className="w-full px-3 py-2.5 bg-zinc-700 border border-zinc-600 rounded-lg text-white text-sm text-center focus:outline-none focus:ring-2 focus:ring-emerald-500"
                            placeholder="0"
                          />
                        </div>
                      )}

                      {strategy.conditions.filter((c) => {
                        return c.type !== "delta" && c.type !== "volume" && c.type !== "wick_pct";
                      }).length > 1 && condition && (
                        <button
                          onClick={handleConditionDelete}
                          className="px-2 py-2 bg-red-600/50 hover:bg-red-600 text-white text-xs font-medium rounded transition-colors mb-0.5"
                          title="Удалить условие"
                        >
                          ×
                        </button>
                      )}
                    </div>
                  </div>
                );
              })
              .filter((item) => item !== null)}
          </div>

          <button
            onClick={() => {
              const updatedConditions = [...strategy.conditions];
              updatedConditions.push({
                type: "series",
                count: 2,
                timeWindowSeconds: 300,
              });
              handleStrategyUpdate({ conditions: updatedConditions });
            }}
            className="inline-flex items-center justify-center px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 text-white text-xs font-medium rounded-lg border border-zinc-700 hover:border-emerald-500/60 transition-colors"
          >
            <span className="mr-1 text-emerald-400 text-sm">+</span>
            Добавить условие
          </button>
          </>
        )}
      </div>

      {/* Секция "Шаблон сообщения" */}
      <div className="mb-6 bg-zinc-800/50 border border-zinc-700 rounded-lg p-4">
        <button
          onClick={() => toggleSection("template")}
          className="w-full flex items-center justify-between mb-4"
        >
          <h4 className="text-lg font-semibold text-white">Шаблон сообщения</h4>
          <svg
            className={`w-5 h-5 text-zinc-400 transition-transform ${expandedSections.has("template") ? "rotate-180" : ""}`}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </button>

        {expandedSections.has("template") && (
          <>

          {/* Доступные вставки */}
          <div className="mb-3">
            <h4 className="text-xs font-medium text-zinc-300 mb-2">Доступные вставки:</h4>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
              {[
                { friendly: "[[Дельта стрелы]]", label: "Дельта стрелы", desc: "Например: 5.23%" },
                { friendly: "[[Направление]]", label: "Направление", desc: "Эмодзи стрелки вверх ⬆️ или вниз ⬇️" },
                { friendly: "[[Биржа и тип рынка]]", label: "Биржа и тип рынка", desc: "BINANCE | SPOT" },
                { friendly: "[[Торговая пара]]", label: "Торговая пара", desc: "Например: BTC-USDT" },
                { friendly: "[[Объём стрелы]]", label: "Объём стрелы", desc: "Объём в USDT" },
                { friendly: "[[Тень свечи]]", label: "Тень свечи", desc: "Процент тени свечи" },
                { friendly: "[[Время детекта]]", label: "Время детекта", desc: "Дата и время (YYYY-MM-DD HH:MM:SS)" },
                { friendly: "[[Временная метка]]", label: "Временная метка", desc: "Unix timestamp" },
              ].map((placeholder) => (
                <button
                  key={placeholder.friendly}
                  type="button"
                  onClick={() => insertPlaceholder(placeholder.friendly)}
                  className="text-left px-3 py-2 bg-zinc-800 hover:bg-zinc-700 border-2 border-zinc-600 hover:border-emerald-500 rounded-lg transition-all cursor-pointer group shadow-sm hover:shadow-md"
                  title={placeholder.desc}
                >
                  <div className="text-xs font-medium text-white group-hover:text-emerald-300 mb-0.5">
                    {placeholder.label}
                  </div>
                  <div className="text-[11px] text-zinc-500 group-hover:text-zinc-400">
                    {placeholder.desc}
                  </div>
                </button>
              ))}
            </div>
          </div>

          {/* Редактор шаблона */}
          <div className="relative mb-4">
            <div
              id={`conditionalTemplate_${strategyIndex}`}
              contentEditable
              suppressContentEditableWarning
              onInput={(e) => {
                const editor = e.currentTarget as HTMLElement;
                const content = editor.innerHTML;
                const tempDiv = document.createElement("div");
                tempDiv.innerHTML = content;
                const blocks = tempDiv.querySelectorAll("[data-placeholder-key]");
                let textContent = content;
                blocks.forEach((block) => {
                  const key = block.getAttribute("data-placeholder-key");
                  if (key) {
                    const blockHTML = block.outerHTML.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
                    textContent = textContent.replace(new RegExp(blockHTML, "g"), key);
                  }
                });
                textContent = textContent.replace(/<br\s*\/?>/gi, "\n");

                isConditionalUserEditingRef.current = true;

                handleStrategyUpdate({
                  template: convertToTechnicalKeys(textContent),
                });
                onUnsavedChanges?.();

                setTimeout(() => {
                  isConditionalUserEditingRef.current = false;
                }, 150);
              }}
              className="w-full min-h-32 px-4 py-3 bg-zinc-800 border-2 border-zinc-600 rounded-lg text-white font-mono text-sm focus:outline-none focus:ring-2 focus:border-emerald-500 focus:ring-emerald-500 resize-none overflow-y-auto template-editor cursor-text"
              style={{ whiteSpace: "pre-wrap" }}
            />
          </div>

          {/* Превью сообщения */}
          <div>
            <label className="block text-xs font-medium text-zinc-300 mb-2">
              Превью сообщения в Telegram
            </label>
            <div className="bg-zinc-800 border-2 border-zinc-700 rounded-lg p-4 min-h-[100px]">
              <div
                className="text-white text-sm whitespace-pre-wrap font-sans"
                dangerouslySetInnerHTML={{
                  __html: generateMessagePreview(strategy.template || "").replace(/\n/g, "<br>"),
                }}
              />
            </div>
            <p className="text-xs text-zinc-500 mt-2">
              💡 Это пример того, как будет выглядеть сообщение в Telegram с примерами значений
            </p>
          </div>
          </>
        )}
      </div>
    </div>
  );
}

