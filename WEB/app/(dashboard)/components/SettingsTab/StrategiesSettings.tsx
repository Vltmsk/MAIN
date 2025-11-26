"use client";

import { useState } from "react";
import { ConditionalTemplate } from "./types";
import { convertToTechnicalKeys } from "./utils/templateUtils";
import { placeholderMap } from "./utils/placeholderMap";
import StrategiesTreeView from "./StrategiesTreeView";
import StrategyDetailsPanel from "./StrategyDetailsPanel";
import StrategyActionsPanel from "./StrategyActionsPanel";

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
  setSaveMessage: (message: { type: "success" | "error"; text: string } | null) => void;
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
  setSaveMessage,
  onUnsavedChangesChange,
}: StrategiesSettingsProps) {
  // Состояния для управления интерфейсом
  const [selectedStrategyIndex, setSelectedStrategyIndex] = useState<number | null>(null);
  const [selectedStrategies, setSelectedStrategies] = useState<Set<number>>(new Set());
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState<boolean>(false);

  // Функция для работы с шаблонами (используется для вставки placeholder в старый код, если он еще используется)
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

  // Функция для вставки placeholder в шаблон (будет использоваться в центральной панели на этапе 3)
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
      setHasUnsavedChanges(true);
    }
  };

  // Обработчики для работы с выбранными стратегиями
  const handleStrategySelect = (index: number) => {
    setSelectedStrategyIndex(index);
    // НЕ сбрасываем hasUnsavedChanges при переключении стратегий
    // Флаг должен сбрасываться только после сохранения или при закрытии стратегии
  };

  const handleStrategyToggle = (index: number) => {
    setSelectedStrategies((prev) => {
      const newSet = new Set(prev);
      if (newSet.has(index)) {
        newSet.delete(index);
      } else {
        newSet.add(index);
      }
      return newSet;
    });
  };

  const handleAddStrategy = () => {
    const extractedText = extractTextFromEditor();
    const technicalTemplate = convertToTechnicalKeys(extractedText || messageTemplate);
    const newStrategy: ConditionalTemplate = {
      name: undefined,
      enabled: true,
      useGlobalFilters: true,
      conditions: [{
        type: "volume",
        value: 0,
      }],
      template: technicalTemplate,
    };
    
    const newTemplates = [...conditionalTemplates, newStrategy];
    onTemplatesChange(newTemplates);
    
    // Автоматически выбираем новую стратегию
    const newIndex = newTemplates.length - 1;
    setSelectedStrategyIndex(newIndex);
    setSelectedStrategies((prev) => new Set(prev).add(newIndex));
  };

  const handleDeleteStrategy = (index: number) => {
    const strategy = conditionalTemplates[index];
    const strategyName = strategy.name || `Стратегия #${index + 1}`;
    
    const confirmMessage = `Вы действительно хотите удалить стратегию "${strategyName}"?\n\nЭто действие нельзя отменить.`;
    
    if (confirm(confirmMessage)) {
      const newTemplates = conditionalTemplates.filter((_, i) => i !== index);
      onTemplatesChange(newTemplates);
      
      // Обновляем индексы выбранных стратегий
      const newSelectedStrategies = new Set<number>();
      selectedStrategies.forEach((selectedIndex) => {
        if (selectedIndex < index) {
          newSelectedStrategies.add(selectedIndex);
        } else if (selectedIndex > index) {
          newSelectedStrategies.add(selectedIndex - 1);
        }
        // Если selectedIndex === index, то эта стратегия удалена, не добавляем её
      });
      setSelectedStrategies(newSelectedStrategies);
      
      // Если удаляемая стратегия была выбрана, сбрасываем выбор
      if (selectedStrategyIndex === index) {
        setSelectedStrategyIndex(null);
      } else if (selectedStrategyIndex !== null && selectedStrategyIndex > index) {
        // Если выбранная стратегия была после удаляемой, уменьшаем её индекс
        setSelectedStrategyIndex(selectedStrategyIndex - 1);
      }
      
      setHasUnsavedChanges(true);
      setSaveMessage({
        type: "success",
        text: `Стратегия "${strategyName}" удалена. Не забудьте сохранить изменения.`
      });
    }
  };

  return (
    <div className="h-[calc(100vh-200px)] flex flex-col gap-4">
      {/* Верхняя часть: левая и центральная панели (на планшетах и десктопе) */}
      <div className="flex flex-col lg:flex-row gap-4 flex-1 min-h-0">
        {/* Левая панель - Дерево стратегий (~25%) */}
        <div className="w-full lg:w-1/4 flex-shrink-0">
          <StrategiesTreeView
            strategies={conditionalTemplates}
            selectedStrategyIndex={selectedStrategyIndex}
            selectedStrategies={selectedStrategies}
            onStrategySelect={handleStrategySelect}
            onStrategyToggle={handleStrategyToggle}
            generateTemplateDescription={generateTemplateDescription}
          />
        </div>

        {/* Центральная панель - Детали стратегии (~50% на десктопе, 100% на планшете) */}
        <div className="flex-1 bg-zinc-900 border border-zinc-800 rounded-xl p-6 overflow-y-auto min-h-0">
          {selectedStrategyIndex !== null && conditionalTemplates[selectedStrategyIndex] ? (
            <StrategyDetailsPanel
              strategy={conditionalTemplates[selectedStrategyIndex]}
              strategyIndex={selectedStrategyIndex}
              strategyValidationErrors={strategyValidationErrors[selectedStrategyIndex]}
              isConditionalUserEditingRef={isConditionalUserEditingRef}
              onStrategyChange={(updatedStrategy) => {
                const newTemplates = [...conditionalTemplates];
                newTemplates[selectedStrategyIndex] = updatedStrategy;
                onTemplatesChange(newTemplates);
                setHasUnsavedChanges(true);
              }}
              onValidationErrorsChange={(errors) => {
                if (errors) {
                  onValidationErrorsChange({
                    ...strategyValidationErrors,
                    [selectedStrategyIndex]: errors,
                  });
                } else {
                  const newErrors = { ...strategyValidationErrors };
                  delete newErrors[selectedStrategyIndex];
                  onValidationErrorsChange(newErrors);
                }
              }}
              generateTemplateDescription={generateTemplateDescription}
              onUnsavedChanges={() => setHasUnsavedChanges(true)}
            />
          ) : (
            <div className="flex items-center justify-center h-full">
              <div className="text-center">
                <svg
                  className="w-16 h-16 text-zinc-600 mx-auto mb-4"
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
                <p className="text-zinc-400">Выберите стратегию для просмотра деталей</p>
              </div>
            </div>
          )}
        </div>

        {/* Правая панель - Действия (~25% на десктопе, скрыта на планшетах) */}
        <div className="hidden xl:block w-1/4 flex-shrink-0">
          <StrategyActionsPanel
            conditionalTemplates={conditionalTemplates}
            selectedStrategies={selectedStrategies}
            selectedStrategyIndex={selectedStrategyIndex}
            hasUnsavedChanges={hasUnsavedChanges}
            saving={saving}
            onTemplatesChange={onTemplatesChange}
            onSave={onSave}
            onAddStrategy={handleAddStrategy}
            onDeleteStrategy={handleDeleteStrategy}
            onClose={() => {
              setSelectedStrategyIndex(null);
              setHasUnsavedChanges(false);
            }}
            setHasUnsavedChanges={setHasUnsavedChanges}
            setSaveMessage={setSaveMessage}
          />
        </div>
      </div>

      {/* Нижняя часть: правая панель на планшетах (показывается только на lg и xl, но не на xl) */}
      <div className="xl:hidden">
        <StrategyActionsPanel
          conditionalTemplates={conditionalTemplates}
          selectedStrategies={selectedStrategies}
          selectedStrategyIndex={selectedStrategyIndex}
          hasUnsavedChanges={hasUnsavedChanges}
          saving={saving}
          onTemplatesChange={onTemplatesChange}
          onSave={onSave}
          onAddStrategy={handleAddStrategy}
          onDeleteStrategy={handleDeleteStrategy}
          onClose={() => {
            setSelectedStrategyIndex(null);
            setHasUnsavedChanges(false);
          }}
          setHasUnsavedChanges={setHasUnsavedChanges}
          setSaveMessage={setSaveMessage}
        />
      </div>
    </div>
  );
}
