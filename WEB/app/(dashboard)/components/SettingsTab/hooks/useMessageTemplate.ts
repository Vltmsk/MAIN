"use client";

import { useState, useCallback, useRef } from "react";
import { convertToTechnicalKeys, convertToFriendlyKeys, generateMessagePreview } from "../utils/templateUtils";
import { placeholderMap } from "../utils/placeholderMap";

export function useMessageTemplate() {
  const [messageTemplate, setMessageTemplate] = useState<string>(`🚨 <b>НАЙДЕНА СТРЕЛА!</b> [[Направление]]

<b>[[Биржа и тип рынка]]</b>
💰 <b>[[Торговая пара]]</b>

📊 <b>Метрики:</b>
• Изменение: <b>[[Дельта стрелы]]</b> [[Направление]]
• Объём: <b>[[Объём стрелы]] USDT</b>
• Тень: <b>[[Тень свечи]]</b>

⏰ <b>[[Время детекта]]</b>`);
  const [timezone, setTimezone] = useState<string>("UTC");
  const [isMessageFormatExpanded, setIsMessageFormatExpanded] = useState(false);
  const [contextMenu, setContextMenu] = useState<{
    visible: boolean;
    x: number;
    y: number;
    selectedText: string;
    selectionStart: number;
    selectionEnd: number;
  } | null>(null);
  
  // Ref для отслеживания редактирования пользователем
  const isUserEditingRef = useRef(false);

  // Преобразование шаблона в HTML для отображения в contentEditable
  const convertTemplateToHTML = useCallback((template: string): string => {
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
  }, []);

  // Извлечение текста из редактора
  const extractTextFromEditor = useCallback((editorId: string = "messageTemplate"): string => {
    const editor = document.getElementById(editorId) as HTMLElement;
    if (!editor) return messageTemplate;
    
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
  }, [messageTemplate]);

  // Вставка плейсхолдера в редактор
  const insertPlaceholder = useCallback((placeholder: string, editorId: string = "messageTemplate") => {
    const editor = document.getElementById(editorId) as HTMLElement;
    if (!editor) return;
    
    const selection = window.getSelection();
    if (!selection || selection.rangeCount === 0) return;
    
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
    
    // Создаем красивый визуальный блок для вставки
    const block = document.createElement('span');
    block.className = 'inline-flex items-center gap-1.5 px-2 py-1 mx-0.5 bg-emerald-500/20 border border-emerald-500/50 rounded text-emerald-300 text-xs font-medium cursor-default';
    block.setAttribute('data-placeholder-key', placeholder);
    block.setAttribute('contenteditable', 'false');
    block.innerHTML = `
      <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 8h10M7 12h4m1 8l-4-4H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-3l-4 4z"></path>
      </svg>
      <span>${label}</span>
    `;
    
    range.insertNode(block);
    
    // Устанавливаем курсор после блока
    const newRange = document.createRange();
    newRange.setStartAfter(block);
    newRange.collapse(true);
    selection.removeAllRanges();
    selection.addRange(newRange);
    
    // Обновляем состояние
    const updatedContent = editor.innerHTML;
    const tempDiv = document.createElement('div');
    tempDiv.innerHTML = updatedContent;
    const blocks = tempDiv.querySelectorAll('[data-placeholder-key]');
    let textContent = updatedContent;
    blocks.forEach((b) => {
      const key = b.getAttribute('data-placeholder-key');
      if (key) {
        textContent = textContent.replace(b.outerHTML, key);
      }
    });
    isUserEditingRef.current = true;
    setMessageTemplate(textContent);
  }, []);

  // Обработчик контекстного меню
  const handleContextMenu = useCallback((e: React.MouseEvent<HTMLElement>) => {
    e.preventDefault();
    const editor = e.currentTarget;
    const selection = window.getSelection();
    const selectedText = selection ? selection.toString() : '';

    const rect = editor.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    setContextMenu({
      visible: true,
      x: x,
      y: y,
      selectedText,
      selectionStart: 0,
      selectionEnd: 0,
    });
  }, []);

  // Функции форматирования текста
  const applyFormatting = useCallback((tag: string, closingTag: string, editorId: string = "messageTemplate") => {
    const editor = document.getElementById(editorId) as HTMLElement;
    if (!editor) return;

    const selection = window.getSelection();
    if (!selection || selection.rangeCount === 0) return;

    const range = selection.getRangeAt(0);
    const selectedText = range.toString();

    if (selectedText) {
      const wrapper = document.createElement('span');
      wrapper.innerHTML = tag + selectedText + closingTag;
      range.deleteContents();
      range.insertNode(wrapper);
      
      const content = editor.innerHTML;
      const tempDiv = document.createElement('div');
      tempDiv.innerHTML = content;
      const blocks = tempDiv.querySelectorAll('[data-placeholder-key]');
      let textContent = content;
      blocks.forEach((b) => {
        const key = b.getAttribute('data-placeholder-key');
        if (key) {
          textContent = textContent.replace(b.outerHTML, key);
        }
      });
      isUserEditingRef.current = true;
      setMessageTemplate(textContent);
    }
    setContextMenu(null);
  }, []);

  const formatBold = useCallback(() => {
    document.execCommand('bold', false);
    setContextMenu(null);
  }, []);

  const formatItalic = useCallback(() => {
    document.execCommand('italic', false);
    setContextMenu(null);
  }, []);

  const formatUnderline = useCallback(() => {
    document.execCommand('underline', false);
    setContextMenu(null);
  }, []);

  const formatStrikethrough = useCallback(() => {
    document.execCommand('strikeThrough', false);
    setContextMenu(null);
  }, []);

  const formatCode = useCallback(() => applyFormatting("<code>", "</code>"), [applyFormatting]);
  const formatSpoiler = useCallback(() => applyFormatting("<spoiler>", "</spoiler>"), [applyFormatting]);

  // Обработчик клавиатуры
  const handleKeyDown = useCallback((e: React.KeyboardEvent<HTMLElement>) => {
    const isCtrl = e.ctrlKey || e.metaKey;
    const isShift = e.shiftKey;

    if (isCtrl && !isShift && e.key === 'b') {
      e.preventDefault();
      formatBold();
    } else if (isCtrl && !isShift && e.key === 'i') {
      e.preventDefault();
      formatItalic();
    } else if (isCtrl && !isShift && e.key === 'u') {
      e.preventDefault();
      formatUnderline();
    } else if (isCtrl && isShift && e.key === 'X') {
      e.preventDefault();
      formatStrikethrough();
    } else if (isCtrl && isShift && e.key === 'M') {
      e.preventDefault();
      formatCode();
    } else if (isCtrl && isShift && e.key === 'P') {
      e.preventDefault();
      formatSpoiler();
    }
  }, [formatBold, formatItalic, formatUnderline, formatStrikethrough, formatCode, formatSpoiler]);

  return {
    // Состояния
    messageTemplate,
    timezone,
    isMessageFormatExpanded,
    contextMenu,
    isUserEditingRef,
    // Сеттеры
    setMessageTemplate,
    setTimezone,
    setIsMessageFormatExpanded,
    setContextMenu,
    // Функции
    convertTemplateToHTML,
    extractTextFromEditor,
    insertPlaceholder,
    generateMessagePreview,
    handleContextMenu,
    handleKeyDown,
    formatBold,
    formatItalic,
    formatUnderline,
    formatStrikethrough,
    formatCode,
    formatSpoiler,
  };
}

