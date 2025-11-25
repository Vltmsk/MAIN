"use client";

import { useEffect, useRef } from "react";
import { ConditionalTemplate } from "./types";
import { convertToTechnicalKeys, convertToFriendlyKeys as convertToFriendlyNames, generateMessagePreview } from "./utils/templateUtils";
import { placeholderMap } from "./utils/placeholderMap";

interface StrategiesSettingsProps {
  conditionalTemplates: ConditionalTemplate[];
  strategyValidationErrors: Record<number, { hasError: boolean; missingFields: string[]; message: string }>;
  isConditionalUserEditingRef: { current: boolean };
  onTemplatesChange: (templates: ConditionalTemplate[]) => void;
  onValidationErrorsChange: (errors: Record<number, { hasError: boolean; missingFields: string[]; message: string }>) => void;
  onSave: () => Promise<void>;
  saving: boolean;
  extractTextFromEditor: () => string;
  messageTemplate: string;
  generateTemplateDescription: (template: ConditionalTemplate) => string;
}

export default function StrategiesSettings({
  conditionalTemplates,
  strategyValidationErrors,
  isConditionalUserEditingRef,
  onTemplatesChange,
  onValidationErrorsChange,
  onSave,
  saving,
  extractTextFromEditor,
  messageTemplate,
  generateTemplateDescription,
}: StrategiesSettingsProps) {

  const handleStrategyChange = (index: number, strategy: ConditionalTemplate) => {
    const newTemplates = [...conditionalTemplates];
    newTemplates[index] = strategy;
    onTemplatesChange(newTemplates);
    
    // Очищаем ошибки валидации при изменении useGlobalFilters
    if (strategy.useGlobalFilters !== false) {
      const newErrors = { ...strategyValidationErrors };
      delete newErrors[index];
      onValidationErrorsChange(newErrors);
    }
  };

  const handleStrategyDelete = (index: number) => {
    const newTemplates = conditionalTemplates.filter((_, i) => i !== index);
    onTemplatesChange(newTemplates);
    
    // Удаляем ошибки валидации для удалённой стратегии
    const newErrors = { ...strategyValidationErrors };
    delete newErrors[index];
    // Сдвигаем индексы ошибок
    const shifted: typeof strategyValidationErrors = {};
    Object.entries(newErrors).forEach(([key, value]) => {
      const oldIndex = parseInt(key);
      if (oldIndex > index) {
        shifted[oldIndex - 1] = value;
      } else {
        shifted[oldIndex] = value;
      }
    });
    onValidationErrorsChange(shifted);
  };

  const handleAddStrategy = () => {
    const extractedText = extractTextFromEditor();
    const technicalTemplate = convertToTechnicalKeys(extractedText || messageTemplate);
    onTemplatesChange([
      ...conditionalTemplates,
      {
        name: undefined,
        enabled: true,
        useGlobalFilters: true,
        conditions: [{
          type: "volume",
          value: 0,
        }],
        template: technicalTemplate,
      },
    ]);
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

  const insertPlaceholderIntoStrategy = (index: number, placeholder: string) => {
    const editor = document.getElementById(`conditionalTemplate_${index}`) as HTMLElement;
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

      const newTemplates = [...conditionalTemplates];
      newTemplates[index].template = convertToTechnicalKeys(textContent.replace(/<br\s*\/?>/gi, "\n"));
      onTemplatesChange(newTemplates);
    }
  };

  // Инициализация редакторов стратегий
  useEffect(() => {
    const timer = setTimeout(() => {
      if (!isConditionalUserEditingRef.current) {
        conditionalTemplates.forEach((template, index) => {
          const editorId = `conditionalTemplate_${index}`;
          const editor = document.getElementById(editorId) as HTMLElement;
          if (editor) {
            const html = convertTemplateToHTML(convertToFriendlyNames(template.template));
            if (editor.innerHTML !== html) {
              editor.innerHTML = html;
            }
          }
        });
      }
    }, 100);
    return () => clearTimeout(timer);
  }, [conditionalTemplates, isConditionalUserEditingRef]);

  return (
    <div className="grid grid-cols-1 md:grid-cols-12 gap-6">
      <div className="col-span-1 md:col-span-12">
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6">
          <div className="flex items-center justify-between mb-1">
            <div className="flex items-center gap-2">
              <h2 className="text-xl font-bold text-white">Стратегии</h2>
              <svg className="w-5 h-5 text-zinc-400 cursor-help" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <title>Создайте независимые стратегии детектирования с собственными фильтрами и условиями. Стратегии работают параллельно с обычными настройками прострела и имеют приоритет при отправке уведомлений.</title>
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
          </div>
          <p className="text-sm text-zinc-400 mb-4 mt-2">
            Создайте независимые стратегии детектирования с собственными фильтрами и условиями. Стратегии работают параллельно с обычными настройками прострела и имеют приоритет при отправке уведомлений.
            Можно задать несколько условий одновременно (все условия должны выполняться). Все подходящие стратегии будут отправлены одновременно при обнаружении стрелы.
          </p>

          <div className="space-y-4 mb-4">
            {conditionalTemplates.map((template, index) => {
              const isEnabled = template.enabled !== false;
              
              return (
                <div key={index} className={`bg-zinc-800 border rounded-lg p-4 ${isEnabled ? 'border-zinc-700' : 'border-zinc-600/50 opacity-75'}`}>
                  <div className="flex items-start justify-between mb-3">
                    <div className="flex-1">
                      <div className="flex items-center gap-3 mb-2">
                        <input
                          type="text"
                          value={template.name || ""}
                          onChange={(e) => {
                            const newTemplates = [...conditionalTemplates];
                            newTemplates[index].name = e.target.value.trim() || undefined;
                            onTemplatesChange(newTemplates);
                          }}
                          placeholder={`Стратегия #${index + 1}`}
                          className="flex-1 px-3 py-1.5 bg-zinc-700 border border-zinc-600 rounded-lg text-white text-sm font-medium focus:outline-none focus:ring-2 focus:ring-emerald-500"
                        />
                        <div className="flex items-center gap-2">
                          <label className="flex items-center gap-2 cursor-pointer">
                            <input
                              type="checkbox"
                              checked={isEnabled}
                              onChange={(e) => {
                                const newTemplates = [...conditionalTemplates];
                                newTemplates[index].enabled = e.target.checked;
                                onTemplatesChange(newTemplates);
                              }}
                              className="w-4 h-4 text-emerald-600 bg-zinc-700 border-zinc-600 rounded focus:ring-emerald-500 focus:ring-2"
                            />
                            <span className="text-xs text-zinc-300">
                              {isEnabled ? "Включена" : "Выключена"}
                            </span>
                          </label>
                        </div>
                      </div>
                      <p className="text-xs text-zinc-400 italic">
                        {generateTemplateDescription(template)}
                      </p>
                    </div>
                    <button
                      onClick={() => handleStrategyDelete(index)}
                      className="ml-3 px-2 py-1 bg-red-600 hover:bg-red-700 text-white text-xs font-medium rounded transition-colors"
                    >
                      Удалить
                    </button>
                  </div>

                  {/* Галочка useGlobalFilters */}
                  <div className="mb-4 p-3 bg-zinc-900/50 border border-zinc-700/50 rounded-lg">
                    <label className="flex items-start gap-3 cursor-pointer group">
                      <input
                        type="checkbox"
                        checked={template.useGlobalFilters !== false}
                        onChange={(e) => {
                          const newTemplates = [...conditionalTemplates];
                          newTemplates[index].useGlobalFilters = e.target.checked;
                          if (!e.target.checked) {
                            // Удаляем условия delta, volume, wick_pct, если они есть
                            newTemplates[index].conditions = newTemplates[index].conditions.filter(
                              cond => cond.type !== "delta" && cond.type !== "volume" && cond.type !== "wick_pct"
                            );
                          } else {
                            // Если включаем глобальные фильтры, очищаем ошибки валидации для этой стратегии
                            const newErrors = { ...strategyValidationErrors };
                            delete newErrors[index];
                            onValidationErrorsChange(newErrors);
                          }
                          onTemplatesChange(newTemplates);
                        }}
                        className="mt-0.5 w-4 h-4 text-emerald-600 bg-zinc-700 border-zinc-600 rounded focus:ring-emerald-500 focus:ring-2"
                      />
                      <div className="flex-1">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-medium text-zinc-200 group-hover:text-white">
                            Использовать мои фильтры из глобальных настроек (дельта, объём, тень)
                          </span>
                          <svg className="w-4 h-4 text-zinc-400 cursor-help" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <title>
                              Если включено: стратегия будет использовать фильтры дельты, объёма и тени из ваших настроек пары (pairSettings).
                              Если выключено: вы должны указать значения для дельты, объёма и тени в условиях стратегии.
                            </title>
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                          </svg>
                        </div>
                        <p className="text-xs text-zinc-500 mt-1.5">
                          {template.useGlobalFilters !== false 
                            ? "Стратегия будет использовать фильтры из ваших глобальных настроек прострела для дельты, объёма и тени."
                            : "Укажите значения для дельты, объёма и тени в условиях стратегии ниже. Эти поля обязательны для работы стратегии."}
                        </p>
                      </div>
                    </label>
                  </div>

                  {/* Базовые фильтры (показываются только если useGlobalFilters = false) */}
                  {template.useGlobalFilters === false && (
                    <div className={`mb-4 p-4 rounded-lg transition-colors ${
                      strategyValidationErrors[index]?.hasError 
                        ? "bg-red-900/20 border-2 border-red-600/70" 
                        : "bg-amber-900/20 border border-amber-700/50"
                    }`}>
                      <div className="flex items-center gap-2 mb-3">
                        <svg className={`w-5 h-5 ${strategyValidationErrors[index]?.hasError ? "text-red-400" : "text-amber-400"}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                        </svg>
                        <h3 className={`text-sm font-semibold ${strategyValidationErrors[index]?.hasError ? "text-red-300" : "text-amber-300"}`}>
                          Базовые фильтры (обязательны)
                        </h3>
                      </div>
                      {strategyValidationErrors[index]?.hasError && (
                        <div className="mb-4 p-3 bg-red-900/30 border border-red-600/50 rounded-lg">
                          <p className="text-xs text-red-200 font-medium mb-1">
                            ⚠️ Ошибка валидации
                          </p>
                          <p className="text-xs text-red-300/90">
                            {strategyValidationErrors[index].message}
                          </p>
                        </div>
                      )}
                      <p className="text-xs text-amber-200/80 mb-4">
                        Для работы стратегии необходимо указать значения для дельты, объёма и тени. Эти фильтры будут использоваться вместо глобальных настроек.
                      </p>
                      
                      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                        {/* Дельта */}
                        <div>
                          <label className={`block text-xs font-medium mb-2 ${
                            strategyValidationErrors[index]?.missingFields?.includes("Дельта") 
                              ? "text-red-300" 
                              : "text-amber-200"
                          }`}>
                            Дельта (%) <span className="text-red-400">*</span>
                          </label>
                          <input
                            type="number"
                            step="0.1"
                            min="0.01"
                            max="100"
                            value={
                              template.conditions.find(c => c.type === "delta")?.valueMin !== undefined
                                ? template.conditions.find(c => c.type === "delta")?.valueMin
                                : ""
                            }
                            onChange={(e) => {
                              const newTemplates = [...conditionalTemplates];
                              const val = e.target.value === "" ? undefined : parseFloat(e.target.value);
                              const deltaIndex = newTemplates[index].conditions.findIndex(c => c.type === "delta");
                              if (deltaIndex >= 0) {
                                newTemplates[index].conditions[deltaIndex].valueMin = val !== undefined && !isNaN(val) ? Math.max(0.01, Math.min(100, val)) : undefined;
                                newTemplates[index].conditions[deltaIndex].valueMax = null;
                              } else {
                                newTemplates[index].conditions.unshift({
                                  type: "delta",
                                  valueMin: val !== undefined && !isNaN(val) ? Math.max(0.01, Math.min(100, val)) : undefined,
                                  valueMax: null,
                                });
                              }
                              const updatedDescription = generateTemplateDescription(newTemplates[index]);
                              newTemplates[index].description = updatedDescription;
                              onTemplatesChange(newTemplates);
                              
                              if (val !== undefined && !isNaN(val)) {
                                const newErrors = { ...strategyValidationErrors };
                                if (newErrors[index] && newErrors[index].missingFields) {
                                  newErrors[index] = {
                                    ...newErrors[index],
                                    missingFields: newErrors[index].missingFields.filter(f => f !== "Дельта"),
                                    hasError: newErrors[index].missingFields.filter(f => f !== "Дельта").length > 0,
                                  };
                                  if (!newErrors[index].hasError) {
                                    delete newErrors[index];
                                  }
                                  onValidationErrorsChange(newErrors);
                                }
                              }
                            }}
                            className={`w-full px-3 py-2.5 bg-zinc-800 rounded-lg text-white text-sm focus:outline-none focus:ring-2 ${
                              strategyValidationErrors[index]?.missingFields?.includes("Дельта")
                                ? "border-2 border-red-500 focus:ring-red-500 focus:border-red-500"
                                : "border-2 border-amber-600/50 focus:ring-amber-500 focus:border-amber-500"
                            }`}
                            placeholder="0.3"
                          />
                          <p className={`text-[11px] mt-1 ${
                            strategyValidationErrors[index]?.missingFields?.includes("Дельта")
                              ? "text-red-300/70"
                              : "text-amber-300/70"
                          }`}>
                            Минимальная дельта стрелы (от 0.01% до 100%)
                          </p>
                        </div>
                        
                        {/* Объём */}
                        <div>
                          <label className={`block text-xs font-medium mb-2 ${
                            strategyValidationErrors[index]?.missingFields?.includes("Объём") 
                              ? "text-red-300" 
                              : "text-amber-200"
                          }`}>
                            Объём (USDT) <span className="text-red-400">*</span>
                          </label>
                          <input
                            type="number"
                            step="0.01"
                            min="1"
                            value={
                              template.conditions.find(c => c.type === "volume")?.value !== undefined
                                ? template.conditions.find(c => c.type === "volume")?.value
                                : ""
                            }
                            onChange={(e) => {
                              const newTemplates = [...conditionalTemplates];
                              const val = e.target.value === "" ? undefined : parseFloat(e.target.value);
                              const volumeIndex = newTemplates[index].conditions.findIndex(c => c.type === "volume");
                              if (volumeIndex >= 0) {
                                newTemplates[index].conditions[volumeIndex].value = val !== undefined && !isNaN(val) ? Math.max(1, val) : undefined;
                              } else {
                                newTemplates[index].conditions.unshift({
                                  type: "volume",
                                  value: val !== undefined && !isNaN(val) ? Math.max(1, val) : undefined,
                                });
                              }
                              const updatedDescription = generateTemplateDescription(newTemplates[index]);
                              newTemplates[index].description = updatedDescription;
                              onTemplatesChange(newTemplates);
                              
                              if (val !== undefined && !isNaN(val)) {
                                const newErrors = { ...strategyValidationErrors };
                                if (newErrors[index] && newErrors[index].missingFields) {
                                  newErrors[index] = {
                                    ...newErrors[index],
                                    missingFields: newErrors[index].missingFields.filter(f => f !== "Объём"),
                                    hasError: newErrors[index].missingFields.filter(f => f !== "Объём").length > 0,
                                  };
                                  if (!newErrors[index].hasError) {
                                    delete newErrors[index];
                                  }
                                  onValidationErrorsChange(newErrors);
                                }
                              }
                            }}
                            className={`w-full px-3 py-2.5 bg-zinc-800 rounded-lg text-white text-sm focus:outline-none focus:ring-2 ${
                              strategyValidationErrors[index]?.missingFields?.includes("Объём")
                                ? "border-2 border-red-500 focus:ring-red-500 focus:border-red-500"
                                : "border-2 border-amber-600/50 focus:ring-amber-500 focus:border-amber-500"
                            }`}
                            placeholder="1000000"
                          />
                          <p className={`text-[11px] mt-1 ${
                            strategyValidationErrors[index]?.missingFields?.includes("Объём")
                              ? "text-red-300/70"
                              : "text-amber-300/70"
                          }`}>
                            Минимальный объём стрелы (от 1 USDT)
                          </p>
                        </div>
                        
                        {/* Тень */}
                        <div>
                          <label className={`block text-xs font-medium mb-2 ${
                            strategyValidationErrors[index]?.missingFields?.includes("Тень") 
                              ? "text-red-300" 
                              : "text-amber-200"
                          }`}>
                            Тень (%) <span className="text-red-400">*</span>
                          </label>
                          <div className="grid grid-cols-2 gap-2">
                            <div>
                              <label className={`block text-[11px] mb-1 ${
                                strategyValidationErrors[index]?.missingFields?.includes("Тень")
                                  ? "text-red-300/70"
                                  : "text-amber-300/70"
                              }`}>От</label>
                              <input
                                type="number"
                                step="0.1"
                                min="0"
                                max="100"
                                value={
                                  template.conditions.find(c => c.type === "wick_pct")?.valueMin !== undefined
                                    ? template.conditions.find(c => c.type === "wick_pct")?.valueMin
                                    : ""
                                }
                                onChange={(e) => {
                                  const newTemplates = [...conditionalTemplates];
                                  const val = e.target.value === "" ? undefined : parseFloat(e.target.value);
                                  const wickIndex = newTemplates[index].conditions.findIndex(c => c.type === "wick_pct");
                                  if (wickIndex >= 0) {
                                    newTemplates[index].conditions[wickIndex].valueMin = val !== undefined && !isNaN(val) ? Math.max(0, Math.min(100, val)) : undefined;
                                  } else {
                                    newTemplates[index].conditions.unshift({
                                      type: "wick_pct",
                                      valueMin: val !== undefined && !isNaN(val) ? Math.max(0, Math.min(100, val)) : undefined,
                                      valueMax: null,
                                    });
                                  }
                                  const updatedDescription = generateTemplateDescription(newTemplates[index]);
                                  newTemplates[index].description = updatedDescription;
                                  onTemplatesChange(newTemplates);
                                  
                                  if (val !== undefined && !isNaN(val)) {
                                    const newErrors = { ...strategyValidationErrors };
                                    if (newErrors[index] && newErrors[index].missingFields) {
                                      newErrors[index] = {
                                        ...newErrors[index],
                                        missingFields: newErrors[index].missingFields.filter(f => f !== "Тень"),
                                        hasError: newErrors[index].missingFields.filter(f => f !== "Тень").length > 0,
                                      };
                                      if (!newErrors[index].hasError) {
                                        delete newErrors[index];
                                      }
                                      onValidationErrorsChange(newErrors);
                                    }
                                  }
                                }}
                                className={`w-full px-3 py-2 rounded-lg text-white text-sm text-center focus:outline-none focus:ring-2 ${
                                  strategyValidationErrors[index]?.missingFields?.includes("Тень")
                                    ? "bg-zinc-800 border-2 border-red-500 focus:ring-red-500 focus:border-red-500"
                                    : "bg-zinc-800 border-2 border-amber-600/50 focus:ring-amber-500 focus:border-amber-500"
                                }`}
                                placeholder="0"
                              />
                            </div>
                            <div>
                              <label className={`block text-[11px] mb-1 ${
                                strategyValidationErrors[index]?.missingFields?.includes("Тень")
                                  ? "text-red-300/70"
                                  : "text-amber-300/70"
                              }`}>До</label>
                              <input
                                type="text"
                                value={
                                  template.conditions.find(c => c.type === "wick_pct")?.valueMax === null || 
                                  template.conditions.find(c => c.type === "wick_pct")?.valueMax === undefined
                                    ? "∞"
                                    : String(template.conditions.find(c => c.type === "wick_pct")?.valueMax ?? "")
                                }
                                onChange={(e) => {
                                  const newTemplates = [...conditionalTemplates];
                                  const wickIndex = newTemplates[index].conditions.findIndex(c => c.type === "wick_pct");
                                  if (e.target.value === "∞" || e.target.value === "" || e.target.value.trim() === "") {
                                    if (wickIndex >= 0) {
                                      newTemplates[index].conditions[wickIndex].valueMax = null;
                                    } else {
                                      newTemplates[index].conditions.unshift({
                                        type: "wick_pct",
                                        valueMin: 0,
                                        valueMax: null,
                                      });
                                    }
                                  } else {
                                    const numValue = parseFloat(e.target.value);
                                    if (!isNaN(numValue)) {
                                      if (wickIndex >= 0) {
                                        newTemplates[index].conditions[wickIndex].valueMax = Math.max(0, Math.min(100, numValue));
                                      } else {
                                        newTemplates[index].conditions.unshift({
                                          type: "wick_pct",
                                          valueMin: 0,
                                          valueMax: Math.max(0, Math.min(100, numValue)),
                                        });
                                      }
                                    }
                                  }
                                  const updatedDescription = generateTemplateDescription(newTemplates[index]);
                                  newTemplates[index].description = updatedDescription;
                                  onTemplatesChange(newTemplates);
                                }}
                                onBlur={(e) => {
                                  if (e.target.value === "" || e.target.value.trim() === "") {
                                    const newTemplates = [...conditionalTemplates];
                                    const wickIndex = newTemplates[index].conditions.findIndex(c => c.type === "wick_pct");
                                    if (wickIndex >= 0) {
                                      newTemplates[index].conditions[wickIndex].valueMax = null;
                                      const updatedDescription = generateTemplateDescription(newTemplates[index]);
                                      newTemplates[index].description = updatedDescription;
                                      onTemplatesChange(newTemplates);
                                    }
                                  }
                                }}
                                placeholder="∞"
                                className={`w-full px-3 py-2 rounded-lg text-white text-sm text-center focus:outline-none focus:ring-2 ${
                                  strategyValidationErrors[index]?.missingFields?.includes("Тень")
                                    ? "bg-zinc-800 border-2 border-red-500 focus:ring-red-500 focus:border-red-500"
                                    : "bg-zinc-800 border-2 border-amber-600/50 focus:ring-amber-500 focus:border-amber-500"
                                }`}
                                title="Введите число от 0 до 100 или оставьте ∞ для бесконечности"
                              />
                            </div>
                          </div>
                          <p className={`text-[11px] mt-1 ${
                            strategyValidationErrors[index]?.missingFields?.includes("Тень")
                              ? "text-red-300/70"
                              : "text-amber-300/70"
                          }`}>
                            Диапазон тени свечи (от 0% до 100%)
                          </p>
                        </div>
                      </div>
                      
                      <div className="mt-4 p-3 bg-zinc-900/50 rounded-lg border border-zinc-700/50">
                        <p className="text-xs text-amber-200/80">
                          <strong className="text-amber-300">💡 Пример:</strong> Если указать дельта ≥ 0.3%, объём ≥ 1,000,000 USDT и тень от 0% до ∞, 
                          стратегия будет детектировать только стрелы с дельтой не менее 0.3%, объёмом не менее 1 млн USDT и любой тенью.
                        </p>
                      </div>
                    </div>
                  )}

                  {/* Условия */}
                  <div className="mb-4">
                    <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-2 mb-3">
                      <div>
                        <p className="text-xs font-medium text-zinc-200">
                          Условия <span className="text-[11px] text-zinc-400">(все должны выполняться)</span>
                        </p>
                        <p className="text-[11px] text-zinc-500 mt-0.5">
                          Можно добавить несколько строк с разными параметрами (объём, дельта, серия и т.д.).
                        </p>
                      </div>
                      <button
                        onClick={() => {
                          const newTemplates = [...conditionalTemplates];
                          newTemplates[index].conditions.push({
                            type: "volume",
                            value: 0,
                          });
                          onTemplatesChange(newTemplates);
                        }}
                        className="inline-flex items-center justify-center px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 text-white text-xs font-medium rounded-lg border border-zinc-700 hover:border-emerald-500/60 transition-colors"
                      >
                        <span className="mr-1 text-emerald-400 text-sm">+</span>
                        Добавить условие
                      </button>
                    </div>
                    
                    <div className="space-y-3">
                      {template.conditions.map((condition, condIndex) => {
                        const handleConditionChange = (condIndex: number, cond: ConditionalTemplate["conditions"][0]) => {
                          const newTemplates = [...conditionalTemplates];
                          newTemplates[index].conditions[condIndex] = cond;
                          const updatedDescription = generateTemplateDescription(newTemplates[index]);
                          newTemplates[index].description = updatedDescription;
                          onTemplatesChange(newTemplates);
                        };

                        const handleConditionDelete = (condIndex: number) => {
                          const newTemplates = [...conditionalTemplates];
                          newTemplates[index].conditions = newTemplates[index].conditions.filter((_, i) => i !== condIndex);
                          const updatedDescription = generateTemplateDescription(newTemplates[index]);
                          newTemplates[index].description = updatedDescription;
                          onTemplatesChange(newTemplates);
                        };

                        return (
                          <div key={condIndex} className="bg-zinc-900/50 border border-zinc-700/50 rounded-lg p-3 md:p-4 max-w-4xl">
                            <div className="flex gap-2 items-end mb-2">
                              <div className="w-full md:w-56">
                                <label className="block text-xs text-zinc-400 mb-1">Параметр</label>
                                <select
                                  value={condition.type}
                                  onChange={(e) => {
                                    const newTemplates = [...conditionalTemplates];
                                    const newType = e.target.value as ConditionalTemplate["conditions"][0]["type"];
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

                                    newTemplates[index].conditions[condIndex] = newCondition;
                                    const updatedDescription = generateTemplateDescription(newTemplates[index]);
                                    newTemplates[index].description = updatedDescription;
                                    onTemplatesChange(newTemplates);
                                  }}
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
                                        handleConditionChange(condIndex, { ...condition, count: isNaN(val) ? 2 : Math.max(2, val) });
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
                                        handleConditionChange(condIndex, { ...condition, timeWindowSeconds: isNaN(val) ? 300 : Math.max(60, val) });
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
                                    value={condition.valueMin !== undefined ? condition.valueMin : (condition.value !== undefined ? condition.value : "")}
                                    onChange={(e) => {
                                      const val = e.target.value === "" ? 0 : parseFloat(e.target.value);
                                      handleConditionChange(condIndex, { ...condition, valueMin: isNaN(val) ? 0 : val, valueMax: null });
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
                                    onChange={(e) => handleConditionChange(condIndex, { ...condition, symbol: e.target.value.toUpperCase().trim() })}
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
                                          handleConditionChange(condIndex, { ...condition, valueMin: isNaN(val) ? 0 : Math.max(0, Math.min(100, val)) });
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
                                            handleConditionChange(condIndex, { ...condition, valueMax: null });
                                          } else {
                                            const numValue = parseFloat(e.target.value);
                                            if (!isNaN(numValue)) {
                                              handleConditionChange(condIndex, { ...condition, valueMax: Math.max(0, Math.min(100, numValue)) });
                                            }
                                          }
                                        }}
                                        onBlur={(e) => {
                                          if (e.target.value === "" || e.target.value.trim() === "") {
                                            handleConditionChange(condIndex, { ...condition, valueMax: null });
                                          }
                                        }}
                                        placeholder="∞"
                                        className="w-full px-3 py-2.5 bg-zinc-700 border border-zinc-600 rounded-lg text-white text-sm text-center focus:outline-none focus:ring-2 focus:ring-emerald-500"
                                        title="Введите число от 0 до 100 или оставьте ∞ для бесконечности"
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
                                    onChange={(e) => handleConditionChange(condIndex, { ...condition, exchange_market: e.target.value })}
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
                                    onChange={(e) => handleConditionChange(condIndex, { ...condition, direction: e.target.value as "up" | "down" })}
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
                                      handleConditionChange(condIndex, { ...condition, value: isNaN(val) ? 0 : val });
                                    }}
                                    className="w-full px-3 py-2.5 bg-zinc-700 border border-zinc-600 rounded-lg text-white text-sm text-center focus:outline-none focus:ring-2 focus:ring-emerald-500"
                                    placeholder="0"
                                  />
                                </div>
                              )}

                              {template.conditions.length > 1 && (
                                <button
                                  onClick={() => handleConditionDelete(condIndex)}
                                  className="px-2 py-2 bg-red-600/50 hover:bg-red-600 text-white text-xs font-medium rounded transition-colors mb-0.5"
                                  title="Удалить условие"
                                >
                                  ×
                                </button>
                              )}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>

                  {/* Редактор шаблона сообщения для стратегии */}
                  <div className="mb-4">
                    <div className="flex items-center justify-between mb-2">
                      <label className="block text-xs text-zinc-400">
                        Шаблон сообщения
                      </label>
                    </div>

                    {/* Доступные вставки для стратегии */}
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
                            onClick={() => insertPlaceholderIntoStrategy(index, placeholder.friendly)}
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

                    <div className="relative">
                      <div
                        id={`conditionalTemplate_${index}`}
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

                          const newTemplates = [...conditionalTemplates];
                          newTemplates[index].template = convertToTechnicalKeys(textContent);
                          onTemplatesChange(newTemplates);

                          setTimeout(() => {
                            isConditionalUserEditingRef.current = false;
                          }, 150);
                        }}
                        className="w-full min-h-32 px-4 py-3 bg-zinc-800 border-2 border-zinc-600 rounded-lg text-white font-mono text-sm focus:outline-none focus:ring-2 focus:border-emerald-500 focus:ring-emerald-500 resize-none overflow-y-auto template-editor cursor-text"
                        style={{ whiteSpace: "pre-wrap" }}
                      />
                    </div>

                    {/* Превью сообщения для стратегии */}
                    <div className="mt-3">
                      <label className="block text-xs font-medium text-zinc-300 mb-2">
                        Превью сообщения в Telegram
                      </label>
                      <div className="bg-zinc-800 border-2 border-zinc-700 rounded-lg p-4 min-h-[100px]">
                        <div 
                          className="text-white text-sm whitespace-pre-wrap font-sans"
                          dangerouslySetInnerHTML={{ __html: generateMessagePreview(template.template || "").replace(/\n/g, '<br>') }}
                        />
                      </div>
                      <p className="text-xs text-zinc-500 mt-2">
                        💡 Это пример того, как будет выглядеть сообщение в Telegram с примерами значений
                      </p>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
          
          <div className="flex gap-3">
            <button
              onClick={handleAddStrategy}
              className="px-4 py-2 bg-zinc-700 hover:bg-zinc-600 text-white font-medium rounded-lg smooth-transition"
            >
              + Добавить стратегию
            </button>
            <button
              onClick={onSave}
              disabled={saving}
              className="px-4 py-2 bg-gradient-to-r from-emerald-500 to-emerald-600 hover:from-emerald-600 hover:to-emerald-700 text-white font-medium rounded-lg smooth-transition ripple hover-glow shadow-emerald disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {saving ? "Сохранение..." : "Сохранить стратегии"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

