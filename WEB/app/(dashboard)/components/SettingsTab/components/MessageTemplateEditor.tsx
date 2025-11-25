"use client";

import { useEffect, useRef } from "react";
import { generateMessagePreview } from "../utils/templateUtils";
import { placeholderMap } from "../utils/placeholderMap";

interface MessageTemplateEditorProps {
  template: string;
  timezone: string;
  onChange: (template: string) => void;
  onTimezoneChange: (timezone: string) => void;
  editorId?: string;
  isUserEditingRef?: React.MutableRefObject<boolean>;
}

export default function MessageTemplateEditor({
  template,
  timezone,
  onChange,
  onTimezoneChange,
  editorId = "messageTemplate",
  isUserEditingRef,
}: MessageTemplateEditorProps) {
  const editorRef = useRef<HTMLDivElement>(null);

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

  const extractText = (): string => {
    const editor = editorRef.current;
    if (!editor) return template;
    
    const content = editor.innerHTML;
    const tempDiv = document.createElement('div');
    tempDiv.innerHTML = content;
    
    const blocks = tempDiv.querySelectorAll('[data-placeholder-key]');
    let textContent = content;
    blocks.forEach((block) => {
      const key = block.getAttribute('data-placeholder-key');
      if (key) {
        const blockHTML = block.outerHTML.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        textContent = textContent.replace(new RegExp(blockHTML, 'g'), key);
      }
    });
    
    textContent = textContent.replace(/<br\s*\/?>/gi, '\n');
    return textContent;
  };

  const insertPlaceholder = (placeholder: string) => {
    const editor = editorRef.current;
    if (!editor) return;
    
    const selection = window.getSelection();
    if (!selection || selection.rangeCount === 0) {
      return;
    }
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
    const block = document.createElement('span');
    block.className = 'inline-flex items-center gap-1.5 px-2 py-1 mx-0.5 bg-emerald-500/20 border border-emerald-500/50 rounded text-emerald-300 text-xs font-medium cursor-default';
    block.setAttribute('data-placeholder-key', placeholder);
    block.setAttribute('contenteditable', 'false');
    block.innerHTML = `<svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 8h10M7 12h4m1 8l-4-4H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-3l-4 4z"></path></svg><span>${label}</span>`;
    
    range.insertNode(block);
    const newRange = document.createRange();
    newRange.setStartAfter(block);
    newRange.collapse(true);
    selection.removeAllRanges();
    selection.addRange(newRange);
    
    if (isUserEditingRef) isUserEditingRef.current = true;
    onChange(extractText());
  };

  // Инициализация редактора
  useEffect(() => {
    if (!isUserEditingRef?.current && editorRef.current) {
      const html = convertTemplateToHTML(template);
      if (editorRef.current.innerHTML !== html) {
        editorRef.current.innerHTML = html;
      }
    }
  }, [template, isUserEditingRef]);

  return (
    <div>
      {/* Список доступных вставок */}
      <div className="mb-4">
        <h3 className="text-sm font-medium text-zinc-300 mb-3">Доступные вставки:</h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
          {Object.entries(placeholderMap).map(([friendly, technical]) => {
            const labels: Record<string, string> = {
              "[[Дельта стрелы]]": "Дельта стрелы",
              "[[Направление]]": "Направление",
              "[[Биржа и тип рынка]]": "Биржа и тип рынка",
              "[[Торговая пара]]": "Торговая пара",
              "[[Объём стрелы]]": "Объём стрелы",
              "[[Тень свечи]]": "Тень свечи",
              "[[Время детекта]]": "Время детекта",
              "[[Временная метка]]": "Временная метка",
            };
            const label = labels[friendly] || friendly;
            return (
              <button
                key={friendly}
                onClick={() => insertPlaceholder(friendly)}
                className="text-left px-3 py-2 bg-zinc-800 hover:bg-zinc-700 border-2 border-zinc-600 hover:border-emerald-500 rounded-lg transition-all cursor-pointer text-sm"
                type="button"
              >
                {label}
              </button>
            );
          })}
        </div>
      </div>

      {/* Редактор */}
      <div className="mb-4">
        <label className="block text-sm font-medium text-zinc-300 mb-2">Шаблон сообщения</label>
        <div
          ref={editorRef}
          id={editorId}
          contentEditable
          suppressContentEditableWarning
          onInput={(e) => {
            if (isUserEditingRef) isUserEditingRef.current = true;
            onChange(extractText());
          }}
          className="w-full min-h-64 px-4 py-3 bg-zinc-800 border-2 border-zinc-600 rounded-lg text-white font-mono text-sm focus:outline-none focus:ring-2 focus:border-emerald-500 focus:ring-emerald-500 overflow-y-auto template-editor cursor-text"
          style={{ whiteSpace: 'pre-wrap' }}
        />
      </div>

      {/* Превью */}
      <div className="mb-4">
        <label className="block text-xs font-medium text-zinc-300 mb-2">Превью сообщения</label>
        <div className="bg-zinc-800 border-2 border-zinc-700 rounded-lg p-4 min-h-[100px]">
          <div 
            className="text-white text-sm whitespace-pre-wrap font-sans"
            dangerouslySetInnerHTML={{ __html: generateMessagePreview(template).replace(/\n/g, '<br>') }}
          />
        </div>
      </div>
    </div>
  );
}

