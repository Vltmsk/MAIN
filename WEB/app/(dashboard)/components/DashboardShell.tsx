"use client";
import { useEffect, useState, useRef } from "react";
import { useRouter } from "next/navigation";
import dynamic from "next/dynamic";
import ChatIdHelp from "@/components/ChatIdHelp";

// Динамический импорт EmojiPicker для избежания SSR проблем
const EmojiPicker = dynamic(() => import("emoji-picker-react"), { ssr: false });

type Exchange = {
  name: string;
  market: "spot" | "linear";
  status: "active" | "inactive" | "problems";
  websocketInfo: string; // Например: "2 WS, 4 batches" или "5 WS"
  candles: number;
  lastUpdate: string;
  lastUpdateTimestamp?: number; // Timestamp последнего обновления в миллисекундах
  wsConnections: number;
  reconnects: number;
  tradingPairs: number; // торговые пары (active_symbols)
  tps: number; // T/s - тики в секунду (ticks per second)
};

export default function Dashboard() {
  const router = useRouter();
  const [activeTab, setActiveTab] = useState("monitoring");
  const [userLogin, setUserLogin] = useState("");
  const [loading, setLoading] = useState(true);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  
  const [exchanges, setExchanges] = useState<Exchange[]>([]);
  const [totalDetects, setTotalDetects] = useState(0);
  const [uptimeSeconds, setUptimeSeconds] = useState(0);
  const [startTime, setStartTime] = useState<number | null>(null);
  
  // Состояния для настроек Telegram
  const [telegramChatId, setTelegramChatId] = useState("");
  const [telegramBotToken, setTelegramBotToken] = useState("");
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [saveMessage, setSaveMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);
  const [isTelegramConfigured, setIsTelegramConfigured] = useState(false);
  const [isEditingTelegram, setIsEditingTelegram] = useState(true);
  
  // Состояния для валидации Telegram
  const [telegramChatIdError, setTelegramChatIdError] = useState<string>("");
  const [telegramBotTokenError, setTelegramBotTokenError] = useState<string>("");
  
  // Состояние для временной зоны
  const [timezone, setTimezone] = useState<string>("UTC");
  
  // Состояния для фильтров по биржам
  const [exchangeFilters, setExchangeFilters] = useState<Record<string, boolean>>({
    binance: true,
    bybit: true,
    bitget: true,
    gate: true,
    hyperliquid: true,
  });
  const [expandedExchanges, setExpandedExchanges] = useState<Record<string, boolean>>({});
  
  // Состояния для настроек Spot и Futures каждой биржи
  const [exchangeSettings, setExchangeSettings] = useState<Record<string, {
    spot: { enabled: boolean; delta: string; volume: string; shadow: string };
    futures: { enabled: boolean; delta: string; volume: string; shadow: string };
  }>>({
    binance: { spot: { enabled: true, delta: "0", volume: "0", shadow: "0" }, futures: { enabled: true, delta: "0", volume: "0", shadow: "0" } },
    bybit: { spot: { enabled: true, delta: "0", volume: "0", shadow: "0" }, futures: { enabled: true, delta: "0", volume: "0", shadow: "0" } },
    bitget: { spot: { enabled: true, delta: "0", volume: "0", shadow: "0" }, futures: { enabled: true, delta: "0", volume: "0", shadow: "0" } },
    gate: { spot: { enabled: true, delta: "0", volume: "0", shadow: "0" }, futures: { enabled: true, delta: "0", volume: "0", shadow: "0" } },
    hyperliquid: { spot: { enabled: true, delta: "0", volume: "0", shadow: "0" }, futures: { enabled: true, delta: "0", volume: "0", shadow: "0" } },
  });
  
  // Состояния для чёрного списка
  const [blacklist, setBlacklist] = useState<string[]>([]);
  const [newBlacklistSymbol, setNewBlacklistSymbol] = useState("");
  
  // Маппинг между понятными названиями и техническими ключами
  const placeholderMap: Record<string, string> = {
    "[[Дельта стрелы]]": "{delta_formatted}",
    "[[Направление]]": "{direction}",
    "[[Биржа и тип рынка]]": "{exchange_market}",
    "[[Торговая пара]]": "{symbol}",
    "[[Объём стрелы]]": "{volume_formatted}",
    "[[Тень свечи]]": "{wick_formatted}",
    "[[Время детекта]]": "{time}",
    "[[Временная метка]]": "{timestamp}",
  };

  // Обратный маппинг (технический ключ -> понятное название)
  const reversePlaceholderMap: Record<string, string> = Object.fromEntries(
    Object.entries(placeholderMap).map(([key, value]) => [value, key])
  );

  // Функция для преобразования понятных названий в технические ключи
  const convertToTechnicalKeys = (template: string): string => {
    let result = template;
    Object.entries(placeholderMap).forEach(([friendly, technical]) => {
      result = result.replace(new RegExp(friendly.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'g'), technical);
    });
    return result;
  };

  // Функция для преобразования технических ключей в понятные названия
  const convertToFriendlyNames = (template: string): string => {
    let result = template;
    Object.entries(reversePlaceholderMap).forEach(([technical, friendly]) => {
      result = result.replace(new RegExp(technical.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'g'), friendly);
    });
    return result;
  };

  // Функция для генерации описания шаблона на основе условий
  const generateTemplateDescription = (template: ConditionalTemplate): string => {
    if (!template.conditions || template.conditions.length === 0) {
      return "Нет условий";
    }

    const parts: string[] = [];

    template.conditions.forEach((condition) => {
      switch (condition.type) {
        case "volume":
          if (condition.value !== undefined) {
            parts.push(`Объём ≥ ${condition.value.toLocaleString()} USDT`);
          }
          break;
        case "delta":
          if (condition.valueMin !== undefined) {
            const min = condition.valueMin;
            const max = condition.valueMax;
            if (max === null || max === undefined) {
              parts.push(`Дельта ≥ ${min}%`);
            } else {
              parts.push(`Дельта ${min}% - ${max}%`);
            }
          } else if (condition.value !== undefined) {
            parts.push(`Дельта ≥ ${condition.value}%`);
          }
          break;
        case "series":
          if (condition.count !== undefined && condition.timeWindowSeconds !== undefined) {
            const minutes = Math.floor(condition.timeWindowSeconds / 60);
            parts.push(`Серия: ${condition.count} стрел за ${minutes} мин`);
          }
          break;
        case "symbol":
          if (condition.symbol) {
            parts.push(`Монета: ${condition.symbol}`);
          }
          break;
        case "wick_pct":
          if (condition.valueMin !== undefined) {
            const min = condition.valueMin;
            const max = condition.valueMax;
            if (max === null || max === undefined) {
              parts.push(`Тень ≥ ${min}%`);
            } else {
              parts.push(`Тень ${min}% - ${max}%`);
            }
          }
          break;
        case "exchange":
          if (condition.exchange) {
            const exchangeNames: Record<string, string> = {
              binance: "Binance",
              gate: "Gate",
              bitget: "Bitget",
              bybit: "Bybit",
              hyperliquid: "Hyperliquid",
            };
            parts.push(`Биржа: ${exchangeNames[condition.exchange] || condition.exchange}`);
          }
          break;
        case "market":
          if (condition.market) {
            const marketNames: Record<string, string> = {
              spot: "Spot",
              futures: "Futures",
              linear: "Linear",
            };
            parts.push(`Рынок: ${marketNames[condition.market] || condition.market}`);
          }
          break;
        case "direction":
          if (condition.direction) {
            parts.push(`Направление: ${condition.direction === "up" ? "Вверх ⬆️" : "Вниз ⬇️"}`);
          }
          break;
      }
    });

    if (parts.length === 0) {
      return "Нет условий";
    }

    return parts.join(" • ");
  };

  // Состояние для шаблона сообщения (отображается с понятными названиями)
  const [messageTemplate, setMessageTemplate] = useState<string>(`🚨 <b>НАЙДЕНА СТРЕЛА!</b> [[Направление]]

<b>[[Биржа и тип рынка]]</b>
💰 <b>[[Торговая пара]]</b>

📊 <b>Метрики:</b>
• Изменение: <b>[[Дельта стрелы]]</b> [[Направление]]
• Объём: <b>[[Объём стрелы]] USDT</b>
• Тень: <b>[[Тень свечи]]</b>

⏰ <b>[[Время детекта]]</b>`);
  
  // Состояние для условных шаблонов
  type ConditionalTemplate = {
    name?: string; // Название шаблона (опционально, для отображения)
    description?: string; // Автоматически сгенерированное описание (опционально)
    enabled?: boolean; // Включен/выключен (по умолчанию true)
    conditions: Array<{
      type: "volume" | "delta" | "series" | "symbol" | "wick_pct" | "exchange" | "market" | "direction";
      value?: number; // Для volume и старого формата delta
      valueMin?: number; // Для delta и wick_pct (минимальное значение)
      valueMax?: number | null; // Для delta и wick_pct (максимальное значение, null = бесконечность)
      count?: number; // Для series
      timeWindowSeconds?: number; // Для series
      symbol?: string; // Для symbol (нормализованный символ, например: ETH, BTC)
      exchange?: string; // Для exchange (название биржи: binance, gate, bitget, bybit, hyperliquid)
      market?: "spot" | "futures" | "linear"; // Для market (тип рынка)
      direction?: "up" | "down"; // Для direction (направление стрелы)
    }>;
    template: string;
    chatId?: string; // Telegram Chat ID для этого шаблона (опционально, если не указан - используется основной)
  };
  const [conditionalTemplates, setConditionalTemplates] = useState<ConditionalTemplate[]>([]);
  const [isConditionalTemplatesExpanded, setIsConditionalTemplatesExpanded] = useState(false);
  
  // Состояние для управления видимостью блока формата отправки детекта
  // Реф для отслеживания, что пользователь активно редактирует
  const isUserEditingRef = useRef(false);
  
  const [isMessageFormatExpanded, setIsMessageFormatExpanded] = useState(false);
  
  // Состояние для контекстного меню форматирования
  const [contextMenu, setContextMenu] = useState<{
    visible: boolean;
    x: number;
    y: number;
    selectedText: string;
    selectionStart: number;
    selectionEnd: number;
  } | null>(null);
  
  // Состояние для управления emoji picker
  const [showEmojiPicker, setShowEmojiPicker] = useState<{
    main: boolean;
    conditional: number | null; // null если не показывается, число = индекс условного шаблона
    position?: { x: number; y: number }; // Позиция для отображения picker
  }>({ main: false, conditional: null });
  
  // Refs для кнопок emoji picker
  const emojiButtonRef = useRef<HTMLButtonElement>(null);
  const conditionalEmojiButtonRefs = useRef<Record<number, HTMLButtonElement | null>>({});

  // Функции форматирования текста для contentEditable
  const applyFormatting = (tag: string, closingTag: string) => {
    const editor = document.getElementById("messageTemplate") as HTMLElement;
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
      
      // Обновляем состояние
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
  };

  const formatBold = () => {
    document.execCommand('bold', false);
    setContextMenu(null);
  };
  const formatItalic = () => {
    document.execCommand('italic', false);
    setContextMenu(null);
  };
  const formatUnderline = () => {
    document.execCommand('underline', false);
    setContextMenu(null);
  };
  const formatStrikethrough = () => {
    document.execCommand('strikeThrough', false);
    setContextMenu(null);
  };
  const formatCode = () => applyFormatting("<code>", "</code>");
  const formatSpoiler = () => applyFormatting("<spoiler>", "</spoiler>");
  
  // Функция для вставки emoji в редактор
  const insertEmoji = (emojiData: { emoji: string }, editorId: string, isConditional: boolean = false) => {
    const editor = document.getElementById(editorId) as HTMLElement;
    if (!editor) return;
    
    // Устанавливаем фокус на редактор
    editor.focus();
    
    const selection = window.getSelection();
    if (selection && selection.rangeCount > 0) {
      const range = selection.getRangeAt(0);
      range.deleteContents();
      
      // Вставляем emoji как текстовый узел
      const textNode = document.createTextNode(emojiData.emoji);
      range.insertNode(textNode);
      
      // Устанавливаем курсор после вставленного emoji
      const newRange = document.createRange();
      newRange.setStartAfter(textNode);
      newRange.collapse(true);
      selection.removeAllRanges();
      selection.addRange(newRange);
      
      // Триггерим событие input для обновления состояния
      const inputEvent = new Event('input', { bubbles: true });
      editor.dispatchEvent(inputEvent);
    } else {
      // Если нет выделения, вставляем в конец
      const range = document.createRange();
      range.selectNodeContents(editor);
      range.collapse(false);
      
      const textNode = document.createTextNode(emojiData.emoji);
      range.insertNode(textNode);
      
      const newRange = document.createRange();
      newRange.setStartAfter(textNode);
      newRange.collapse(true);
      const sel = window.getSelection();
      if (sel) {
        sel.removeAllRanges();
        sel.addRange(newRange);
      }
      
      const inputEvent = new Event('input', { bubbles: true });
      editor.dispatchEvent(inputEvent);
    }
    
    // Закрываем picker после вставки
    setShowEmojiPicker({ main: false, conditional: null });
  };
  
  const formatBlockquote = () => {
    const editor = document.getElementById("messageTemplate") as HTMLElement;
    if (!editor) return;

    const selection = window.getSelection();
    if (!selection || selection.rangeCount === 0) return;

    const range = selection.getRangeAt(0);
    const selectedText = range.toString();
    const lines = selectedText.split('\n');
    
    if (selectedText) {
      const formattedText = lines.map(line => `> ${line}`).join('\n');
      range.deleteContents();
      const textNode = document.createTextNode(formattedText);
      range.insertNode(textNode);
      
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
  };

  // Обработчик правого клика
  const handleContextMenu = (e: React.MouseEvent<HTMLElement>) => {
    e.preventDefault();
    const editor = e.currentTarget;
    const selection = window.getSelection();
    const selectedText = selection ? selection.toString() : '';

    // Получаем позицию текстового поля относительно страницы
    const rect = editor.getBoundingClientRect();
    // Вычисляем позицию клика относительно текстового поля
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
  };

  // Функция для преобразования текстового шаблона в HTML с визуальными блоками
  const convertTemplateToHTML = (template: string): string => {
    let html = template;
    // Маппинг friendly -> label для отображения
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
      // Создаем визуальный блок для каждой вставки
      const blockHTML = `<span class="inline-flex items-center gap-1.5 px-2 py-1 mx-0.5 bg-emerald-500/20 border border-emerald-500/50 rounded text-emerald-300 text-xs font-medium cursor-default" data-placeholder-key="${friendly}" contenteditable="false"><svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 8h10M7 12h4m1 8l-4-4H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-3l-4 4z"></path></svg><span>${label}</span></span>`;
      html = html.replace(new RegExp(friendly.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'g'), blockHTML);
    });
    // Заменяем переносы строк на <br>
    html = html.replace(/\n/g, '<br>');
    return html;
  };

  // Вспомогательная функция для получения текстовых узлов
  const getTextNodes = (element: Node): Text[] => {
    const textNodes: Text[] = [];
    const walker = document.createTreeWalker(
      element,
      NodeFilter.SHOW_TEXT,
      null
    );
    let node;
    while (node = walker.nextNode()) {
      textNodes.push(node as Text);
    }
    return textNodes;
  };

  // Пример текста для шаблона
  const exampleTemplate = `🚨 <b>НАЙДЕНА СТРЕЛА!</b> [[Направление]]

<b>[[Биржа и тип рынка]]</b>
💰 <b>[[Торговая пара]]</b>

📊 <b>Метрики:</b>
• Изменение: <b>[[Дельта стрелы]]</b> [[Направление]]
• Объём: <b>[[Объём стрелы]] USDT</b>
• Тень: <b>[[Тень свечи]]</b>

⏰ <b>[[Время детекта]]</b>`;

  // Проверка, является ли шаблон пустым или дефолтным
  const isTemplateEmpty = () => {
    const editor = document.getElementById("messageTemplate") as HTMLElement;
    if (!editor) return true;
    const text = editor.textContent || editor.innerText || '';
    return text.trim().length === 0 || editor.innerHTML.trim() === '';
  };

  // Инициализация редактора при загрузке шаблона
  useEffect(() => {
    // Ждём, пока элемент будет в DOM (особенно важно, если вкладка settings не активна)
    const initEditor = () => {
      const editor = document.getElementById("messageTemplate") as HTMLElement;
      if (!editor) return;
      
      // Убеждаемся, что у нас есть шаблон (если нет, используем дефолтный)
      const templateToUse = messageTemplate && messageTemplate.trim() !== '' 
        ? messageTemplate 
        : exampleTemplate;
      
      const html = convertTemplateToHTML(convertToFriendlyNames(templateToUse));
      // Проверяем, является ли это примером или пользовательским шаблоном
      const isExample = templateToUse === exampleTemplate || templateToUse.trim() === exampleTemplate.trim();
      
      // Проверяем, нужно ли обновлять содержимое и не редактирует ли пользователь
      if (isUserEditingRef.current) {
        return; // Не обновляем innerHTML во время редактирования
      }
      
      const currentContent = editor.innerHTML.trim();
      const newContent = html.trim();
      
      if (currentContent !== newContent) {
        editor.innerHTML = html;
      }
      
      if (isExample) {
        editor.classList.add('template-placeholder');
      } else {
        editor.classList.remove('template-placeholder');
      }
    };
    
    // Если вкладка settings активна, инициализируем с небольшой задержкой
    if (activeTab === "settings") {
      // Небольшая задержка для гарантии, что элемент уже в DOM
      setTimeout(initEditor, 100);
      // Также пробуем ещё раз через большее время на случай медленного рендеринга
      setTimeout(initEditor, 500);
    } else {
      // Если вкладка не активна, пробуем инициализировать (на случай, если элемент уже есть)
      initEditor();
    }
  }, [messageTemplate, activeTab]);

  // Дополнительная инициализация редактора при переключении на вкладку settings
  useEffect(() => {
    if (activeTab === "settings") {
      // Даём время на рендеринг элемента
      const timer = setTimeout(() => {
        const editor = document.getElementById("messageTemplate") as HTMLElement;
        if (!editor) return;
        
        // Убеждаемся, что у нас есть шаблон (если нет, используем дефолтный)
        const templateToUse = messageTemplate && messageTemplate.trim() !== '' 
          ? messageTemplate 
          : exampleTemplate;
        
        const html = convertTemplateToHTML(convertToFriendlyNames(templateToUse));
        const isExample = templateToUse === exampleTemplate || templateToUse.trim() === exampleTemplate.trim();
        
        // Проверяем, нужно ли обновлять содержимое и не редактирует ли пользователь
        if (isUserEditingRef.current) {
          return; // Не обновляем innerHTML во время редактирования
        }
        
        const currentContent = editor.innerHTML.trim();
        const newContent = html.trim();
        
        if (currentContent !== newContent) {
          editor.innerHTML = html;
        }
        
        if (isExample) {
          editor.classList.add('template-placeholder');
        } else {
          editor.classList.remove('template-placeholder');
        }
      }, 200);
      
      return () => clearTimeout(timer);
    }
  }, [activeTab, messageTemplate]);

  // Инициализация редактора при открытии блока формата сообщения
  useEffect(() => {
    if (isMessageFormatExpanded && activeTab === "settings") {
      // Даём время на рендеринг элемента после открытия блока
      const timer = setTimeout(() => {
        const editor = document.getElementById("messageTemplate") as HTMLElement;
        if (!editor) {
          console.warn("Редактор не найден при открытии блока");
          return;
        }
        
        // Убеждаемся, что у нас есть шаблон (если нет, используем дефолтный)
        const templateToUse = messageTemplate && messageTemplate.trim() !== '' 
          ? messageTemplate 
          : exampleTemplate;
        
        console.log("Инициализация редактора с шаблоном:", templateToUse);
        
        const html = convertTemplateToHTML(convertToFriendlyNames(templateToUse));
        const isExample = templateToUse === exampleTemplate || templateToUse.trim() === exampleTemplate.trim();
        
        // Не обновляем innerHTML во время редактирования
        if (isUserEditingRef.current) {
          return;
        }
        
        // Всегда обновляем содержимое при открытии блока
        editor.innerHTML = html;
        
        if (isExample) {
          editor.classList.add('template-placeholder');
        } else {
          editor.classList.remove('template-placeholder');
        }
      }, 300);
      
      return () => clearTimeout(timer);
    }
  }, [isMessageFormatExpanded, messageTemplate, activeTab]);

  // Инициализация редакторов условных шаблонов
  useEffect(() => {
    if (isConditionalTemplatesExpanded && activeTab === "settings") {
      // Небольшая задержка для гарантии, что элементы уже в DOM
      const timer = setTimeout(() => {
        conditionalTemplates.forEach((template, index) => {
          const editorId = `conditionalTemplate_${index}`;
          const editor = document.getElementById(editorId) as HTMLElement;
          if (editor) {
            const html = convertTemplateToHTML(convertToFriendlyNames(template.template));
            // Обновляем только если содержимое отличается и редактор не пустой или действительно пустой
            const currentContent = editor.innerHTML.trim();
            if (currentContent === "" || currentContent !== html.trim()) {
              editor.innerHTML = html;
            }
          }
        });
      }, 100);
      
      return () => clearTimeout(timer);
    }
  }, [conditionalTemplates, isConditionalTemplatesExpanded, activeTab]);

  // Отслеживание изменений в редакторе для удаления placeholder класса
  useEffect(() => {
    const editor = document.getElementById("messageTemplate") as HTMLElement;
    if (editor) {
      const handleFocus = () => {
        if (editor.classList.contains('template-placeholder')) {
          const currentText = editor.textContent || '';
          const exampleText = exampleTemplate.replace(/\[\[.*?\]\]/g, '').replace(/<[^>]*>/g, '').trim();
          if (currentText.trim() === exampleText.trim()) {
            // Если это пример, очищаем при фокусе
            editor.innerHTML = '';
            editor.classList.remove('template-placeholder');
          }
        }
      };

      const handleBlur = () => {
        if (editor.innerHTML.trim() === '' || editor.textContent?.trim() === '') {
          // Если редактор пустой, показываем пример
          const exampleHTML = convertTemplateToHTML(convertToFriendlyNames(exampleTemplate));
          editor.innerHTML = exampleHTML;
          editor.classList.add('template-placeholder');
        }
      };

      editor.addEventListener('focus', handleFocus);
      editor.addEventListener('blur', handleBlur);

      return () => {
        editor.removeEventListener('focus', handleFocus);
        editor.removeEventListener('blur', handleBlur);
      };
    }
  }, []);

  // Обработчик горячих клавиш
  const handleKeyDown = (e: React.KeyboardEvent<HTMLElement>) => {
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
  };
  
  // Состояния для дополнительных пар
  const [openPairs, setOpenPairs] = useState<Record<string, boolean>>({});
  const [pairSettings, setPairSettings] = useState<Record<string, { enabled: boolean; delta: string; volume: string; shadow: string }>>({});
  
  // Определение пар для каждой биржи и типа рынка
  const getPairsForExchange = (exchange: string, market: "spot" | "futures"): string[] => {
    if (exchange === "binance" && market === "spot") {
      return ["BTC", "ETH", "USDT", "BNB", "AUD", "TUSD", "BRL", "GBP", "USDC", "TRX", "EUR", "BIDR", "DOGE", "TRY", "FDUSD", "AEUR"];
    }
    if (exchange === "binance" && market === "futures") {
      return ["USDT", "USDC", "BTC"];
    }
    if (exchange === "bybit" && market === "spot") {
      return ["USDT", "ETH", "BTC", "USDC", "EUR"];
    }
    return [];
  };
  
  // Состояния для статистики стрел
  const [spikesStats, setSpikesStats] = useState<{
    total_count: number;
    avg_delta: number;
    avg_volume: number;
    total_volume: number;
    chart_data: Array<{ date: string; count: number }>;
    by_exchange: Record<string, number>;
    by_market: Record<string, number>;
    top_symbols: Array<{ symbol: string; count: number }>;
    top_by_delta: Array<any>;
    top_by_volume: Array<any>;
    spikes: Array<any>;
  } | null>(null);
  const [spikesStatsLoading, setSpikesStatsLoading] = useState(false);
  const [statisticsMode, setStatisticsMode] = useState<"personal" | "global">("personal");
  const [statisticsPeriod, setStatisticsPeriod] = useState<number>(30);
  const [deletingSpikes, setDeletingSpikes] = useState(false);

  // Состояния для админ панели
  type AdminUser = {
    user: string;
    has_telegram: boolean;
    options_json?: string;
    tg_token?: string;
    chat_id?: string;
  };

  type AdminUserSettings = {
    user: string;
    tg_token: string;
    chat_id: string;
    options_json?: string;
  };

  const [adminUsers, setAdminUsers] = useState<AdminUser[]>([]);
  const [adminForm, setAdminForm] = useState<string>(""); // Только имя пользователя
  const [adminMsg, setAdminMsg] = useState("");
  const [adminLoading, setAdminLoading] = useState(false);
  const [selectedUserSettings, setSelectedUserSettings] = useState<AdminUserSettings | null>(null);
  const [deletingGlobalStats, setDeletingGlobalStats] = useState(false);
  
  // Состояния для редактирования настроек бирж в админ панели
  const [adminExchangeFilters, setAdminExchangeFilters] = useState<Record<string, boolean>>({
    binance: true,
    bybit: true,
    bitget: true,
    gate: true,
    hyperliquid: true,
  });
  const [adminExpandedExchanges, setAdminExpandedExchanges] = useState<Record<string, boolean>>({});
  const [adminExchangeSettings, setAdminExchangeSettings] = useState<Record<string, {
    spot: { enabled: boolean; delta: string; volume: string; shadow: string };
    futures: { enabled: boolean; delta: string; volume: string; shadow: string };
  }>>({
    binance: { spot: { enabled: true, delta: "0", volume: "0", shadow: "0" }, futures: { enabled: true, delta: "0", volume: "0", shadow: "0" } },
    bybit: { spot: { enabled: true, delta: "0", volume: "0", shadow: "0" }, futures: { enabled: true, delta: "0", volume: "0", shadow: "0" } },
    bitget: { spot: { enabled: true, delta: "0", volume: "0", shadow: "0" }, futures: { enabled: true, delta: "0", volume: "0", shadow: "0" } },
    gate: { spot: { enabled: true, delta: "0", volume: "0", shadow: "0" }, futures: { enabled: true, delta: "0", volume: "0", shadow: "0" } },
    hyperliquid: { spot: { enabled: true, delta: "0", volume: "0", shadow: "0" }, futures: { enabled: true, delta: "0", volume: "0", shadow: "0" } },
  });
  const [adminPairSettings, setAdminPairSettings] = useState<Record<string, { enabled: boolean; delta: string; volume: string; shadow: string }>>({});
  const [adminOpenPairs, setAdminOpenPairs] = useState<Record<string, boolean>>({});

  // Состояния для логов ошибок
  type ErrorLog = {
    id: number;
    timestamp: string;
    exchange?: string;
    error_type: string;
    error_message: string;
    connection_id?: string;
    market?: string;
    symbol?: string;
    stack_trace?: string;
  };
  const [errorLogs, setErrorLogs] = useState<ErrorLog[]>([]);
  const [errorLogsLoading, setErrorLogsLoading] = useState(false);
  const [errorLogsFilter, setErrorLogsFilter] = useState<{
    exchange?: string;
    error_type?: string;
    limit: number;
  }>({ limit: 100 });

  // Проверка, является ли текущий пользователь администратором (без учета регистра)
  const isAdmin = userLogin?.toLowerCase() === "влад";

  const fetchMetrics = async () => {
    try {
      // Загружаем метрики, статистику бирж, статус системы и статистику детектов параллельно
      const [metricsRes, statsRes, statusRes, spikesStatsRes] = await Promise.allSettled([
        fetch("/api/metrics").catch(() => null),
        fetch("/api/exchanges/stats").catch(() => null),
        fetch("/api/status").catch(() => null),
        fetch("/api/spikes/stats").catch(() => null)
      ]);
      
      // Обрабатываем результаты с проверкой статуса
      const metricsResult = metricsRes.status === "fulfilled" && metricsRes.value ? metricsRes.value : null;
      const statsResult = statsRes.status === "fulfilled" && statsRes.value ? statsRes.value : null;
      const statusResult = statusRes.status === "fulfilled" && statusRes.value ? statusRes.value : null;
      const spikesStatsResult = spikesStatsRes.status === "fulfilled" && spikesStatsRes.value ? spikesStatsRes.value : null;
      
      // Проверяем доступность API сервера
      if (!metricsResult || !statsResult) {
        const errorMsg = metricsRes.status === "rejected" || statsRes.status === "rejected"
          ? "API сервер недоступен. Убедитесь, что FastAPI сервер запущен (python api_server.py)"
          : "Ошибка загрузки данных. Проверьте, что API сервер запущен.";
        console.warn(errorMsg);
        // Показываем пустые данные вместо полного стопа
        if (!metricsResult) {
          console.warn("Не удалось загрузить метрики");
        }
        if (!statsResult) {
          console.warn("Не удалось загрузить статистику бирж");
        }
        // Не возвращаемся, продолжаем обработку с пустыми данными
      }
      
      // Обрабатываем ответы метрик
      let metricsData = null;
      if (metricsResult && metricsResult.ok) {
        try {
          metricsData = await metricsResult.json();
        } catch (e) {
          console.error("Ошибка парсинга JSON метрик:", e);
          metricsData = null;
        }
      } else if (metricsResult && !metricsResult.ok) {
        try {
          const errorData = await metricsResult.json().catch(async () => {
            const errorText = await metricsResult.text().catch(() => "Unknown error");
            return { error: errorText };
          });
          console.error("Ошибка загрузки метрик:", metricsResult.status, errorData.detail || errorData.error || JSON.stringify(errorData));
        } catch (e) {
          console.error("Ошибка загрузки метрик:", metricsResult.status, "Unknown error");
        }
      }
      
      // Обрабатываем ответы статистики бирж
      let statsData = null;
      if (statsResult && statsResult.ok) {
        try {
          statsData = await statsResult.json();
        } catch (e) {
          console.error("Ошибка парсинга JSON статистики бирж:", e);
          statsData = null;
        }
      } else if (statsResult && !statsResult.ok) {
        try {
          const errorData = await statsResult.json().catch(async () => {
            const errorText = await statsResult.text().catch(() => "Unknown error");
            return { error: errorText };
          });
          console.error("Ошибка загрузки статистики бирж:", statsResult.status, errorData.detail || errorData.error || JSON.stringify(errorData));
        } catch (e) {
          console.error("Ошибка загрузки статистики бирж:", statsResult.status, "Unknown error");
        }
      }
      
      // Если нет критических данных, выходим
      if (!metricsData || !statsData) {
        console.warn("Не удалось загрузить критически важные данные. Метрики:", !!metricsData, "Статистика:", !!statsData);
        return;
      }
      
      // Получаем статус системы и общее количество детектов
      let uptimeSecondsValue = 0;
      let totalDetectsValue = 0;
      let startTimeValue: number | null = null;
      
      if (statusResult && statusResult.ok) {
        try {
          const statusData = await statusResult.json();
          // Используем только alerts_since_start для детектов с момента запуска
          totalDetectsValue = statusData.alerts_since_start ?? 0;
          uptimeSecondsValue = statusData.uptime_seconds || 0;
          startTimeValue = statusData.start_time || null;
        } catch (e) {
          console.warn("Не удалось получить статус системы:", e);
        }
      }
      
      // Устанавливаем значения
      setTotalDetects(totalDetectsValue);
      setUptimeSeconds(uptimeSecondsValue);
      setStartTime(startTimeValue);
      
      // Используем значение для расчетов
      const uptimeSeconds = uptimeSecondsValue;
      
      console.log("Metrics data:", metricsData);
      console.log("Exchanges stats:", statsData);
      
      // Если нет данных, показываем сообщение
      if (!metricsData || !metricsData.metrics) {
        console.warn("Метрики не получены или пусты. Убедитесь что:");
        console.warn("1. FastAPI сервер запущен (python api_server.py)");
        console.warn("2. Основной детектор запущен (python main.py)");
        console.warn("3. В базе данных есть записи в таблице spikes");
        return;
      }
      
      if (!statsData || !statsData.exchanges) {
        console.warn("Статистика бирж не получена или пуста. Убедитесь что:");
        console.warn("1. FastAPI сервер запущен (python api_server.py)");
        console.warn("2. Основной детектор запущен (python main.py)");
        console.warn("3. В базе данных есть записи в таблице stats");
        return;
      }
      
      // Обрабатываем данные даже если они частично пустые
      if (metricsData.metrics && statsData.exchanges) {
        // Создаем список всех бирж и их типов рынка
        const exchangeNames = ["Binance", "Bybit", "Gate.io", "Bitget", "Hyperliquid"];
        const markets: ("spot" | "linear")[] = ["spot", "linear"];
        
        const newExchanges: Exchange[] = [];
        
        for (const exchangeName of exchangeNames) {
          // Нормализуем имя биржи для поиска в метриках
          let nameKey = exchangeName.toLowerCase();
          // Gate.io в метриках хранится как "gate"
          if (nameKey === "gate.io") {
            nameKey = "gate";
          }
          
          // Получаем статистику WS для биржи
          const exchangeStats = statsData.exchanges[nameKey] || {
            spot: { active_connections: 0, reconnects: 0, active_symbols: 0 },
            linear: { active_connections: 0, reconnects: 0, active_symbols: 0 }
          };
          
          // Создаем отдельную запись для spot и linear
          for (const market of markets) {
            const marketStats = exchangeStats[market] || {};
            const wsConnections = marketStats.active_connections || 0;
            const symbols = marketStats.active_symbols || 0;
            const reconnects = marketStats.reconnects || 0;
            
            // Формируем строку с информацией о WS (без количества символов, т.к. оно в отдельном столбце)
            let wsInfo = `${wsConnections} WS`;
            
            // Получаем свечи для конкретного рынка - сначала из API, потом из метрик
            let candles = marketStats.candles || 0;
            if (candles === 0) {
              candles = metricsData.metrics[`candles_processed_${nameKey}_${market}`] || 0;
            }
            
            // Получаем время последнего обновления из метрик (last_candle_ts) - это основной источник
            // Получаем время последнего обновления из API (last_candle_time) или метрик (last_candle_ts)
            let lastUpdateTimestamp: number | undefined = undefined;
            let lastUpdate = "Нет данных";
            
            // Сначала пытаемся получить из API (last_candle_time в формате ISO строки)
            const lastCandleTime = marketStats.last_candle_time;
            if (lastCandleTime) {
              try {
                // Парсим ISO строку в Date и конвертируем в timestamp
                const date = new Date(lastCandleTime);
                if (!isNaN(date.getTime())) {
                  lastUpdateTimestamp = date.getTime();
                  lastUpdate = date.toLocaleString("ru-RU");
                }
              } catch (e) {
                console.warn(`Ошибка парсинга last_candle_time для ${nameKey} ${market}:`, e);
              }
            }
            
            // Fallback: если нет в API, пытаемся получить из метрик (last_candle_ts)
            if (!lastUpdateTimestamp) {
              const lastCandleTS = metricsData.metrics[`last_candle_ts_${nameKey}_${market}`] || 0;
              if (lastCandleTS > 0) {
                // Конвертируем timestamp в миллисекунды если в секундах
                const ts_sec = lastCandleTS < 1e10 ? lastCandleTS : Math.floor(lastCandleTS / 1000);
                lastUpdateTimestamp = ts_sec * 1000; // Конвертируем в миллисекунды
                lastUpdate = new Date(lastUpdateTimestamp).toLocaleString("ru-RU");
              }
            }
            
            // Получаем T/s (тики в секунду) из статистики биржи
            // Значение уже рассчитано на бэкенде и приходит из API
            const tps = marketStats.ticks_per_second || 0;
            
            // Определяем статус - ПРИОРИТЕТ: проверка времени последнего обновления last_candle_ts
            let status: "active" | "inactive" | "problems" = "inactive";
            
            // Проверяем, прошла ли минута с последнего обновления last_candle_ts
            const now = Date.now();
            const oneMinuteAgo = now - 60 * 1000; // 1 минута в миллисекундах
            
            if (!lastUpdateTimestamp || lastUpdateTimestamp < oneMinuteAgo) {
              // Если timestamp отсутствует или последнее обновление было больше минуты назад - биржа отключена
              status = "inactive";
            } else {
              // Если timestamp свежий (< минуты) - используем логику из API или fallback
              const apiStatus = marketStats.status;
              if (apiStatus) {
                // Переводим статус из API (русский) в формат фронтенда
                if (apiStatus === "Активна") {
                  status = "active";
                } else if (apiStatus === "Проблемы") {
                  status = "problems";
                } else {
                  status = "inactive";
                }
              } else {
                // Fallback: определяем статус сами (если API не вернул статус)
                if (wsConnections > 0 && reconnects <= 15) {
                  status = "active";
                } else if (reconnects > 15) {
                  status = "problems";
                }
              }
            }
            
            newExchanges.push({
              name: exchangeName,
              market: market,
              status: status,
              websocketInfo: wsInfo,
              candles: candles,
              lastUpdate: lastUpdate,
              lastUpdateTimestamp: lastUpdateTimestamp,
              wsConnections: wsConnections,
              reconnects: reconnects,
              tradingPairs: symbols,
              tps: tps
            });
          }
        }
        
        setExchanges(newExchanges);
      }
    } catch (err) {
      console.error("Ошибка загрузки метрик:", err);
      // Если ошибка, показываем предупреждение с деталями
      console.warn("Не удалось загрузить данные. Убедитесь что:");
      console.warn("1. FastAPI сервер запущен на http://localhost:8001");
      console.warn("2. Основной детектор запущен (python main.py)");
      console.warn("3. Сеть доступна и порты не заблокированы");
      if (err instanceof Error) {
        console.error("Детали ошибки:", err.message, err.stack);
      }
    }
  };

  // Загрузка настроек пользователя
  const fetchUserSettings = async () => {
    if (!userLogin) {
      console.log("[Dashboard] fetchUserSettings: userLogin is empty");
      return;
    }
    
    console.log(`[Dashboard] fetchUserSettings: Loading settings for user "${userLogin}"`);
    
    try {
      const url = `/api/users/${encodeURIComponent(userLogin)}`;
      console.log(`[Dashboard] fetchUserSettings: Fetching from ${url}`);
      
      const res = await fetch(url);
      console.log(`[Dashboard] fetchUserSettings: Response status: ${res.status}`);
      
      if (res.ok) {
        const userData = await res.json();
        console.log(`[Dashboard] fetchUserSettings: User data received:`, {
          user: userData.user,
          has_tg_token: !!userData.tg_token,
          has_chat_id: !!userData.chat_id,
          has_options_json: !!userData.options_json
        });
        // Загружаем настройки Telegram из ответа API (сохраняем даже если пустые строки)
        const tgToken = (userData.tg_token || "").trim();
        const chatId = (userData.chat_id || "").trim();
        setTelegramBotToken(tgToken);
        setTelegramChatId(chatId);
        
        // Проверяем, настроен ли Telegram (оба поля должны быть не пустыми после trim)
        const hasTelegram = !!(tgToken && chatId);
        setIsTelegramConfigured(hasTelegram);
        setIsEditingTelegram(!hasTelegram); // Если не настроен, показываем форму
        
        // Очищаем ошибки валидации при загрузке существующих данных
        if (hasTelegram) {
          setTelegramChatIdError("");
          setTelegramBotTokenError("");
        }
        
        // Загружаем дополнительные настройки из options_json
        try {
          const optionsJson = userData.options_json || "{}";
          const options = typeof optionsJson === "string" ? JSON.parse(optionsJson) : optionsJson;
          
          // Загружаем шаблон сообщения и преобразуем технические ключи в понятные названия
          if (options.messageTemplate && options.messageTemplate.trim() !== '') {
            console.log("Загружен шаблон из БД (технический):", options.messageTemplate);
            let template = options.messageTemplate;
            
            // Миграция старых шаблонов: заменяем отдельные {exchange} и {market} на {exchange_market}
            // Это нужно для обратной совместимости со старыми шаблонами
            if (template.includes("{exchange}") && template.includes("{market}")) {
              // Ищем паттерны типа "{exchange} | {market}" или "{exchange} | {market}" в разных вариантах
              template = template.replace(/\{exchange\}\s*\|\s*\{market\}/g, "{exchange_market}");
              template = template.replace(/\{exchange\}\s*\{market\}/g, "{exchange_market}");
              // Также проверяем в обратном порядке
              template = template.replace(/\{market\}\s*\|\s*\{exchange\}/g, "{exchange_market}");
              template = template.replace(/\{market\}\s*\{exchange\}/g, "{exchange_market}");
            }
            
            // Также миграция для понятных названий (старые шаблоны могли использовать их)
            let friendlyTemplate = convertToFriendlyNames(template);
            
            // Миграция старого названия "Объём торгов" на "Объём стрелы"
            friendlyTemplate = friendlyTemplate.replace(/\[\[Объём торгов\]\]/g, "[[Объём стрелы]]");
            
            if (friendlyTemplate.includes("[[Биржа]]") && friendlyTemplate.includes("[[Тип рынка]]")) {
              // Заменяем "[[Биржа]] | [[Тип рынка]]" на "[[Биржа и тип рынка]]"
              friendlyTemplate = friendlyTemplate.replace(/\[\[Биржа\]\]\s*\|\s*\[\[Тип рынка\]\]/g, "[[Биржа и тип рынка]]");
              friendlyTemplate = friendlyTemplate.replace(/\[\[Биржа\]\]\s*\[\[Тип рынка\]\]/g, "[[Биржа и тип рынка]]");
              friendlyTemplate = friendlyTemplate.replace(/\[\[Тип рынка\]\]\s*\|\s*\[\[Биржа\]\]/g, "[[Биржа и тип рынка]]");
              friendlyTemplate = friendlyTemplate.replace(/\[\[Тип рынка\]\]\s*\[\[Биржа\]\]/g, "[[Биржа и тип рынка]]");
            }
            
            console.log("Шаблон после преобразования (понятный):", friendlyTemplate);
            setMessageTemplate(friendlyTemplate);
          } else {
            // Если шаблона нет, устанавливаем пример
            console.log("Шаблон не найден в БД, используем дефолтный");
            setMessageTemplate(exampleTemplate);
          }
          
          // Загружаем фильтры по биржам
          if (options.exchanges && typeof options.exchanges === "object") {
            setExchangeFilters({
              binance: options.exchanges.binance !== false && options.exchanges.binance !== undefined ? options.exchanges.binance : true,
              bybit: options.exchanges.bybit !== false && options.exchanges.bybit !== undefined ? options.exchanges.bybit : true,
              bitget: options.exchanges.bitget !== false && options.exchanges.bitget !== undefined ? options.exchanges.bitget : true,
              gate: options.exchanges.gate !== false && options.exchanges.gate !== undefined ? options.exchanges.gate : true,
              hyperliquid: options.exchanges.hyperliquid !== false && options.exchanges.hyperliquid !== undefined ? options.exchanges.hyperliquid : true,
            });
          } else {
            // Если фильтры не найдены, используем значения по умолчанию (все включены)
            setExchangeFilters({
              binance: true,
              bybit: true,
              bitget: true,
              gate: true,
              hyperliquid: true,
            });
          }
          
          // Загружаем настройки бирж (Spot/Futures) с мерджем дефолтных значений
          if (options.exchangeSettings) {
            setExchangeSettings((prevSettings) => {
              const merged = { ...prevSettings };
              // Мерджим загруженные настройки с дефолтными
              Object.keys(options.exchangeSettings).forEach((exchange) => {
                if (merged[exchange]) {
                  merged[exchange] = {
                    spot: {
                      ...merged[exchange].spot,
                      ...options.exchangeSettings[exchange].spot,
                    },
                    futures: {
                      ...merged[exchange].futures,
                      ...options.exchangeSettings[exchange].futures,
                    },
                  };
                } else {
                  merged[exchange] = options.exchangeSettings[exchange];
                }
              });
              return merged;
            });
          }
          
          // Загружаем настройки пар (с поддержкой enabled и миграцией старых данных)
          if (options.pairSettings) {
            const migratedPairSettings: Record<string, { enabled: boolean; delta: string; volume: string; shadow: string }> = {};
            Object.entries(options.pairSettings).forEach(([key, value]: [string, any]) => {
              // Миграция старых данных без поля enabled
              if (value && typeof value === 'object' && !('enabled' in value)) {
                migratedPairSettings[key] = {
                  enabled: true, // По умолчанию включено
                  delta: value.delta || "0",
                  volume: value.volume || "0",
                  shadow: value.shadow || "0"
                };
              } else {
                migratedPairSettings[key] = value;
              }
            });
            setPairSettings(migratedPairSettings);
          }
          
          // Загружаем чёрный список
          if (options.blacklist) {
            setBlacklist(options.blacklist || []);
          }
          
          // Загружаем условные шаблоны и преобразуем технические ключи в понятные названия
          if (options.conditionalTemplates && Array.isArray(options.conditionalTemplates)) {
            const templatesWithFriendlyNames = options.conditionalTemplates.map((template: any) => {
              // Миграция: если есть старый формат с одним condition, преобразуем в новый формат
              let conditions = [];
              if (template.conditions && Array.isArray(template.conditions)) {
                // Новый формат
                conditions = template.conditions.map((cond: any) => {
                  const condType = cond.type === "wick" ? "delta" : (cond.type || "volume");
                  if (condType === "series") {
                    return {
                      type: "series",
                      count: cond.count || 2,
                      timeWindowSeconds: cond.timeWindowSeconds || 300,
                    };
                  } else if (condType === "delta" || condType === "wick_pct") {
                    // Для дельты и тени - поддержка диапазона (valueMin, valueMax) или старого формата (value)
                    if (cond.valueMin !== undefined || cond.valueMax !== undefined) {
                      // Новый формат с диапазоном
                      return {
                        type: condType,
                        valueMin: cond.valueMin !== undefined ? cond.valueMin : 0,
                        valueMax: cond.valueMax !== undefined ? cond.valueMax : null, // null = бесконечность
                      };
                    } else {
                      // Старый формат - мигрируем value в valueMin
                      return {
                        type: condType,
                        valueMin: cond.value !== undefined ? cond.value : 0,
                        valueMax: null, // null = бесконечность
                      };
                    }
                  } else if (condType === "symbol") {
                    // Для символа - используем symbol или value (для обратной совместимости)
                    return {
                      type: "symbol",
                      symbol: (cond.symbol || cond.value || "").toUpperCase().trim(),
                    };
                  } else if (condType === "exchange") {
                    // Для биржи
                    return {
                      type: "exchange",
                      exchange: (cond.exchange || "binance").toLowerCase(),
                    };
                  } else if (condType === "market") {
                    // Для типа рынка
                    return {
                      type: "market",
                      market: (cond.market || "spot").toLowerCase() as "spot" | "futures" | "linear",
                    };
                  } else if (condType === "direction") {
                    // Для направления
                    return {
                      type: "direction",
                      direction: (cond.direction || "up").toLowerCase() as "up" | "down",
                    };
                  } else {
                    // Для объёма - одно значение
                    return {
                      type: condType,
                      value: cond.value || 0,
                    };
                  }
                });
              } else if (template.condition) {
                // Старый формат - преобразуем в новый
                const condType = template.condition.type === "wick" ? "delta" : (template.condition.type || "volume");
                if (condType === "delta") {
                  // Для дельты - мигрируем в диапазон
                  conditions = [{
                    type: "delta",
                    valueMin: template.condition.value !== undefined ? template.condition.value : 0,
                    valueMax: null, // null = бесконечность
                  }];
                } else {
                  // Для объёма - одно значение
                  conditions = [{
                    type: condType,
                    value: template.condition.value || 0,
                  }];
                }
              } else {
                // Если ничего нет, создаем пустое условие
                conditions = [{ type: "volume", value: 0 }];
              }
              
              return {
                name: template.name || undefined, // Название шаблона
                enabled: template.enabled !== undefined ? template.enabled : true, // По умолчанию true
                conditions,
                template: convertToFriendlyNames(template.template || ""), // Преобразуем в понятные названия
                chatId: template.chatId || undefined, // Chat ID на уровне шаблона
              };
            });
            setConditionalTemplates(templatesWithFriendlyNames);
          } else {
            setConditionalTemplates([]);
          }
          
          // Загружаем временную зону
          if (options.timezone && typeof options.timezone === "string") {
            setTimezone(options.timezone);
          } else {
            // Если не установлена, пытаемся определить автоматически из браузера
            try {
              const browserTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
              setTimezone(browserTimezone || "UTC");
            } catch (e) {
              setTimezone("UTC");
            }
          }
          
          console.log("Настройки пользователя загружены:", {
            hasTelegram,
            exchangeFilters: options.exchanges,
            timezone: options.timezone,
            optionsKeys: Object.keys(options)
          });
        } catch (e) {
          console.error("Ошибка парсинга options_json:", e);
          // При ошибке парсинга используем значения по умолчанию для фильтров
          setExchangeFilters({
            binance: true,
            bybit: true,
            bitget: true,
            gate: true,
            hyperliquid: true,
          });
        }
      } else if (res.status === 404) {
        // Пользователь не найден - это нормально для новых пользователей
        console.log(`Пользователь "${userLogin}" не найден в БД. Будет создан при сохранении настроек.`);
        // Оставляем дефолтные значения (уже установлены в useState)
      } else {
        const errorText = await res.text().catch(() => "Unknown error");
        console.error(`Ошибка загрузки настроек пользователя ${userLogin}:`, res.status, errorText);
      }
    } catch (err) {
      console.error("Ошибка загрузки настроек пользователя:", err);
    }
  };
  
  // Функция для извлечения текстового содержимого из contentEditable
  const extractTextFromEditor = (): string => {
    const editor = document.getElementById("messageTemplate") as HTMLElement;
    if (!editor) return messageTemplate;
    
    const content = editor.innerHTML;
    const tempDiv = document.createElement('div');
    tempDiv.innerHTML = content;
    
    // Извлекаем технические ключи из визуальных блоков
    const blocks = tempDiv.querySelectorAll('[data-placeholder-key]');
    let textContent = content;
    blocks.forEach((block) => {
      const key = block.getAttribute('data-placeholder-key');
      if (key) {
        // Экранируем специальные символы для regex
        const blockHTML = block.outerHTML.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        textContent = textContent.replace(new RegExp(blockHTML, 'g'), key);
      }
    });
    
    // Заменяем <br> на переносы строк
    textContent = textContent.replace(/<br\s*\/?>/gi, '\n');
    
    return textContent;
  };

  // Сохранение всех настроек
  const saveAllSettings = async () => {
    if (!userLogin) return;
    
    // Извлекаем текст из редактора перед сохранением
    const extractedText = extractTextFromEditor();
    
    const options = {
      exchanges: exchangeFilters,
      exchangeSettings,
      pairSettings,
      blacklist,
      messageTemplate: convertToTechnicalKeys(extractedText), // Преобразуем в технические ключи перед сохранением
      conditionalTemplates: conditionalTemplates.map(template => {
        const templateData: any = {
          conditions: template.conditions.map(condition => {
            const baseCondition: any = {
              type: condition.type,
              operator: ">=", // Всегда используем >=
            };
            
            if (condition.type === "series") {
              baseCondition.count = condition.count || 2;
              baseCondition.timeWindowSeconds = condition.timeWindowSeconds || 300;
            } else if (condition.type === "delta" || condition.type === "wick_pct") {
              // Для дельты и тени сохраняем valueMin и valueMax
              if (condition.valueMin !== undefined) {
                baseCondition.valueMin = condition.valueMin;
              }
              if (condition.valueMax !== undefined || condition.valueMax === null) {
                baseCondition.valueMax = condition.valueMax; // null = бесконечность
              }
            } else if (condition.type === "symbol") {
              // Для символа сохраняем symbol (нормализованный символ)
              if (condition.symbol) {
                baseCondition.value = condition.symbol.toUpperCase().trim();
                // Также сохраняем в поле symbol для обратной совместимости
                baseCondition.symbol = condition.symbol.toUpperCase().trim();
              }
            } else if (condition.type === "exchange") {
              // Для биржи сохраняем exchange
              if (condition.exchange) {
                baseCondition.exchange = condition.exchange.toLowerCase();
              }
            } else if (condition.type === "market") {
              // Для типа рынка сохраняем market
              if (condition.market) {
                baseCondition.market = condition.market.toLowerCase();
              }
            } else if (condition.type === "direction") {
              // Для направления сохраняем direction
              if (condition.direction) {
                baseCondition.direction = condition.direction.toLowerCase();
              }
            } else {
              // Для объёма сохраняем value
              baseCondition.value = condition.value || 0;
            }
            
            return baseCondition;
          }),
          template: convertToTechnicalKeys(template.template), // Преобразуем технические ключи в условных шаблонах
        };
        
        // Добавляем name, если указан
        if (template.name) {
          templateData.name = template.name;
        }
        
        // Добавляем enabled (по умолчанию true, сохраняем только если false)
        if (template.enabled === false) {
          templateData.enabled = false;
        }
        // enabled: true не сохраняем явно, так как это значение по умолчанию
        
        // Добавляем chatId на уровне шаблона, если указан
        if (template.chatId) {
          templateData.chatId = template.chatId;
        }
        
        return templateData;
      }),
      timezone: timezone || "UTC", // Сохраняем временную зону
    };
    
    try {
      const res = await fetch(`/api/users/${userLogin}/settings`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          tg_token: telegramBotToken,
          chat_id: telegramChatId,
          options_json: JSON.stringify(options),
        })
      });
      
      if (res.ok) {
        // Проверяем, были ли сохранены данные Telegram
        const hasTelegram = !!(telegramBotToken && telegramChatId);
        if (hasTelegram) {
          setIsTelegramConfigured(true);
          setIsEditingTelegram(false); // Скрываем форму после успешного сохранения
        }
        
        // Скрываем блок формата отправки детекта после сохранения
        setIsMessageFormatExpanded(false);
        
        setSaveMessage({ 
          type: "success", 
          text: "Настройки успешно сохранены! Изменения применятся в течение 1 минуты (время обновления кэша системы)." 
        });
      } else {
        const error = await res.json();
        setSaveMessage({ type: "error", text: error.detail || "Ошибка сохранения настроек" });
      }
    } catch (err) {
      setSaveMessage({ type: "error", text: "Ошибка при сохранении настроек" });
      console.error(err);
    }
  };

  // Админ панель - загрузка списка пользователей
  const fetchAdminUsers = async () => {
    try {
      const res = await fetch("/api/users");
      const data = await res.json();
      setAdminUsers(data.users || []);
    } catch (err) {
      console.error("Ошибка загрузки пользователей:", err);
      setAdminMsg("Ошибка загрузки пользователей");
      setTimeout(() => setAdminMsg(""), 3000);
    }
  };

  // Админ панель - создание нового пользователя
  const createAdminUser = async () => {
    if (!adminForm.trim()) {
      setAdminMsg("Введите имя пользователя");
      setTimeout(() => setAdminMsg(""), 2000);
      return;
    }

    setAdminLoading(true);
    try {
      // Кодируем имя пользователя для URL (важно для кириллицы и специальных символов)
      const trimmedUserName = adminForm.trim();
      const encodedUserName = encodeURIComponent(trimmedUserName);
      const res = await fetch(`/api/users/${encodedUserName}/settings`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          tg_token: "",
          chat_id: "",
          options_json: JSON.stringify({
            thresholds: { delta_pct: 1.0, volume_usdt: 10000.0, wick_pct: 50.0 },
            exchanges: { gate: true, binance: true, bitget: true, bybit: true, hyperliquid: true },
          }),
        }),
      });

      if (!res.ok) {
        const error = await res.json();
        throw new Error(error.detail || "Ошибка создания пользователя");
      }

      setAdminMsg(`Пользователь "${trimmedUserName}" успешно создан!`);
      setTimeout(() => setAdminMsg(""), 3000);
      setAdminForm(""); // Очищаем форму
      fetchAdminUsers();
    } catch (err) {
      console.error("Ошибка создания пользователя:", err);
      setAdminMsg(err instanceof Error ? err.message : "Ошибка создания пользователя");
      setTimeout(() => setAdminMsg(""), 3000);
    } finally {
      setAdminLoading(false);
    }
  };

  // Админ панель - загрузка настроек пользователя
  const loadUserSettings = async (userName: string) => {
    setAdminLoading(true);
    try {
      const res = await fetch(`/api/users/${userName}`);
      if (res.ok) {
        const data = await res.json();
        // Если options_json пустой или null, создаем базовую структуру
        let optionsJson = data.options_json || "{}";
        if (!optionsJson || optionsJson.trim() === "") {
          optionsJson = JSON.stringify({
            thresholds: { delta_pct: 1.0, volume_usdt: 10000.0, wick_pct: 50.0 },
            exchanges: { gate: true, binance: true, bitget: true, bybit: true, hyperliquid: true },
          });
        }
        setSelectedUserSettings({
          user: data.user,
          tg_token: data.tg_token || "",
          chat_id: data.chat_id || "",
          options_json: optionsJson,
        });
        
        // Загружаем настройки бирж в состояния для редактирования
        try {
          const options = JSON.parse(optionsJson);
          
          // Загружаем фильтры по биржам
          if (options.exchanges && typeof options.exchanges === "object") {
            setAdminExchangeFilters({
              binance: options.exchanges.binance !== false && options.exchanges.binance !== undefined ? options.exchanges.binance : true,
              bybit: options.exchanges.bybit !== false && options.exchanges.bybit !== undefined ? options.exchanges.bybit : true,
              bitget: options.exchanges.bitget !== false && options.exchanges.bitget !== undefined ? options.exchanges.bitget : true,
              gate: options.exchanges.gate !== false && options.exchanges.gate !== undefined ? options.exchanges.gate : true,
              hyperliquid: options.exchanges.hyperliquid !== false && options.exchanges.hyperliquid !== undefined ? options.exchanges.hyperliquid : true,
            });
          } else {
            setAdminExchangeFilters({
              binance: true,
              bybit: true,
              bitget: true,
              gate: true,
              hyperliquid: true,
            });
          }
          
          // Загружаем настройки бирж (Spot/Futures)
          if (options.exchangeSettings) {
            setAdminExchangeSettings((prevSettings) => {
              const merged = { ...prevSettings };
              Object.keys(options.exchangeSettings).forEach((exchange) => {
                if (merged[exchange]) {
                  merged[exchange] = {
                    spot: {
                      ...merged[exchange].spot,
                      ...options.exchangeSettings[exchange].spot,
                    },
                    futures: {
                      ...merged[exchange].futures,
                      ...options.exchangeSettings[exchange].futures,
                    },
                  };
                } else {
                  merged[exchange] = options.exchangeSettings[exchange];
                }
              });
              return merged;
            });
          }
          
          // Загружаем настройки пар
          if (options.pairSettings) {
            const migratedPairSettings: Record<string, { enabled: boolean; delta: string; volume: string; shadow: string }> = {};
            Object.entries(options.pairSettings).forEach(([key, value]: [string, any]) => {
              if (value && typeof value === 'object' && !('enabled' in value)) {
                migratedPairSettings[key] = {
                  enabled: true,
                  delta: value.delta || "0",
                  volume: value.volume || "0",
                  shadow: value.shadow || "0"
                };
              } else {
                migratedPairSettings[key] = value;
              }
            });
            setAdminPairSettings(migratedPairSettings);
          }
        } catch (e) {
          console.error("Ошибка парсинга options_json при загрузке:", e);
        }
      } else {
        throw new Error("Ошибка загрузки настроек");
      }
    } catch (err) {
      console.error("Ошибка загрузки настроек пользователя:", err);
      setAdminMsg("Ошибка загрузки настроек");
      setTimeout(() => setAdminMsg(""), 2000);
      setSelectedUserSettings(null);
    } finally {
      setAdminLoading(false);
    }
  };

  // Админ панель - удаление пользователя
  const deleteAdminUser = async (userName: string) => {
    // Убираем пробелы в начале и конце имени пользователя
    const trimmedUserName = userName.trim();
    
    if (!trimmedUserName) {
      setAdminMsg("Имя пользователя не может быть пустым");
      setTimeout(() => setAdminMsg(""), 3000);
      return;
    }
    
    // Запрещаем удаление системных пользователей "Stats" и "Влад"
    const lowerUserName = trimmedUserName.toLowerCase();
    if (lowerUserName === "stats" || lowerUserName === "влад") {
      setAdminMsg(`Нельзя удалить системного пользователя '${trimmedUserName}'`);
      setTimeout(() => setAdminMsg(""), 3000);
      return;
    }

    if (!confirm(`Удалить пользователя "${trimmedUserName}"?`)) return;

    setAdminLoading(true);
    try {
      // Кодируем имя пользователя для URL (важно для кириллицы и специальных символов)
      const encodedUserName = encodeURIComponent(trimmedUserName);
      const res = await fetch(`/api/users/${encodedUserName}/delete`, {
        method: "DELETE",
      });

      if (!res.ok) {
        // Пытаемся получить детальное сообщение об ошибке
        let errorMessage = "Ошибка удаления";
        try {
          const errorData = await res.json();
          errorMessage = errorData.error || errorData.detail || errorMessage;
        } catch {
          // Если не удалось распарсить JSON, используем стандартное сообщение
        }
        throw new Error(errorMessage);
      }

      const data = await res.json();
      setAdminMsg(data.message || "Пользователь удалён");
      setTimeout(() => setAdminMsg(""), 2000);
      fetchAdminUsers();
      if (selectedUserSettings?.user === trimmedUserName) {
        setSelectedUserSettings(null);
      }
    } catch (err) {
      console.error("Ошибка удаления:", err);
      const errorMessage = err instanceof Error ? err.message : "Ошибка удаления";
      setAdminMsg(errorMessage);
      setTimeout(() => setAdminMsg(""), 3000);
    } finally {
      setAdminLoading(false);
    }
  };

  // Админ панель - удаление рыночной статистики (пользователь "Stats")
  const deleteGlobalStats = async () => {
    // Подтверждение удаления
    const confirmed = window.confirm(
      "Вы уверены, что хотите удалить всю рыночную статистику стрел (пользователь 'Stats')? Это действие нельзя отменить."
    );
    
    if (!confirmed) return;
    
    setDeletingGlobalStats(true);
    try {
      const res = await fetch(`/api/users/Stats/spikes`, {
        method: "DELETE",
      });
      
      if (res.ok) {
        const data = await res.json();
        setAdminMsg(`Рыночная статистика успешно удалена. Удалено записей: ${data.deleted_count || 0}`);
        setTimeout(() => setAdminMsg(""), 5000);
      } else {
        const errorData = await res.json().catch(() => ({ error: "Неизвестная ошибка" }));
        setAdminMsg(`Ошибка при удалении рыночной статистики: ${errorData.error || errorData.detail || "Неизвестная ошибка"}`);
        setTimeout(() => setAdminMsg(""), 5000);
      }
    } catch (error) {
      console.error("Ошибка при удалении рыночной статистики:", error);
      setAdminMsg("Ошибка при удалении рыночной статистики. Попробуйте позже.");
      setTimeout(() => setAdminMsg(""), 5000);
    } finally {
      setDeletingGlobalStats(false);
    }
  };

  // Админ панель - копирование значений порогов во все биржи
  const copyThresholdsToAllExchanges = () => {
    if (!selectedUserSettings) return;
    
    try {
      // Получаем актуальные значения порогов из текущих настроек
      const options = selectedUserSettings.options_json 
        ? JSON.parse(selectedUserSettings.options_json) 
        : {};
      const thresholds = options.thresholds || { delta_pct: 1.0, volume_usdt: 10000.0, wick_pct: 50.0 };
      
      // Получаем значения из порогов (конвертируем в строки для совместимости с полями)
      const deltaValue = String(thresholds.delta_pct || 0);
      const volumeValue = String(thresholds.volume_usdt || 0);
      const shadowValue = String(thresholds.wick_pct || 0);
      
      // Список всех бирж
      const exchanges = ["binance", "bybit", "bitget", "gate", "hyperliquid"];
      
      // Обновляем настройки для всех бирж, сохраняя состояние enabled
      const updatedSettings = { ...adminExchangeSettings };
      
      exchanges.forEach((exchange) => {
        const currentSettings = adminExchangeSettings[exchange] || {
          spot: { enabled: true, delta: "0", volume: "0", shadow: "0" },
          futures: { enabled: true, delta: "0", volume: "0", shadow: "0" }
        };
        
        updatedSettings[exchange] = {
          spot: {
            ...currentSettings.spot,
            delta: deltaValue,
            volume: volumeValue,
            shadow: shadowValue,
          },
          futures: {
            ...currentSettings.futures,
            delta: deltaValue,
            volume: volumeValue,
            shadow: shadowValue,
          },
        };
      });
      
      setAdminExchangeSettings(updatedSettings);
      setAdminMsg("Значения порогов скопированы во все биржи (Spot и Futures)!");
      setTimeout(() => setAdminMsg(""), 3000);
    } catch (e) {
      console.error("Ошибка при копировании значений:", e);
      setAdminMsg("Ошибка при копировании значений");
      setTimeout(() => setAdminMsg(""), 3000);
    }
  };

  // Админ панель - сохранение настроек пользователя
  const saveAdminUserSettings = async () => {
    if (!selectedUserSettings) return;

    setAdminLoading(true);
    try {
      // Получаем текущие настройки из options_json и обновляем их
      let options: any = {};
      try {
        options = selectedUserSettings.options_json ? JSON.parse(selectedUserSettings.options_json) : {};
      } catch (e) {
        options = {};
      }
      
      // Обновляем настройки из состояний редактирования
      options.exchanges = adminExchangeFilters;
      options.exchangeSettings = adminExchangeSettings;
      options.pairSettings = adminPairSettings;
      
      // Сохраняем пороги детектора (они уже должны быть в options из selectedUserSettings.options_json,
      // но убеждаемся, что они есть, иначе используем дефолтные значения)
      if (!options.thresholds) {
        options.thresholds = { delta_pct: 1.0, volume_usdt: 10000.0, wick_pct: 50.0 };
      }
      // Пороги уже обновлены через onChange в UI и находятся в options из selectedUserSettings.options_json
      
      const optionsJson = JSON.stringify(options);

      const res = await fetch(`/api/users/${selectedUserSettings.user}/settings`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          tg_token: selectedUserSettings.tg_token || "",
          chat_id: selectedUserSettings.chat_id || "",
          options_json: optionsJson,
        }),
      });

      if (!res.ok) {
        const error = await res.json();
        throw new Error(error.detail || "Ошибка сохранения");
      }

      setAdminMsg("Настройки успешно сохранены!");
      setTimeout(() => setAdminMsg(""), 3000);
      fetchAdminUsers(); // Обновляем список пользователей
      // Обновляем текущие настройки, чтобы они соответствовали сохраненным
      setSelectedUserSettings({
        ...selectedUserSettings,
        options_json: optionsJson,
      });
    } catch (err) {
      console.error("Ошибка сохранения настроек:", err);
      setAdminMsg(err instanceof Error ? err.message : "Ошибка сохранения настроек");
      setTimeout(() => setAdminMsg(""), 3000);
    } finally {
      setAdminLoading(false);
    }
  };

  useEffect(() => {
    // Проверяем авторизацию
    if (typeof window !== "undefined") {
      const token = localStorage.getItem("auth_token");
      const login = localStorage.getItem("user_login");
      
      if (!token) {
        router.push("/login");
        return;
      }

      setUserLogin(login || "");
    }
    
    fetchMetrics();
    setLoading(false);
    
    // Автообновление каждые 10 секунд
    const interval = setInterval(fetchMetrics, 10000);
    
    // Периодическая проверка статуса бирж на основе времени последнего обновления
    const statusCheckInterval = setInterval(() => {
      setExchanges((prevExchanges) => {
        const now = Date.now();
        const oneMinuteAgo = now - 60 * 1000; // 1 минута в миллисекундах
        
        return prevExchanges.map((exchange) => {
          // Если есть timestamp последнего обновления и оно старше минуты - биржа отключена
          if (exchange.lastUpdateTimestamp && exchange.lastUpdateTimestamp < oneMinuteAgo) {
            return {
              ...exchange,
              status: "inactive" as const
            };
          }
          // Если статус был inactive, но данные обновились - проверяем через fetchMetrics
          return exchange;
        });
      });
    }, 5000); // Проверяем каждые 5 секунд
    
    return () => {
      clearInterval(interval);
      clearInterval(statusCheckInterval);
    };
  }, [router]);

  // Загрузка настроек пользователя после установки userLogin
  useEffect(() => {
    if (userLogin) {
      fetchUserSettings();
    }
  }, [userLogin]);

  // Загрузка пользователей админ панели при переключении на вкладку
  useEffect(() => {
    if (activeTab === "admin" && isAdmin) {
      fetchAdminUsers();
      fetchErrorLogs();
    }
  }, [activeTab, isAdmin]);

  // Обновление логов при изменении фильтров
  useEffect(() => {
    if (activeTab === "admin" && isAdmin) {
      const timer = setTimeout(() => {
        fetchErrorLogs();
      }, 300); // Небольшая задержка для дебаунса
      return () => clearTimeout(timer);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [errorLogsFilter.exchange, errorLogsFilter.error_type, errorLogsFilter.limit]);

  // Админ панель - загрузка логов ошибок
  const fetchErrorLogs = async () => {
    setErrorLogsLoading(true);
    try {
      const params = new URLSearchParams();
      if (errorLogsFilter.exchange) {
        params.append("exchange", errorLogsFilter.exchange);
      }
      if (errorLogsFilter.error_type) {
        params.append("error_type", errorLogsFilter.error_type);
      }
      params.append("limit", errorLogsFilter.limit.toString());

      const res = await fetch(`/api/errors?${params.toString()}`);
      if (res.ok) {
        const data = await res.json();
        setErrorLogs(data.errors || []);
      } else {
        throw new Error("Ошибка загрузки логов");
      }
    } catch (err) {
      console.error("Ошибка загрузки логов:", err);
      setErrorLogs([]);
    } finally {
      setErrorLogsLoading(false);
    }
  };

  // Удаление одного лога ошибки
  const deleteError = async (errorId: number) => {
    if (!isAdmin) {
      alert("Удаление логов ошибок доступно только для пользователя 'Влад'");
      return;
    }

    if (!confirm("Вы уверены, что хотите удалить этот лог ошибки?")) {
      return;
    }

    try {
      const params = new URLSearchParams();
      params.append("error_id", errorId.toString());
      params.append("user", userLogin);

      const res = await fetch(`/api/errors?${params.toString()}`, {
        method: "DELETE",
      });

      if (res.ok) {
        // Обновляем список логов
        fetchErrorLogs();
      } else {
        const data = await res.json();
        alert(data.error || "Ошибка при удалении лога");
      }
    } catch (err) {
      console.error("Ошибка удаления лога:", err);
      alert("Ошибка при удалении лога");
    }
  };

  // Удаление всех логов ошибок
  const deleteAllErrors = async () => {
    if (!isAdmin) {
      alert("Удаление всех логов ошибок доступно только для пользователя 'Влад'");
      return;
    }

    if (!confirm("Вы уверены, что хотите удалить ВСЕ логи ошибок? Это действие нельзя отменить.")) {
      return;
    }

    try {
      const params = new URLSearchParams();
      params.append("user", userLogin);

      const res = await fetch(`/api/errors?${params.toString()}`, {
        method: "DELETE",
      });

      if (res.ok) {
        const data = await res.json();
        alert(`Успешно удалено ${data.deleted_count || 0} логов ошибок`);
        // Обновляем список логов
        fetchErrorLogs();
      } else {
        const data = await res.json();
        alert(data.error || "Ошибка при удалении логов");
      }
    } catch (err) {
      console.error("Ошибка удаления всех логов:", err);
      alert("Ошибка при удалении логов");
    }
  };
  
  // Загрузка статистики стрел при переключении на вкладку
  // Автоматическое скрытие уведомлений
  useEffect(() => {
    if (saveMessage) {
      const timer = setTimeout(() => {
        setSaveMessage(null);
      }, 3000); // Исчезает через 3 секунды
      return () => clearTimeout(timer);
    }
  }, [saveMessage]);


  // Состояние для деталей по монете
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);
  const [symbolSpikes, setSymbolSpikes] = useState<any[]>([]);
  const [symbolSpikesLoading, setSymbolSpikesLoading] = useState(false);

  useEffect(() => {
    const fetchSpikesStats = async () => {
      if (activeTab === "statistics") {
        setSpikesStatsLoading(true);
        try {
          let url: string;
          if (statisticsMode === "personal") {
            // Личная статистика текущего пользователя
            url = `/api/users/${encodeURIComponent(userLogin)}/spikes/stats?days=${statisticsPeriod}`;
          } else {
            // Рыночная статистика (пользователь Stats)
            url = `/api/users/Stats/spikes/stats?days=${statisticsPeriod}`;
          }
          
          const res = await fetch(url);
          if (res.ok) {
            const data = await res.json();
            setSpikesStats(data);
          } else {
            console.error("Ошибка загрузки статистики стрел:", res.status);
            setSpikesStats(null);
          }
        } catch (error) {
          console.error("Ошибка загрузки статистики стрел:", error);
          setSpikesStats(null);
        } finally {
          setSpikesStatsLoading(false);
        }
      }
    };
    
    fetchSpikesStats();
  }, [activeTab, statisticsMode, statisticsPeriod, userLogin]);

  // Загрузка деталей по монете
  useEffect(() => {
    const fetchSymbolSpikes = async () => {
      if (selectedSymbol) {
        setSymbolSpikesLoading(true);
        try {
          let url: string;
          if (statisticsMode === "personal") {
            // Личная статистика текущего пользователя
            url = `/api/users/${encodeURIComponent(userLogin)}/spikes/by-symbol/${encodeURIComponent(selectedSymbol)}`;
          } else {
            // Рыночная статистика (пользователь Stats)
            url = `/api/users/Stats/spikes/by-symbol/${encodeURIComponent(selectedSymbol)}`;
          }
          
          const res = await fetch(url);
          if (res.ok) {
            const data = await res.json();
            setSymbolSpikes(data.spikes || []);
          } else {
            console.error("Ошибка загрузки деталей по монете:", res.status);
            setSymbolSpikes([]);
          }
        } catch (error) {
          console.error("Ошибка загрузки деталей по монете:", error);
          setSymbolSpikes([]);
        } finally {
          setSymbolSpikesLoading(false);
        }
      }
    };
    
    fetchSymbolSpikes();
  }, [selectedSymbol, statisticsMode, userLogin]);

  // Функция для очистки статистики стрел пользователя
  const handleDeleteSpikes = async () => {
    if (!userLogin) return;
    
    // Подтверждение очистки
    const confirmed = window.confirm(
      "Вы уверены, что хотите очистить всю вашу статистику стрел? Это действие нельзя отменить."
    );
    
    if (!confirmed) return;
    
    setDeletingSpikes(true);
    try {
      const res = await fetch(`/api/users/${encodeURIComponent(userLogin)}/spikes`, {
        method: "DELETE",
      });
      
      if (res.ok) {
        const data = await res.json();
        alert(`Статистика успешно очищена. Удалено записей: ${data.deleted_count || 0}`);
        // Обновляем статистику после удаления - сбрасываем и перезагружаем
        setSpikesStats(null);
        // Перезагружаем статистику
        try {
          const statsRes = await fetch(`/api/users/${encodeURIComponent(userLogin)}/spikes/stats?days=${statisticsPeriod}`);
          if (statsRes.ok) {
            const statsData = await statsRes.json();
            setSpikesStats(statsData);
          }
        } catch (statsError) {
          console.error("Ошибка при обновлении статистики после удаления:", statsError);
        }
      } else {
        const errorData = await res.json().catch(() => ({ error: "Неизвестная ошибка" }));
        alert(`Ошибка при очистке статистики: ${errorData.error || errorData.detail || "Неизвестная ошибка"}`);
      }
    } catch (error) {
      console.error("Ошибка при очистке статистики:", error);
      alert("Ошибка при очистке статистики. Попробуйте позже.");
    } finally {
      setDeletingSpikes(false);
    }
  };

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center gradient-bg">
        <div className="flex flex-col items-center gap-4">
          <div className="w-16 h-16 border-4 border-emerald-500 border-t-transparent rounded-full animate-spin"></div>
          <div className="text-white text-xl animate-pulse-slow">Загрузка...</div>
        </div>
      </div>
    );
  }

  // Подсчитываем активные подключения (spot или linear считаются отдельно)
  // Активные - это все биржи, которые получают свечи (не "inactive")
  // Т.е. статус "active" или "problems" - оба считаются активными
  const activeExchanges = exchanges.filter(e => e.status !== "inactive").length;
  const totalCandles = exchanges.reduce((sum, e) => sum + e.candles, 0);

  const formatNumber = (num: number) => {
    return new Intl.NumberFormat("ru-RU").format(num);
  };

  // Форматирование времени работы программы
  const formatUptime = (seconds: number): string => {
    if (seconds === 0) {
      return "неизвестно";
    }
    
    const days = Math.floor(seconds / 86400);
    const hours = Math.floor((seconds % 86400) / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;
    
    const parts: string[] = [];
    
    if (days > 0) {
      parts.push(`${days} ${days === 1 ? 'день' : days < 5 ? 'дня' : 'дней'}`);
    }
    if (hours > 0) {
      parts.push(`${hours} ${hours === 1 ? 'час' : hours < 5 ? 'часа' : 'часов'}`);
    }
    if (minutes > 0 && days === 0) {
      parts.push(`${minutes} ${minutes === 1 ? 'минуту' : minutes < 5 ? 'минуты' : 'минут'}`);
    }
    if (secs > 0 && days === 0 && hours === 0) {
      parts.push(`${secs} ${secs === 1 ? 'секунду' : secs < 5 ? 'секунды' : 'секунд'}`);
    }
    
    if (parts.length === 0) {
      return "менее секунды";
    }
    
    return parts.join(" ");
  };

  // Валидация Bot Token
  const validateBotToken = (token: string): string => {
    if (!token.trim()) {
      return ""; // Пустое поле - не ошибка
    }
    
    // Формат: число:буквы_и_цифры
    // Пример: 1234567890:ABCdefGHIjkIMNOpqrsTUVwxyz
    // Число: от 8 до 12 цифр, затем двоеточие, затем строка из букв, цифр, подчёркиваний и дефисов (от 30 до 40 символов)
    const botTokenRegex = /^\d{8,12}:[A-Za-z0-9_-]{30,40}$/;
    
    if (!botTokenRegex.test(token)) {
      return "Неверный формат Bot Token. Формат: число:буквы (например: 1234567890:ABCdefGHIjkIMNOpqrsTUVwxyz)";
    }
    
    return "";
  };

  // Валидация Chat ID
  const validateChatId = (chatId: string): string => {
    if (!chatId.trim()) {
      return ""; // Пустое поле - не ошибка
    }
    
    // Chat ID - это число (может быть отрицательным для групп)
    // Обычно от 8 до 11 цифр, но может быть больше
    const chatIdRegex = /^-?\d{8,20}$/;
    
    if (!chatIdRegex.test(chatId)) {
      return "Неверный формат Chat ID. Chat ID должен быть числом от 8 до 20 цифр (например: 123456789 для личных чатов или -1001234567890 для групп/каналов). Разверните инструкцию ниже, чтобы узнать, как получить Chat ID.";
    }
    
    return "";
  };

  const getAdminUserStatus = (user: AdminUser) => {
    const hasToken = Boolean(user.tg_token && user.tg_token.trim().length > 0);
    const hasChat = Boolean(user.chat_id && user.chat_id.trim().length > 0);
    const telegramActive = user.has_telegram || (hasToken && hasChat);

    let settingsActive = false;
    const raw = user.options_json;

    if (raw) {
      try {
        const trimmed = raw.trim();
        if (trimmed.length === 0 || trimmed === "{}") {
          settingsActive = false;
        } else {
          const opts = JSON.parse(trimmed);

          const hasNonZeroNumericValue = (value: unknown): boolean => {
            if (typeof value === "number") {
              return value !== 0;
            }
            if (typeof value === "string") {
              const normalized = value.replace(/\s+/g, "").replace(/,/g, ".");
              if (!normalized) return false;
              const numeric = Number(normalized);
              if (!Number.isFinite(numeric)) {
                return false;
              }
              return numeric !== 0;
            }
            return false;
          };

          const hasNonZeroThresholds = (input: unknown): boolean => {
            if (!input) return false;

            if (Array.isArray(input)) {
              return input.some((item) => {
                if (typeof item === "boolean") return false;
                if (typeof item === "object" && item !== null) {
                  return hasNonZeroThresholds(item);
                }
                return hasNonZeroNumericValue(item);
              });
            }

            if (typeof input === "object") {
              return Object.entries(input as Record<string, unknown>).some(([key, value]) => {
                if (key === "enabled") return false;
                if (typeof value === "boolean") return false;
                if (value && typeof value === "object") {
                  return hasNonZeroThresholds(value);
                }
                return hasNonZeroNumericValue(value);
              });
            }

            return hasNonZeroNumericValue(input);
          };

          const exchangeSettingsActive = hasNonZeroThresholds(opts?.exchangeSettings);
          const pairSettingsActive = hasNonZeroThresholds(opts?.pairSettings);

          settingsActive = Boolean(exchangeSettingsActive || pairSettingsActive);
        }
      } catch (e) {
        console.warn("[AdminTab] Невозможно распарсить options_json", e);
        settingsActive = true;
      }
    }

    return { telegramActive, settingsActive };
  };

  return (
    <div className="min-h-screen gradient-bg flex">
      {/* Mobile Menu Overlay */}
      {isMobileMenuOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-40 md:hidden"
          onClick={() => setIsMobileMenuOpen(false)}
        />
      )}

      {/* Sidebar */}
      <div className={`fixed md:static inset-y-0 left-0 z-50 w-64 glass-strong border-r border-zinc-800 flex flex-col animate-slide-in transform transition-transform duration-300 ease-in-out ${
        isMobileMenuOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0'
      }`}>
        {/* Header */}
        <div className="p-6 border-b border-zinc-800">
          <div className="flex items-center gap-3 mb-3">
            <div className="w-8 h-8 bg-gradient-to-br from-emerald-500 to-emerald-600 rounded-lg flex items-center justify-center shadow-emerald hover-glow">
              <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
              </svg>
            </div>
            <h1 className="text-xl font-bold gradient-text">Exchange Monitor</h1>
          </div>
          <p className="text-sm text-zinc-400">{userLogin || "user"}</p>
        </div>

        {/* Navigation */}
        <nav className="flex-1 p-4 space-y-2">
          <button
            onClick={() => {
              setActiveTab("monitoring");
              setIsMobileMenuOpen(false);
            }}
            className={`w-full flex items-center gap-3 px-4 py-3 rounded-lg smooth-transition ripple ${
              activeTab === "monitoring"
                ? "bg-gradient-to-r from-emerald-500 to-emerald-600 text-white shadow-emerald nav-active"
                : "text-zinc-400 hover:text-white hover:bg-zinc-800/50 hover-glow"
            }`}
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
            </svg>
            Мониторинг
          </button>

          <button
            onClick={() => {
              setActiveTab("statistics");
              setIsMobileMenuOpen(false);
            }}
            className={`w-full flex items-center gap-3 px-4 py-3 rounded-lg smooth-transition ripple ${
              activeTab === "statistics"
                ? "bg-gradient-to-r from-emerald-500 to-emerald-600 text-white shadow-emerald nav-active"
                : "text-zinc-400 hover:text-white hover:bg-zinc-800/50 hover-glow"
            }`}
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
            </svg>
            Статистика стрел
          </button>

          <button
            onClick={() => {
              setActiveTab("settings");
              setIsMobileMenuOpen(false);
            }}
            className={`w-full flex items-center gap-3 px-4 py-3 rounded-lg smooth-transition ripple ${
              activeTab === "settings"
                ? "bg-gradient-to-r from-emerald-500 to-emerald-600 text-white shadow-emerald nav-active"
                : "text-zinc-400 hover:text-white hover:bg-zinc-800/50 hover-glow"
            }`}
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
            Настройки
          </button>

          {/* Админ панель - только для Влад */}
          {isAdmin && (
            <button
              onClick={() => {
                setActiveTab("admin");
                setIsMobileMenuOpen(false);
              }}
              className={`w-full flex items-center gap-3 px-4 py-3 rounded-lg smooth-transition ripple ${
                activeTab === "admin"
                  ? "bg-gradient-to-r from-emerald-500 to-emerald-600 text-white shadow-emerald nav-active"
                  : "text-zinc-400 hover:text-white hover:bg-zinc-800/50 hover-glow"
              }`}
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
              </svg>
              Админ панель
            </button>
          )}
        </nav>

        {/* Logout */}
        <div className="p-4 border-t border-zinc-800">
          <button
            onClick={() => {
              localStorage.removeItem("auth_token");
              localStorage.removeItem("user_login");
              router.push("/login");
            }}
            className="w-full flex items-center gap-3 px-4 py-3 rounded-lg text-zinc-400 hover:text-white hover:bg-zinc-800/50 smooth-transition ripple hover-glow"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
            </svg>
            Выход
          </button>
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1 overflow-auto">
        <div className="p-4 md:p-8">
          {/* Mobile Header with Hamburger */}
          <div className="md:hidden mb-4 flex items-center justify-between">
            <button
              onClick={() => setIsMobileMenuOpen(true)}
              className="p-2 glass rounded-lg hover:bg-zinc-800/50 smooth-transition ripple"
              aria-label="Открыть меню"
            >
              <svg className="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
              </svg>
            </button>
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 bg-gradient-to-br from-emerald-500 to-emerald-600 rounded-lg flex items-center justify-center shadow-emerald">
                <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                </svg>
              </div>
              <h1 className="text-lg font-bold gradient-text">Exchange Monitor</h1>
            </div>
          </div>

          {/* Conditional Content based on activeTab */}
          {activeTab === "monitoring" && (
            <>
              {/* Header */}
              <div className="mb-6 md:mb-8 animate-fade-in">
                <h1 className="text-2xl md:text-3xl font-bold gradient-text mb-2">Мониторинг бирж</h1>
                <p className="text-zinc-400">
                  Статус подключения и статистика в реальном времени
                </p>
              </div>

          {/* Summary Cards */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
            {/* Детекты */}
            <div className="glass-strong border border-zinc-800 rounded-xl p-6 relative overflow-hidden card-hover gradient-border float-animation shadow-emerald animate-scale-in">
              <div className="absolute top-4 right-4 text-emerald-500 opacity-20">
                <svg className="w-16 h-16" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                </svg>
              </div>
              <div className="text-sm text-zinc-400 mb-2">Детекты</div>
              <div className="text-4xl font-bold text-white">{formatNumber(totalDetects)}</div>
              <div className="text-xs text-zinc-500 mt-2">Детектов с момента запуска</div>
            </div>

            {/* Активные */}
            <div className="glass-strong border border-zinc-800 rounded-xl p-6 relative overflow-hidden card-hover gradient-border float-animation shadow-blue animate-scale-in" style={{ animationDelay: '0.2s' }}>
              <div className="absolute top-4 right-4 text-blue-500 opacity-20">
                <svg className="w-16 h-16" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                </svg>
              </div>
              <div className="text-sm text-zinc-400 mb-2">Активные</div>
              <div className="text-4xl font-bold text-blue-400">{activeExchanges}</div>
              <div className="text-xs text-zinc-500 mt-2">Активных подключений</div>
            </div>

            {/* Всего свечей */}
            <div className="glass-strong border border-zinc-800 rounded-xl p-6 relative overflow-hidden card-hover gradient-border float-animation shadow-purple animate-scale-in" style={{ animationDelay: '0.4s' }}>
              <div className="absolute top-4 right-4 text-purple-500 opacity-20">
                <svg className="w-16 h-16" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              </div>
              <div className="text-sm text-zinc-400 mb-2">Всего свечей</div>
              <div className="text-4xl font-bold text-white">{formatNumber(totalCandles)}</div>
              <div className="text-xs text-zinc-500 mt-2">
                Собрано данных 1s за {formatUptime(uptimeSeconds)}
              </div>
            </div>

            {/* Время работы */}
            <div className="glass-strong border border-zinc-800 rounded-xl p-6 relative overflow-hidden card-hover gradient-border float-animation shadow-orange animate-scale-in" style={{ animationDelay: '0.6s' }}>
              <div className="absolute top-4 right-4 text-orange-500 opacity-20">
                <svg className="w-16 h-16" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              </div>
              <div className="text-sm text-zinc-400 mb-2">Время работы</div>
              <div className="text-4xl font-bold text-white">{formatUptime(uptimeSeconds)}</div>
              <div className="text-xs text-zinc-500 mt-2">
                {startTime ? new Date(startTime * 1000).toLocaleString('ru-RU', { 
                  day: '2-digit', 
                  month: '2-digit', 
                  year: 'numeric', 
                  hour: '2-digit', 
                  minute: '2-digit' 
                }) : 'Неизвестно'}
              </div>
            </div>
          </div>

          {/* Exchange Status Table */}
          <div className="glass-strong border border-zinc-800 rounded-xl overflow-hidden card-hover animate-fade-in">
            <div className="p-6 border-b border-zinc-800">
              <h2 className="text-xl font-bold gradient-text mb-1">Состояние бирж</h2>
              <p className="text-sm text-zinc-400">Детальная информация по каждой бирже</p>
            </div>

            <div className="overflow-x-auto table-responsive">
              <table className="w-full">
                <thead className="bg-zinc-800/50">
                  <tr>
                    <th className="px-3 md:px-6 py-3 md:py-4 text-left text-xs md:text-sm font-semibold text-zinc-300">Биржа</th>
                    <th className="px-3 md:px-6 py-3 md:py-4 text-left text-xs md:text-sm font-semibold text-zinc-300">Статус</th>
                    <th className="px-3 md:px-6 py-3 md:py-4 text-left text-xs md:text-sm font-semibold text-zinc-300">Торговые пары</th>
                    <th className="px-3 md:px-6 py-3 md:py-4 text-left text-xs md:text-sm font-semibold text-zinc-300">WebSocket</th>
                    <th className="px-3 md:px-6 py-3 md:py-4 text-left text-xs md:text-sm font-semibold text-zinc-300">Свечи 1s</th>
                    <th className="px-3 md:px-6 py-3 md:py-4 text-left text-xs md:text-sm font-semibold text-zinc-300">Переподключения</th>
                    <th className="px-3 md:px-6 py-3 md:py-4 text-left text-xs md:text-sm font-semibold text-zinc-300">T/s</th>
                    <th className="px-3 md:px-6 py-3 md:py-4 text-left text-xs md:text-sm font-semibold text-zinc-300">Обновлено</th>
                  </tr>
                </thead>
                <tbody>
                  {exchanges.map((exchange) => (
                    <tr key={`${exchange.name}-${exchange.market}`} className="border-t border-zinc-800 table-row-hover">
                      <td className="px-3 md:px-6 py-3 md:py-4 text-white font-medium text-sm">
                        {exchange.name} <span className="text-zinc-500 text-xs">({exchange.market})</span>
                      </td>
                      <td className="px-3 md:px-6 py-3 md:py-4">
                        <span
                          className={`px-2 md:px-3 py-1 rounded-full text-xs font-medium smooth-transition ${
                            exchange.status === "active"
                              ? "bg-green-500/20 text-green-400 border border-green-500/50 status-pulse"
                              : exchange.status === "problems"
                              ? "bg-yellow-500/20 text-yellow-400 border border-yellow-500/50"
                              : "bg-red-500/20 text-red-400 border border-red-500/50"
                          }`}
                        >
                          {exchange.status === "active" ? "Активна" : exchange.status === "problems" ? "Проблемы" : "Отключена"}
                        </span>
                      </td>
                      <td className="px-3 md:px-6 py-3 md:py-4 text-zinc-300 text-sm">{formatNumber(exchange.tradingPairs)}</td>
                      <td className="px-3 md:px-6 py-3 md:py-4 text-zinc-300 text-xs md:text-sm">{exchange.websocketInfo}</td>
                      <td className="px-3 md:px-6 py-3 md:py-4 text-zinc-300 text-sm">{formatNumber(exchange.candles)}</td>
                      <td className="px-3 md:px-6 py-3 md:py-4 text-zinc-300 text-sm">{formatNumber(exchange.reconnects)}</td>
                      <td className="px-3 md:px-6 py-3 md:py-4 text-zinc-300 text-sm">{exchange.tps > 0 ? exchange.tps.toFixed(2) : "0"}</td>
                      <td className="px-3 md:px-6 py-3 md:py-4 text-zinc-400 text-xs md:text-sm">{exchange.lastUpdate || "Нет данных"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
            </>
          )}

          {activeTab === "statistics" && (
            <div className="mb-6 md:mb-8 animate-fade-in">
              <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 mb-4">
                <div>
                  <h1 className="text-2xl md:text-3xl font-bold gradient-text mb-2">Статистика стрел</h1>
                  <p className="text-zinc-400">
                    {statisticsMode === "personal" 
                      ? `Статистика по вашим детектам за последние ${statisticsPeriod} дней (с учетом ваших фильтров)`
                      : `Рыночная статистика по детектам за последние ${statisticsPeriod} дней (с учетом настроек пользователя Stats)`}
                  </p>
                </div>
                <div className="flex items-center gap-3">
                  {/* Селектор периода */}
                  <select
                    value={statisticsPeriod}
                    onChange={(e) => setStatisticsPeriod(Number(e.target.value))}
                    className="bg-zinc-900 border border-zinc-800 rounded-lg px-4 py-2 text-sm text-white focus:outline-none focus:ring-2 focus:ring-emerald-500"
                  >
                    <option value={7}>7 дней</option>
                    <option value={14}>14 дней</option>
                    <option value={30}>30 дней</option>
                    <option value={60}>60 дней</option>
                    <option value={90}>90 дней</option>
                    <option value={180}>180 дней</option>
                    <option value={365}>365 дней</option>
                  </select>
                  {/* Переключатель между личной и общей статистикой */}
                  <div className="flex items-center gap-2 bg-zinc-900 border border-zinc-800 rounded-lg p-1">
                    <button
                      onClick={() => setStatisticsMode("personal")}
                      className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                        statisticsMode === "personal"
                          ? "bg-emerald-500 text-white shadow-emerald"
                          : "text-zinc-400 hover:text-white hover:bg-zinc-800"
                      }`}
                    >
                      Моя статистика
                    </button>
                    <button
                      onClick={() => setStatisticsMode("global")}
                      className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                        statisticsMode === "global"
                          ? "bg-emerald-500 text-white shadow-emerald"
                          : "text-zinc-400 hover:text-white hover:bg-zinc-800"
                      }`}
                    >
                      Рыночная статистика
                    </button>
                  </div>
                  {/* Кнопка очистки статистики (только для личной статистики) */}
                  {statisticsMode === "personal" && (
                    <button
                      onClick={handleDeleteSpikes}
                      disabled={deletingSpikes}
                      className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                        deletingSpikes
                          ? "bg-zinc-700 text-zinc-400 cursor-not-allowed"
                          : "bg-red-600 hover:bg-red-700 text-white"
                      }`}
                      title="Очистить всю мою статистику стрел"
                    >
                      {deletingSpikes ? (
                        <span className="flex items-center gap-2">
                          <span className="w-4 h-4 border-2 border-zinc-400 border-t-transparent rounded-full animate-spin"></span>
                          Очищение...
                        </span>
                      ) : (
                        "🗑️ Очистить мою статистику"
                      )}
                    </button>
                  )}
                </div>
              </div>
              
              {spikesStatsLoading ? (
                <div className="flex items-center justify-center py-12">
                  <div className="flex flex-col items-center gap-4">
                    <div className="w-12 h-12 border-4 border-emerald-500 border-t-transparent rounded-full animate-spin"></div>
                    <div className="text-white text-xl animate-pulse-slow">Загрузка статистики...</div>
                  </div>
                </div>
              ) : spikesStats ? (
                <>
                  {/* Карточки со сводной статистикой */}
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
                    <div className="glass-strong border border-zinc-800 rounded-xl p-6 card-hover gradient-border float-animation shadow-emerald animate-scale-in">
                      <div className="text-zinc-400 text-sm mb-1">Всего детектов</div>
                      <div className="text-3xl font-bold text-white">{formatNumber(spikesStats.total_count)}</div>
                    </div>
                    <div className="glass-strong border border-zinc-800 rounded-xl p-6 card-hover gradient-border float-animation shadow-blue animate-scale-in" style={{ animationDelay: '0.1s' }}>
                      <div className="text-zinc-400 text-sm mb-1">Средняя дельта</div>
                      <div className="text-3xl font-bold text-white">{spikesStats.avg_delta.toFixed(2)}%</div>
                    </div>
                    <div className="glass-strong border border-zinc-800 rounded-xl p-6 card-hover gradient-border float-animation shadow-purple animate-scale-in" style={{ animationDelay: '0.2s' }}>
                      <div className="text-zinc-400 text-sm mb-1">Средний объём</div>
                      <div className="text-3xl font-bold text-white">${formatNumber(Math.round(spikesStats.avg_volume))}</div>
                    </div>
                  </div>
                  
                  {/* График детектов по дням (линейный) */}
                  {spikesStats.chart_data.length > 0 && (() => {
                    const maxCount = Math.max(...spikesStats.chart_data.map(d => d.count), 1);
                    const dataPoints = spikesStats.chart_data.length;
                    const paddingLeft = 70;
                    const paddingRight = 30;
                    const paddingTop = 30;
                    const paddingBottom = 60;
                    const chartHeight = 350;
                    
                    // Генерируем значения для вертикальной оси
                    const yAxisSteps = 5;
                    const yStep = Math.ceil(maxCount / yAxisSteps);
                    const yAxisMax = yStep * yAxisSteps;
                    const yAxisValues = Array.from({ length: yAxisSteps + 1 }, (_, i) => i * yStep);
                    
                    return (
                      <div className="glass-strong border border-zinc-800 rounded-xl p-6 mb-8 card-hover animate-fade-in">
                        <h2 className="text-xl font-semibold gradient-text mb-6">Детекты по дням</h2>
                        <div className="relative w-full" style={{ minHeight: '450px' }}>
                          <svg className="w-full" style={{ height: `${chartHeight + paddingTop + paddingBottom}px` }} viewBox={`0 0 1000 ${chartHeight + paddingTop + paddingBottom}`} preserveAspectRatio="none">
                            <defs>
                              <linearGradient id="lineGradient" x1="0%" y1="0%" x2="0%" y2="100%">
                                <stop offset="0%" stopColor="#10b981" stopOpacity="0.3" />
                                <stop offset="100%" stopColor="#10b981" stopOpacity="0" />
                              </linearGradient>
                            </defs>
                            
                            {(() => {
                              const chartWidth = 1000 - paddingLeft - paddingRight;
                              const stepX = dataPoints > 1 ? chartWidth / (dataPoints - 1) : 0;
                              
                              return (
                                <>
                                  {/* Вертикальная ось (количество детектов) */}
                                  <line
                                    x1={paddingLeft}
                                    y1={paddingTop}
                                    x2={paddingLeft}
                                    y2={chartHeight + paddingTop}
                                    stroke="#4b5563"
                                    strokeWidth="2"
                                  />
                                  
                                  {/* Горизонтальная ось (даты) */}
                                  <line
                                    x1={paddingLeft}
                                    y1={chartHeight + paddingTop}
                                    x2={1000 - paddingRight}
                                    y2={chartHeight + paddingTop}
                                    stroke="#4b5563"
                                    strokeWidth="2"
                                  />
                                  
                                  {/* Деления и подписи на вертикальной оси */}
                                  {yAxisValues.map((value, idx) => {
                                    const y = chartHeight + paddingTop - (value / yAxisMax) * chartHeight;
                                    return (
                                      <g key={idx}>
                                        <line
                                          x1={paddingLeft - 6}
                                          y1={y}
                                          x2={paddingLeft}
                                          y2={y}
                                          stroke="#6b7280"
                                          strokeWidth="1.5"
                                        />
                                        <text
                                          x={paddingLeft - 15}
                                          y={y + 5}
                                          textAnchor="end"
                                          fill="#9ca3af"
                                          fontSize="12"
                                          fontFamily="system-ui, -apple-system, sans-serif"
                                          fontWeight="500"
                                        >
                                          {value}
                                        </text>
                                      </g>
                                    );
                                  })}
                                  
                                  {/* Область под линией */}
                                  <path
                                    d={`M ${paddingLeft},${chartHeight + paddingTop} ${spikesStats.chart_data.map((item, idx) => {
                                      const y = chartHeight + paddingTop - (item.count / yAxisMax) * chartHeight;
                                      const x = paddingLeft + idx * stepX;
                                      return `L ${x},${y}`;
                                    }).join(' ')} L ${paddingLeft + (dataPoints - 1) * stepX},${chartHeight + paddingTop} Z`}
                                    fill="url(#lineGradient)"
                                  />
                                  
                                  {/* Линия графика */}
                                  <polyline
                                    points={spikesStats.chart_data.map((item, idx) => {
                                      const y = chartHeight + paddingTop - (item.count / yAxisMax) * chartHeight;
                                      const x = paddingLeft + idx * stepX;
                                      return `${x},${y}`;
                                    }).join(' ')}
                                    fill="none"
                                    stroke="#10b981"
                                    strokeWidth="2.5"
                                    strokeLinecap="round"
                                    strokeLinejoin="round"
                                  />
                                  
                                  {/* Точки на графике (уменьшенные) */}
                                  {spikesStats.chart_data.map((item, idx) => {
                                    const y = chartHeight + paddingTop - (item.count / yAxisMax) * chartHeight;
                                    const x = paddingLeft + idx * stepX;
                                    return (
                                      <circle
                                        key={idx}
                                        cx={x}
                                        cy={y}
                                        r="3"
                                        fill="#10b981"
                                        stroke="#0f172a"
                                        strokeWidth="1.5"
                                        className="hover:r-4 transition-all cursor-pointer"
                                      />
                                    );
                                  })}
                                  
                                  {/* Деления на горизонтальной оси (даты) */}
                                  {spikesStats.chart_data.map((item, idx) => {
                                    const x = paddingLeft + idx * stepX;
                                    return (
                                      <line
                                        key={idx}
                                        x1={x}
                                        y1={chartHeight + paddingTop}
                                        x2={x}
                                        y2={chartHeight + paddingTop + 6}
                                        stroke="#6b7280"
                                        strokeWidth="1.5"
                                      />
                                    );
                                  })}
                                </>
                              );
                            })()}
                          </svg>
                          
                          {/* Подписи дат под графиком - точно под делениями */}
                          <div className="absolute bottom-0 left-0 right-0" style={{ height: `${paddingBottom}px` }}>
                            {spikesStats.chart_data.map((item, idx) => {
                              // Вычисляем позицию в процентах от общей ширины (1000 в viewBox)
                              const chartWidth = 1000 - paddingLeft - paddingRight;
                              const stepX = dataPoints > 1 ? chartWidth / (dataPoints - 1) : 0;
                              const xPosition = paddingLeft + idx * stepX;
                              // Позиция в процентах от viewBox ширины (1000)
                              const leftPercent = (xPosition / 1000) * 100;
                              return (
                                <div
                                  key={idx}
                                  className="text-zinc-400 text-xs text-center absolute"
                                  style={{
                                    left: `${leftPercent}%`,
                                    transform: 'translateX(-50%)',
                                    whiteSpace: 'nowrap',
                                    bottom: '15px',
                                    fontSize: '11px'
                                  }}
                                >
                                  {new Date(item.date).toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' })}
                                </div>
                              );
                            })}
                          </div>
                          
                          {/* Подпись вертикальной оси - ближе к графику и правильно выровнена */}
                          <div 
                            className="absolute text-zinc-400 text-xs font-medium whitespace-nowrap" 
                            style={{ 
                              left: `${paddingLeft / 2}px`,
                              top: '50%',
                              transform: 'translate(-50%, -50%) rotate(-90deg)',
                              transformOrigin: 'center center',
                              fontSize: '12px'
                            }}
                          >
                            Количество детектов
                          </div>
                          
                          {/* Подпись горизонтальной оси */}
                          <div className="absolute bottom-0 left-1/2 transform translate-x-1/2 translate-y-full text-zinc-400 text-xs font-medium" style={{ marginBottom: '10px', fontSize: '12px' }}>
                            Дата
                          </div>
                        </div>
                      </div>
                    );
                  })()}
                  
                  {/* Распределение по биржам и рынкам */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-8">
                    <div className="glass-strong border border-zinc-800 rounded-xl p-6 card-hover gradient-border animate-fade-in">
                      <h2 className="text-xl font-semibold gradient-text mb-4">По биржам</h2>
                      <div className="space-y-2">
                        {Object.entries(spikesStats.by_exchange).map(([exchange, count]) => (
                          <div key={exchange} className="flex items-center justify-between smooth-transition hover:bg-zinc-800/30 p-2 rounded">
                            <span className="text-zinc-300 capitalize">{exchange}</span>
                            <span className="text-white font-semibold">{formatNumber(count)}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                    <div className="glass-strong border border-zinc-800 rounded-xl p-6 card-hover gradient-border animate-fade-in">
                      <h2 className="text-xl font-semibold gradient-text mb-4">По рынкам</h2>
                      <div className="space-y-2">
                        {Object.entries(spikesStats.by_market).map(([market, count]) => (
                          <div key={market} className="flex items-center justify-between smooth-transition hover:bg-zinc-800/30 p-2 rounded">
                            <span className="text-zinc-300 capitalize">{market === 'linear' ? 'Фьючерсы' : market === 'spot' ? 'Спот' : market}</span>
                            <span className="text-white font-semibold">{formatNumber(count)}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                  
                  {/* Топ символов */}
                  {spikesStats.top_symbols.length > 0 && (
                    <div className="glass-strong border border-zinc-800 rounded-xl p-6 mb-8 card-hover animate-fade-in">
                      <h2 className="text-xl font-semibold gradient-text mb-4">Топ-10 символов</h2>
                      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
                        {spikesStats.top_symbols.map((item) => (
                          <button
                            key={item.symbol}
                            onClick={() => setSelectedSymbol(item.symbol)}
                            className="text-center p-3 rounded-lg glass hover:bg-zinc-800/50 smooth-transition ripple hover-glow border border-transparent hover:border-emerald-500"
                          >
                            <div className="text-zinc-400 text-sm mb-1">{item.symbol}</div>
                            <div className="text-white font-bold">{formatNumber(item.count)}</div>
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                  
                  {/* Детали по выбранной монете */}
                  {selectedSymbol && (
                    <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6 mb-8">
                      <div className="flex items-center justify-between mb-4">
                        <h2 className="text-xl font-semibold text-white">
                          Детали по монете: {selectedSymbol}
                        </h2>
                        <button
                          onClick={() => setSelectedSymbol(null)}
                          className="text-zinc-400 hover:text-white transition-colors"
                        >
                          ✕
                        </button>
                      </div>
                      
                      {symbolSpikesLoading ? (
                        <div className="text-zinc-400 text-center py-8">Загрузка...</div>
                      ) : symbolSpikes.length > 0 ? (
                        <div className="overflow-x-auto">
                          <table className="w-full">
                            <thead className="bg-zinc-800/50">
                              <tr>
                                <th className="px-4 py-2 text-left text-xs font-semibold text-zinc-300">Дата и время</th>
                                <th className="px-4 py-2 text-left text-xs font-semibold text-zinc-300">Биржа</th>
                                <th className="px-4 py-2 text-left text-xs font-semibold text-zinc-300">Рынок</th>
                                <th className="px-4 py-2 text-left text-xs font-semibold text-zinc-300">Дельта %</th>
                                <th className="px-4 py-2 text-left text-xs font-semibold text-zinc-300">Объём USDT</th>
                                <th className="px-4 py-2 text-left text-xs font-semibold text-zinc-300">Тень %</th>
                              </tr>
                            </thead>
                            <tbody>
                              {symbolSpikes.map((spike: any, idx: number) => (
                                <tr key={idx} className="border-t border-zinc-800 hover:bg-zinc-800/30 transition-colors">
                                  <td className="px-4 py-3 text-zinc-300 text-sm">
                                    {new Date(spike.ts).toLocaleString('ru-RU', {
                                      year: 'numeric',
                                      month: '2-digit',
                                      day: '2-digit',
                                      hour: '2-digit',
                                      minute: '2-digit',
                                      second: '2-digit'
                                    })}
                                  </td>
                                  <td className="px-4 py-3 text-zinc-300 capitalize">{spike.exchange}</td>
                                  <td className="px-4 py-3 text-zinc-300 capitalize">
                                    {spike.market === 'linear' ? 'Фьючерсы' : spike.market}
                                  </td>
                                  <td className={`px-4 py-3 font-semibold ${spike.delta >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                    {spike.delta >= 0 ? '+' : ''}{spike.delta.toFixed(2)}%
                                  </td>
                                  <td className="px-4 py-3 text-zinc-300">${formatNumber(Math.round(spike.volume_usdt))}</td>
                                  <td className="px-4 py-3 text-zinc-300">{spike.wick_pct.toFixed(1)}%</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      ) : (
                        <div className="text-zinc-400 text-center py-8">Нет данных по этой монете</div>
                      )}
                    </div>
                  )}
                  
                  {/* Топ 10 стрел по дельте и объёму */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-8">
                    {/* Топ 10 по дельте */}
                    <div className="glass-strong border border-zinc-800 rounded-xl p-4 card-hover animate-fade-in">
                      <h2 className="text-lg font-semibold gradient-text mb-3">Топ 10 стрел по дельте</h2>
                      {spikesStats.top_by_delta && spikesStats.top_by_delta.length > 0 ? (
                        <div className="grid grid-cols-2 gap-2">
                          {spikesStats.top_by_delta.map((spike: any, idx: number) => (
                            <div key={idx} className="p-2 rounded-lg glass hover:bg-zinc-800/50 smooth-transition">
                              <div className="flex items-center justify-between mb-1">
                                <div className="text-zinc-400 text-xs font-medium">#{idx + 1}</div>
                                <div className={`font-semibold text-xs ${spike.delta >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                  {spike.delta >= 0 ? '+' : ''}{spike.delta.toFixed(2)}%
                                </div>
                              </div>
                              <div className="text-white font-medium text-sm mb-0.5 truncate">{spike.symbol}</div>
                              <div className="text-zinc-400 text-xs truncate mb-0.5">
                                {spike.exchange} • {spike.market === 'linear' ? 'Фьючерсы' : 'Спот'}
                              </div>
                              <div className="text-zinc-500 text-xs">
                                {new Date(spike.ts).toLocaleString('ru-RU', { 
                                  day: '2-digit', 
                                  month: '2-digit',
                                  hour: '2-digit',
                                  minute: '2-digit'
                                })}
                              </div>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <div className="text-zinc-500 text-center py-8 text-sm">Нет данных за выбранный период</div>
                      )}
                    </div>
                    
                    {/* Топ 10 по объёму */}
                    <div className="glass-strong border border-zinc-800 rounded-xl p-4 card-hover animate-fade-in">
                      <h2 className="text-lg font-semibold gradient-text mb-3">Топ 10 стрел по объёму</h2>
                      {spikesStats.top_by_volume && spikesStats.top_by_volume.length > 0 ? (
                        <div className="grid grid-cols-2 gap-2">
                          {spikesStats.top_by_volume.map((spike: any, idx: number) => (
                            <div key={idx} className="p-2 rounded-lg glass hover:bg-zinc-800/50 smooth-transition">
                              <div className="flex items-center justify-between mb-1">
                                <div className="text-zinc-400 text-xs font-medium">#{idx + 1}</div>
                                <div className="text-white font-semibold text-xs">
                                  ${formatNumber(Math.round(spike.volume_usdt))}
                                </div>
                              </div>
                              <div className="text-white font-medium text-sm mb-0.5 truncate">{spike.symbol}</div>
                              <div className="text-zinc-400 text-xs truncate mb-0.5">
                                {spike.exchange} • {spike.market === 'linear' ? 'Фьючерсы' : 'Спот'}
                              </div>
                              <div className="text-zinc-500 text-xs">
                                {new Date(spike.ts).toLocaleString('ru-RU', { 
                                  day: '2-digit', 
                                  month: '2-digit',
                                  hour: '2-digit',
                                  minute: '2-digit'
                                })}
                              </div>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <div className="text-zinc-500 text-center py-8 text-sm">Нет данных за выбранный период</div>
                      )}
                    </div>
                  </div>
                  
                  {/* Таблица детектов */}
                  {spikesStats.spikes.length > 0 && (
                    <div className="bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden">
                      <div className="p-6 border-b border-zinc-800">
                        <h2 className="text-xl font-semibold text-white">Последние детекты</h2>
                      </div>
                      <div className="overflow-x-auto">
                        <table className="w-full">
                          <thead className="bg-zinc-800/50">
                            <tr>
                              <th className="px-6 py-3 text-left text-xs font-semibold text-zinc-300">Время</th>
                              <th className="px-6 py-3 text-left text-xs font-semibold text-zinc-300">Биржа</th>
                              <th className="px-6 py-3 text-left text-xs font-semibold text-zinc-300">Рынок</th>
                              <th className="px-6 py-3 text-left text-xs font-semibold text-zinc-300">Символ</th>
                              <th className="px-6 py-3 text-left text-xs font-semibold text-zinc-300">Дельта %</th>
                              <th className="px-6 py-3 text-left text-xs font-semibold text-zinc-300">Объём USDT</th>
                              <th className="px-6 py-3 text-left text-xs font-semibold text-zinc-300">Тень %</th>
                            </tr>
                          </thead>
                          <tbody>
                            {spikesStats.spikes.map((spike: any, idx: number) => (
                              <tr key={idx} className="border-t border-zinc-800 hover:bg-zinc-800/30 transition-colors">
                                <td className="px-6 py-4 text-zinc-300 text-sm">
                                  {new Date(spike.ts).toLocaleString('ru-RU')}
                                </td>
                                <td className="px-6 py-4 text-zinc-300 capitalize">{spike.exchange}</td>
                                <td className="px-6 py-4 text-zinc-300 capitalize">{spike.market === 'linear' ? 'Фьючерсы' : spike.market}</td>
                                <td className="px-6 py-4 text-white font-medium">{spike.symbol}</td>
                                <td className={`px-6 py-4 font-semibold ${spike.delta >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                  {spike.delta >= 0 ? '+' : ''}{spike.delta.toFixed(2)}%
                                </td>
                                <td className="px-6 py-4 text-zinc-300">${formatNumber(Math.round(spike.volume_usdt))}</td>
                                <td className="px-6 py-4 text-zinc-300">{spike.wick_pct.toFixed(1)}%</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}
                </>
              ) : (
                <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6">
                  <p className="text-zinc-400">Нет данных для отображения. Убедитесь, что у вас настроены фильтры детектирования.</p>
                </div>
              )}
            </div>
          )}

          {activeTab === "settings" && (
            <div className="mb-6 md:mb-8">
              <h1 className="text-2xl md:text-3xl font-bold text-white mb-2">Настройки</h1>
              <p className="text-zinc-400 mb-8">
                Управление профилями, фильтрами и интеграциями
              </p>
              
              {/* Уведомление по центру экрана */}
              {saveMessage && (
                <div className="fixed top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2 z-50">
                  <div className={`p-6 rounded-xl shadow-2xl max-w-md ${
                    saveMessage.type === "success" 
                      ? "bg-green-500/95 text-white border-2 border-green-400" 
                      : "bg-red-500/95 text-white border-2 border-red-400"
                  }`}>
                    <div className="flex items-start gap-3">
                      {saveMessage.type === "success" ? (
                        <svg className="w-6 h-6 mt-0.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                      ) : (
                        <svg className="w-6 h-6 mt-0.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                      )}
                      <div className="flex-1">
                        <p className="font-semibold text-lg">{saveMessage.type === "success" ? "Успешно сохранено" : "Ошибка"}</p>
                        <p className="text-sm mt-2 opacity-90">{saveMessage.text}</p>
                      </div>
                    </div>
                  </div>
                </div>
              )}
              
              {/* Интеграция с Telegram */}
              <div className={`mb-8 bg-zinc-900 border border-zinc-800 rounded-xl transition-all duration-300 ${
                isTelegramConfigured && !isEditingTelegram ? "p-4" : "p-6"
              }`}>
                <div className="flex items-center gap-2 mb-1">
                  <h2 className="text-xl font-bold text-white">Интеграция с Telegram</h2>
                  <svg className="w-5 h-5 text-zinc-400 cursor-help" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <title>Настройте уведомления через Telegram бота. После настройки вы будете получать сообщения о найденных стрелах в реальном времени.</title>
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                </div>
                
                {isTelegramConfigured && !isEditingTelegram ? (
                  // Компактный вид после сохранения
                  <div className="space-y-3">
                    <p className="text-sm text-zinc-400">
                      Telegram настроен. Вы будете получать уведомления о найденных стрелах.
                    </p>
                    
                    <div className="flex gap-3">
                      <button
                        onClick={async () => {
                          if (!userLogin || !telegramBotToken || !telegramChatId) {
                            setSaveMessage({ type: "error", text: "Заполните Chat ID и Bot Token перед отправкой теста" });
                            return;
                          }
                          
                          setTesting(true);
                          setSaveMessage(null);
                          try {
                            const res = await fetch(`/api/users/${userLogin}/test`, {
                              method: "POST"
                            });
                            
                            if (res.ok) {
                              setSaveMessage({ type: "success", text: "Тестовое сообщение успешно отправлено! Проверьте Telegram." });
                            } else {
                              const error = await res.json();
                              setSaveMessage({ type: "error", text: error.detail || "Ошибка отправки тестового сообщения" });
                            }
                          } catch (err) {
                            setSaveMessage({ type: "error", text: "Ошибка при отправке тестового сообщения" });
                            console.error(err);
                          } finally {
                            setTesting(false);
                          }
                        }}
                        disabled={testing || !telegramBotToken || !telegramChatId}
                        className="flex-1 px-4 py-2 glass hover:bg-zinc-700/50 text-white font-medium rounded-lg smooth-transition ripple hover-glow disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                      >
                        {testing ? (
                          "Отправка..."
                        ) : (
                          <>
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                            </svg>
                            Отправить тест
                          </>
                        )}
                      </button>
                      
                      <button
                        onClick={() => setIsEditingTelegram(true)}
                        className="flex-1 px-4 py-2 bg-gradient-to-r from-emerald-500 to-emerald-600 hover:from-emerald-600 hover:to-emerald-700 text-white font-medium rounded-lg smooth-transition ripple hover-glow shadow-emerald flex items-center justify-center gap-2"
                      >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                        </svg>
                        Изменить
                      </button>
                    </div>
                  </div>
                ) : (
                  // Полная форма для редактирования
                  <>
                    <p className="text-sm text-zinc-400 mb-6">Настройте уведомления через Telegram бота. Укажите Chat ID и Bot Token для получения сообщений о найденных стрелах.</p>
                    
                    <div className="space-y-4">
                      <div>
                        <label className="block text-sm font-medium text-zinc-300 mb-2">
                          Chat ID
                        </label>
                        <input
                          type="text"
                          value={telegramChatId}
                          onChange={(e) => {
                            const value = e.target.value;
                            setTelegramChatId(value);
                            setTelegramChatIdError(validateChatId(value));
                          }}
                          onBlur={(e) => {
                            setTelegramChatIdError(validateChatId(e.target.value));
                          }}
                          placeholder="123456789"
                          className={`w-full px-4 py-2 bg-zinc-800 border rounded-lg text-white placeholder-zinc-500 focus:outline-none focus:ring-2 focus:border-transparent ${
                            telegramChatIdError 
                              ? "border-red-500 focus:ring-red-500" 
                              : "border-zinc-700 focus:ring-emerald-500"
                          }`}
                        />
                        {telegramChatIdError ? (
                          <div className="mt-1">
                            <p className="text-xs text-red-400">{telegramChatIdError}</p>
                            <ChatIdHelp variant="compact" />
                          </div>
                        ) : (
                          <ChatIdHelp />
                        )}
                      </div>
                      
                      <div>
                        <label className="block text-sm font-medium text-zinc-300 mb-2">
                          Bot Token
                        </label>
                        <input
                          type="password"
                          value={telegramBotToken}
                          onChange={(e) => {
                            const value = e.target.value;
                            setTelegramBotToken(value);
                            setTelegramBotTokenError(validateBotToken(value));
                          }}
                          onBlur={(e) => {
                            setTelegramBotTokenError(validateBotToken(e.target.value));
                          }}
                          placeholder="1234567890:ABCdefGHIjkIMNOpqrsTUVwxyz"
                          className={`w-full px-4 py-2 bg-zinc-800 border rounded-lg text-white placeholder-zinc-500 focus:outline-none focus:ring-2 focus:border-transparent ${
                            telegramBotTokenError 
                              ? "border-red-500 focus:ring-red-500" 
                              : "border-zinc-700 focus:ring-emerald-500"
                          }`}
                        />
                        {telegramBotTokenError ? (
                          <p className="mt-1 text-xs text-red-400">{telegramBotTokenError}</p>
                        ) : (
                          <div className="mt-1">
                            <p className="text-xs text-zinc-500 mb-2">
                              Получите Bot Token через @BotFather в Telegram
                            </p>
                            <ChatIdHelp showBotTokenWarning={true} />
                          </div>
                        )}
                      </div>
                      
                      <div className="flex gap-3 pt-2">
                        <button
                          onClick={async () => {
                            if (!userLogin) return;
                            
                            // Валидация перед сохранением
                            const chatIdError = validateChatId(telegramChatId);
                            const botTokenError = validateBotToken(telegramBotToken);
                            
                            setTelegramChatIdError(chatIdError);
                            setTelegramBotTokenError(botTokenError);
                            
                            if (chatIdError || botTokenError) {
                              setSaveMessage({ 
                                type: "error", 
                                text: "Исправьте ошибки в полях перед сохранением" 
                              });
                              return;
                            }
                            
                            // Если оба поля заполнены, должны быть валидными
                            if (telegramChatId && telegramBotToken && (!telegramChatId.trim() || !telegramBotToken.trim())) {
                              setSaveMessage({ 
                                type: "error", 
                                text: "Заполните все поля" 
                              });
                              return;
                            }
                            
                            setSaving(true);
                            setSaveMessage(null);
                            await saveAllSettings();
                            setSaving(false);
                          }}
                          disabled={saving || !!telegramChatIdError || !!telegramBotTokenError}
                          className="flex-1 px-4 py-2 bg-gradient-to-r from-emerald-500 to-emerald-600 hover:from-emerald-600 hover:to-emerald-700 text-white font-medium rounded-lg smooth-transition ripple hover-glow shadow-emerald disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                          {saving ? "Сохранение..." : "Сохранить"}
                        </button>
                        
                        <button
                          onClick={async () => {
                            if (!userLogin || !telegramBotToken || !telegramChatId) {
                              setSaveMessage({ type: "error", text: "Заполните Chat ID и Bot Token перед отправкой теста" });
                              return;
                            }
                            
                            // Валидация перед отправкой
                            const chatIdError = validateChatId(telegramChatId);
                            const botTokenError = validateBotToken(telegramBotToken);
                            
                            setTelegramChatIdError(chatIdError);
                            setTelegramBotTokenError(botTokenError);
                            
                            if (chatIdError || botTokenError) {
                              setSaveMessage({ 
                                type: "error", 
                                text: "Исправьте ошибки в полях перед отправкой теста" 
                              });
                              return;
                            }
                            
                            // Сначала сохраняем настройки
                            setSaving(true);
                            await saveAllSettings();
                            setSaving(false);
                            
                            // Затем отправляем тестовое сообщение
                            setTesting(true);
                            setSaveMessage(null);
                            try {
                              const res = await fetch(`/api/users/${userLogin}/test`, {
                                method: "POST"
                              });
                              
                              if (res.ok) {
                                setSaveMessage({ type: "success", text: "Тестовое сообщение успешно отправлено! Проверьте Telegram." });
                              } else {
                                const error = await res.json();
                                setSaveMessage({ type: "error", text: error.detail || "Ошибка отправки тестового сообщения" });
                              }
                            } catch (err) {
                              setSaveMessage({ type: "error", text: "Ошибка при отправке тестового сообщения" });
                              console.error(err);
                            } finally {
                              setTesting(false);
                            }
                          }}
                          disabled={testing || saving || !telegramBotToken || !telegramChatId || !!telegramChatIdError || !!telegramBotTokenError}
                          className="flex-1 px-4 py-2 glass hover:bg-zinc-700/50 text-white font-medium rounded-lg smooth-transition ripple hover-glow disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                        >
                          {testing ? (
                            "Отправка..."
                          ) : (
                            <>
                              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                              </svg>
                              Отправить тест
                            </>
                          )}
                        </button>
                      </div>
                    </div>
                  </>
                )}
              </div>
              {/* Формат отправки детекта */}
              <div className="mb-8 bg-zinc-900 border border-zinc-800 rounded-xl p-6">
                <div className="flex items-center justify-between mb-1">
                  <div className="flex items-center gap-2">
                    <h2 className="text-xl font-bold text-white">Формат отправки детекта</h2>
                    <svg className="w-5 h-5 text-zinc-400 cursor-help" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <title>Настройте формат сообщений, которые будут отправляться в Telegram при обнаружении стрелы. Используйте вставки для добавления данных о детекте (дельта, объём, биржа и т.д.).</title>
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                  </div>
                  {!isMessageFormatExpanded && (
                    <button
                      onClick={() => setIsMessageFormatExpanded(true)}
                      className="px-4 py-2 bg-gradient-to-r from-emerald-500 to-emerald-600 hover:from-emerald-600 hover:to-emerald-700 text-white text-sm font-medium rounded-lg smooth-transition ripple hover-glow shadow-emerald"
                    >
                      Изменить
                    </button>
                  )}
                </div>
                
                {isMessageFormatExpanded && (
                  <>
                <p className="text-sm text-zinc-400 mb-6">
                  Настройте формат сообщений, которые будут отправляться в Telegram при обнаружении стрелы. Используйте вставки ниже для добавления данных о детекте (дельта, объём, биржа и т.д.).
                </p>
                
                {/* Список доступных вставок */}
                <div className="mb-4">
                  <h3 className="text-sm font-medium text-zinc-300 mb-3">Доступные вставки:</h3>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                    {[
                      { friendly: "[[Дельта стрелы]]", label: "Дельта стрелы", desc: "Например: 5.23%" },
                      { friendly: "[[Направление]]", label: "Направление", desc: "Эмодзи стрелки вверх ⬆️ или вниз ⬇️", descHtml: <>Эмодзи стрелки вверх <span style={{color: '#10b981'}}>⬆️</span> или вниз <span style={{color: '#ef4444'}}>⬇️</span></> },
                      { friendly: "[[Биржа и тип рынка]]", label: "Биржа и тип рынка", desc: "Название биржи и тип рынка (например: BINANCE | SPOT)" },
                      { friendly: "[[Торговая пара]]", label: "Торговая пара", desc: "Символ пары (например: BTCUSDT)" },
                      { friendly: "[[Объём стрелы]]", label: "Объём стрелы", desc: "Объём в USDT" },
                      { friendly: "[[Тень свечи]]", label: "Тень свечи", desc: "Процент тени свечи (например: 45.2%)" },
                      { friendly: "[[Время детекта]]", label: "Время детекта", desc: "Дата и время (YYYY-MM-DD HH:MM:SS)" },
                    ].map((placeholder) => (
                      <button
                        key={placeholder.friendly}
                        onClick={() => {
                          const editor = document.getElementById("messageTemplate") as HTMLElement;
                          if (editor) {
                            const selection = window.getSelection();
                            if (selection && selection.rangeCount > 0) {
                              const range = selection.getRangeAt(0);
                              range.deleteContents();
                              
                              // Создаем красивый визуальный блок для вставки
                              const block = document.createElement('span');
                              block.className = 'inline-flex items-center gap-1.5 px-2 py-1 mx-0.5 bg-emerald-500/20 border border-emerald-500/50 rounded text-emerald-300 text-xs font-medium cursor-default';
                              block.setAttribute('data-placeholder-key', placeholder.friendly);
                              block.setAttribute('contenteditable', 'false');
                              block.innerHTML = `
                                <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 8h10M7 12h4m1 8l-4-4H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-3l-4 4z"></path>
                                </svg>
                                <span>${placeholder.label}</span>
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
                            }
                          }
                        }}
                        className="text-left px-3 py-2 bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 hover:border-emerald-500/50 rounded-lg transition-colors group"
                        title={placeholder.desc}
                      >
                        <div className="text-sm font-medium text-white group-hover:text-emerald-300 mb-0.5">
                          {placeholder.label}
                        </div>
                        <div className="text-xs text-zinc-500 group-hover:text-zinc-400">
                          {placeholder.descHtml || placeholder.desc}
                        </div>
                      </button>
                    ))}
                  </div>
                </div>
                
                {/* Редактор шаблона */}
                <div className="mb-4">
                  <div className="flex items-center justify-between mb-2">
                    <label className="block text-sm font-medium text-zinc-300">
                      Шаблон сообщения
                      <span className="text-xs text-zinc-500 ml-2">(можно вставлять emoji из Telegram через Ctrl+V или использовать кнопку Emoji)</span>
                    </label>
                    <button
                      ref={emojiButtonRef}
                      type="button"
                      onClick={(e) => {
                        const button = e.currentTarget;
                        const rect = button.getBoundingClientRect();
                        const pickerWidth = 350;
                        const pickerHeight = 400;
                        const padding = 8;
                        
                        // Вычисляем позицию с учетом границ экрана
                        let x = rect.left;
                        let y = rect.bottom + padding;
                        
                        // Если picker не помещается справа, сдвигаем влево
                        if (x + pickerWidth > window.innerWidth) {
                          x = window.innerWidth - pickerWidth - padding;
                        }
                        
                        // Если picker не помещается снизу, показываем сверху
                        if (y + pickerHeight > window.innerHeight) {
                          y = rect.top - pickerHeight - padding;
                        }
                        
                        // Минимальная позиция слева
                        if (x < padding) {
                          x = padding;
                        }
                        
                        // Минимальная позиция сверху
                        if (y < padding) {
                          y = padding;
                        }
                        
                        setShowEmojiPicker({ 
                          main: !showEmojiPicker.main, 
                          conditional: null,
                          position: { x, y }
                        });
                      }}
                      className="px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 hover:border-emerald-500/50 rounded-lg transition-colors text-sm font-medium text-zinc-300 hover:text-white flex items-center gap-2"
                      title="Добавить emoji"
                    >
                      <span className="text-lg">😀</span>
                      <span>Emoji</span>
                    </button>
                  </div>
                  <div className="relative">
                    <div
                      id="messageTemplate"
                      contentEditable
                      suppressContentEditableWarning
                      onInput={(e) => {
                        const editor = e.currentTarget;
                        const content = editor.innerHTML;
                        // Извлекаем технические ключи из визуальных блоков
                        const tempDiv = document.createElement('div');
                        tempDiv.innerHTML = content;
                        const blocks = tempDiv.querySelectorAll('[data-placeholder-key]');
                        let textContent = content;
                        blocks.forEach((block) => {
                          const key = block.getAttribute('data-placeholder-key');
                          if (key) {
                            // Экранируем HTML для замены
                            const blockHTML = block.outerHTML.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
                            textContent = textContent.replace(new RegExp(blockHTML, 'g'), key);
                          }
                        });
                        // Заменяем <br> обратно на переносы строк
                        textContent = textContent.replace(/<br\s*\/?>/gi, '\n');
                        // Удаляем HTML теги форматирования, но сохраняем структуру
                        const plainText = textContent.replace(/<[^>]*>/g, '');
                        // Обновляем состояние
                        isUserEditingRef.current = true;
                        setMessageTemplate(textContent);
                        // Пересоздаем HTML с визуальными блоками
                        setTimeout(() => {
                          const html = convertTemplateToHTML(convertToFriendlyNames(textContent));
                          if (editor.innerHTML !== html) {
                            // Сохраняем позицию курсора перед обновлением
                            const selection = window.getSelection();
                            let savedRange: Range | null = null;
                            if (selection && selection.rangeCount > 0) {
                              savedRange = selection.getRangeAt(0).cloneRange();
                            }
                            
                            editor.innerHTML = html;
                            
                            // Восстанавливаем позицию курсора
                            if (savedRange && selection) {
                              try {
                                selection.removeAllRanges();
                                selection.addRange(savedRange);
                              } catch (e) {
                                // Если не удалось, пробуем восстановить приблизительно
                                try {
                                  const textNodes = getTextNodes(editor);
                                  if (textNodes.length > 0) {
                                    const startOffset = savedRange.startOffset;
                                    const targetNode = savedRange.startContainer.nodeType === Node.TEXT_NODE 
                                      ? savedRange.startContainer 
                                      : textNodes[0];
                                    const maxOffset = targetNode.textContent?.length || 0;
                                    const newRange = document.createRange();
                                    newRange.setStart(targetNode, Math.min(startOffset, maxOffset));
                                    newRange.collapse(true);
                                    selection.removeAllRanges();
                                    selection.addRange(newRange);
                                  }
                                } catch (e2) {
                                  // Игнорируем ошибки
                                }
                              }
                            }
                          }
                          
                          // Снимаем флаг редактирования после обновления
                          setTimeout(() => {
                            isUserEditingRef.current = false;
                          }, 50);
                        }, 0);
                      }}
                      onContextMenu={handleContextMenu}
                      onKeyDown={handleKeyDown}
                      onClick={() => setContextMenu(null)}
                      className="w-full min-h-64 px-4 py-3 bg-zinc-800 border border-zinc-700 rounded-lg text-white font-mono text-sm focus:outline-none focus:ring-2 focus:border-transparent focus:ring-emerald-500 resize-none overflow-y-auto template-editor"
                      style={{ whiteSpace: 'pre-wrap' }}
                      onPaste={(e) => {
                        // Разрешаем вставку emoji из буфера обмена
                        // Это позволяет вставлять emoji, скопированные из Telegram
                        e.preventDefault();
                        const text = e.clipboardData.getData('text/plain');
                        const selection = window.getSelection();
                        if (selection && selection.rangeCount > 0) {
                          const range = selection.getRangeAt(0);
                          range.deleteContents();
                          const textNode = document.createTextNode(text);
                          range.insertNode(textNode);
                          range.setStartAfter(textNode);
                          range.collapse(true);
                          selection.removeAllRanges();
                          selection.addRange(range);
                          // Триггерим событие input
                          const inputEvent = new Event('input', { bubbles: true });
                          e.currentTarget.dispatchEvent(inputEvent);
                        }
                      }}
                    />
                    
                    {/* Emoji Picker для основного редактора */}
                    {showEmojiPicker.main && showEmojiPicker.position && (
                      <>
                        <div
                          className="fixed inset-0 z-40"
                          onClick={() => setShowEmojiPicker({ main: false, conditional: null })}
                        />
                        <div 
                          className="fixed z-50"
                          style={{
                            left: `${showEmojiPicker.position.x}px`,
                            top: `${showEmojiPicker.position.y}px`
                          }}
                        >
                          <EmojiPicker
                            onEmojiClick={(emojiData) => insertEmoji(emojiData, "messageTemplate", false)}
                            theme={"dark" as any}
                            width={350}
                            height={400}
                            previewConfig={{
                              showPreview: false
                            }}
                          />
                        </div>
                      </>
                    )}
                    
                    {/* Контекстное меню форматирования */}
                    {contextMenu?.visible && (
                      <>
                        <div
                          className="fixed inset-0 z-40"
                          onClick={() => setContextMenu(null)}
                        />
                        <div
                          className="absolute z-50 bg-zinc-900 border border-zinc-700 rounded-lg shadow-2xl overflow-hidden"
                          style={{
                            left: `${contextMenu.x}px`,
                            top: `${contextMenu.y}px`,
                            minWidth: '200px',
                          }}
                        >
                          <div className="py-1">
                            <button
                              onClick={formatBold}
                              className="w-full text-left px-4 py-2 text-sm text-zinc-300 hover:bg-zinc-800 hover:text-white flex items-center justify-between"
                            >
                              <span>Жирный</span>
                              <span className="text-xs text-zinc-500 ml-4">Ctrl+B</span>
                            </button>
                            <button
                              onClick={formatItalic}
                              className="w-full text-left px-4 py-2 text-sm text-zinc-300 hover:bg-zinc-800 hover:text-white flex items-center justify-between"
                            >
                              <span>Курсив</span>
                              <span className="text-xs text-zinc-500 ml-4">Ctrl+I</span>
                            </button>
                            <button
                              onClick={formatUnderline}
                              className="w-full text-left px-4 py-2 text-sm text-zinc-300 hover:bg-zinc-800 hover:text-white flex items-center justify-between"
                            >
                              <span>Подчёркнутый</span>
                              <span className="text-xs text-zinc-500 ml-4">Ctrl+U</span>
                            </button>
                            <button
                              onClick={formatStrikethrough}
                              className="w-full text-left px-4 py-2 text-sm text-zinc-300 hover:bg-zinc-800 hover:text-white flex items-center justify-between"
                            >
                              <span>Зачёркнутый</span>
                              <span className="text-xs text-zinc-500 ml-4">Ctrl+Shift+X</span>
                            </button>
                            <button
                              onClick={formatBlockquote}
                              className="w-full text-left px-4 py-2 text-sm text-zinc-300 hover:bg-zinc-800 hover:text-white flex items-center justify-between"
                            >
                              <span>Цитата</span>
                              <span className="text-xs text-zinc-500 ml-4">Ctrl+Shift+.</span>
                            </button>
                            <button
                              onClick={formatCode}
                              className="w-full text-left px-4 py-2 text-sm text-zinc-300 hover:bg-zinc-800 hover:text-white flex items-center justify-between"
                            >
                              <span>Моноширинный</span>
                              <span className="text-xs text-zinc-500 ml-4">Ctrl+Shift+M</span>
                            </button>
                            <button
                              onClick={formatSpoiler}
                              className="w-full text-left px-4 py-2 text-sm text-zinc-300 hover:bg-zinc-800 hover:text-white flex items-center justify-between"
                            >
                              <span>Скрытый</span>
                              <span className="text-xs text-zinc-500 ml-4">Ctrl+Shift+P</span>
                            </button>
                          </div>
                        </div>
                      </>
                    )}
                  </div>
                  <div className="mt-2 space-y-1">
                    <p className="text-xs text-zinc-500">
                      Используйте HTML теги для форматирования (например, &lt;b&gt; для жирного текста)
                    </p>
                    <p className="text-xs text-zinc-500">
                      💡 Кликните на кнопку выше, чтобы вставить нужную вставку в шаблон. Выделите текст и нажмите правой кнопкой для форматирования
                    </p>
                  </div>
                </div>
                
                {/* Кнопки сохранения и скрытия */}
                <div className="flex gap-3 mt-4">
                  <button
                    onClick={async () => {
                      await saveAllSettings();
                    }}
                    className="px-4 py-2 bg-gradient-to-r from-emerald-500 to-emerald-600 hover:from-emerald-600 hover:to-emerald-700 text-white font-medium rounded-lg smooth-transition ripple hover-glow shadow-emerald"
                  >
                    Сохранить формат сообщения
                  </button>
                  <button
                    onClick={() => {
                      setIsMessageFormatExpanded(false);
                    }}
                    className="px-4 py-2 bg-zinc-700 hover:bg-zinc-600 text-white font-medium rounded-lg smooth-transition"
                  >
                    Скрыть
                  </button>
                </div>
                  </>
                )}
              </div>
              
              {/* Условные шаблоны сообщений */}
              <div className="mb-8 bg-zinc-900 border border-zinc-800 rounded-xl p-6">
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-2">
                    <h2 className="text-xl font-bold text-white">Условные форматы сообщений</h2>
                    <svg className="w-5 h-5 text-zinc-400 cursor-help" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <title>Создайте дополнительные шаблоны сообщений, которые будут использоваться при выполнении определённых условий (например, большой объём или дельта). Все подходящие шаблоны будут отправлены одновременно.</title>
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                  </div>
                  <button
                    onClick={() => setIsConditionalTemplatesExpanded(!isConditionalTemplatesExpanded)}
                    className="px-4 py-2 bg-zinc-700 hover:bg-zinc-600 text-white text-sm font-medium rounded-lg smooth-transition"
                  >
                    {isConditionalTemplatesExpanded ? "Скрыть" : "Показать"}
                  </button>
                </div>
                <p className="text-sm text-zinc-400 mb-4">
                  Создайте дополнительные шаблоны сообщений, которые будут использоваться при выполнении определённых условий (объём, дельта, серия стрел). 
                  Можно задать несколько условий одновременно (все условия должны выполняться). Все подходящие шаблоны будут отправлены одновременно при обнаружении стрелы.
                </p>
                
                {isConditionalTemplatesExpanded && (
                  <>
                    <div className="space-y-4 mb-4">
                      {conditionalTemplates.map((template, index) => {
                        const isEnabled = template.enabled !== false; // По умолчанию true
                        const templateDescription = template.description || generateTemplateDescription(template);
                        const templateName = template.name || `Шаблон #${index + 1}`;
                        
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
                                    setConditionalTemplates(newTemplates);
                                  }}
                                  placeholder={`Шаблон #${index + 1}`}
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
                                        setConditionalTemplates(newTemplates);
                                      }}
                                      className="w-4 h-4 text-emerald-600 bg-zinc-700 border-zinc-600 rounded focus:ring-emerald-500 focus:ring-2"
                                    />
                                    <span className="text-xs text-zinc-300">
                                      {isEnabled ? "Включен" : "Выключен"}
                                    </span>
                                  </label>
                                </div>
                              </div>
                              <p className="text-xs text-zinc-400 italic">
                                {templateDescription}
                              </p>
                            </div>
                            <button
                              onClick={() => {
                                setConditionalTemplates(conditionalTemplates.filter((_, i) => i !== index));
                              }}
                              className="ml-3 px-2 py-1 bg-red-600 hover:bg-red-700 text-white text-xs font-medium rounded transition-colors"
                            >
                              Удалить
                            </button>
                          </div>
                          
                          {/* Список условий для этого шаблона */}
                          <div className="mb-3">
                            <div className="flex items-center justify-between mb-2">
                              <label className="block text-xs font-medium text-zinc-300">Условия (все должны выполняться):</label>
                              <button
                                onClick={() => {
                                  const newTemplates = [...conditionalTemplates];
                                  newTemplates[index].conditions.push({
                                    type: "volume",
                                    value: 0,
                                  });
                                  setConditionalTemplates(newTemplates);
                                }}
                                className="px-2 py-1 bg-zinc-700 hover:bg-zinc-600 text-white text-xs font-medium rounded transition-colors"
                              >
                                + Добавить условие
                              </button>
                            </div>
                            
                            <div className="space-y-2">
                              {template.conditions.map((condition, condIndex) => (
                                <div key={condIndex} className="bg-zinc-900/50 border border-zinc-700/50 rounded-lg p-3">
                                  <div className="flex gap-2 items-end mb-2">
                                    <div className="flex-1">
                                      <label className="block text-xs text-zinc-400 mb-1">Параметр</label>
                                      <select
                                        value={condition.type}
                                        onChange={(e) => {
                                          const newTemplates = [...conditionalTemplates];
                                          const newType = e.target.value as "volume" | "delta" | "series" | "symbol" | "wick_pct" | "exchange" | "market" | "direction";
                                          newTemplates[index].conditions[condIndex].type = newType;
                                          // Очищаем значения при смене типа
                                          if (newType === "series") {
                                            newTemplates[index].conditions[condIndex].value = undefined;
                                            newTemplates[index].conditions[condIndex].valueMin = undefined;
                                            newTemplates[index].conditions[condIndex].valueMax = undefined;
                                            newTemplates[index].conditions[condIndex].symbol = undefined;
                                            newTemplates[index].conditions[condIndex].exchange = undefined;
                                            newTemplates[index].conditions[condIndex].market = undefined;
                                            newTemplates[index].conditions[condIndex].direction = undefined;
                                            newTemplates[index].conditions[condIndex].count = 2;
                                            newTemplates[index].conditions[condIndex].timeWindowSeconds = 300;
                                          } else if (newType === "delta" || newType === "wick_pct") {
                                            // Для дельты и тени используем диапазон
                                            newTemplates[index].conditions[condIndex].count = undefined;
                                            newTemplates[index].conditions[condIndex].timeWindowSeconds = undefined;
                                            newTemplates[index].conditions[condIndex].symbol = undefined;
                                            newTemplates[index].conditions[condIndex].exchange = undefined;
                                            newTemplates[index].conditions[condIndex].market = undefined;
                                            newTemplates[index].conditions[condIndex].direction = undefined;
                                            // Мигрируем старое значение value в valueMin, если оно есть
                                            if (newTemplates[index].conditions[condIndex].value !== undefined) {
                                              newTemplates[index].conditions[condIndex].valueMin = newTemplates[index].conditions[condIndex].value;
                                              delete newTemplates[index].conditions[condIndex].value;
                                            } else {
                                              newTemplates[index].conditions[condIndex].valueMin = 0;
                                            }
                                            newTemplates[index].conditions[condIndex].valueMax = null; // null = бесконечность
                                          } else if (newType === "symbol") {
                                            // Для символа - очищаем все числовые поля
                                            newTemplates[index].conditions[condIndex].value = undefined;
                                            newTemplates[index].conditions[condIndex].valueMin = undefined;
                                            newTemplates[index].conditions[condIndex].valueMax = undefined;
                                            newTemplates[index].conditions[condIndex].count = undefined;
                                            newTemplates[index].conditions[condIndex].timeWindowSeconds = undefined;
                                            newTemplates[index].conditions[condIndex].exchange = undefined;
                                            newTemplates[index].conditions[condIndex].market = undefined;
                                            newTemplates[index].conditions[condIndex].direction = undefined;
                                            newTemplates[index].conditions[condIndex].symbol = "";
                                          } else if (newType === "exchange") {
                                            newTemplates[index].conditions[condIndex].value = undefined;
                                            newTemplates[index].conditions[condIndex].valueMin = undefined;
                                            newTemplates[index].conditions[condIndex].valueMax = undefined;
                                            newTemplates[index].conditions[condIndex].count = undefined;
                                            newTemplates[index].conditions[condIndex].timeWindowSeconds = undefined;
                                            newTemplates[index].conditions[condIndex].symbol = undefined;
                                            newTemplates[index].conditions[condIndex].market = undefined;
                                            newTemplates[index].conditions[condIndex].direction = undefined;
                                            newTemplates[index].conditions[condIndex].exchange = "binance";
                                          } else if (newType === "market") {
                                            newTemplates[index].conditions[condIndex].value = undefined;
                                            newTemplates[index].conditions[condIndex].valueMin = undefined;
                                            newTemplates[index].conditions[condIndex].valueMax = undefined;
                                            newTemplates[index].conditions[condIndex].count = undefined;
                                            newTemplates[index].conditions[condIndex].timeWindowSeconds = undefined;
                                            newTemplates[index].conditions[condIndex].symbol = undefined;
                                            newTemplates[index].conditions[condIndex].exchange = undefined;
                                            newTemplates[index].conditions[condIndex].direction = undefined;
                                            newTemplates[index].conditions[condIndex].market = "spot";
                                          } else if (newType === "direction") {
                                            newTemplates[index].conditions[condIndex].value = undefined;
                                            newTemplates[index].conditions[condIndex].valueMin = undefined;
                                            newTemplates[index].conditions[condIndex].valueMax = undefined;
                                            newTemplates[index].conditions[condIndex].count = undefined;
                                            newTemplates[index].conditions[condIndex].timeWindowSeconds = undefined;
                                            newTemplates[index].conditions[condIndex].symbol = undefined;
                                            newTemplates[index].conditions[condIndex].exchange = undefined;
                                            newTemplates[index].conditions[condIndex].market = undefined;
                                            newTemplates[index].conditions[condIndex].direction = "up";
                                          } else {
                                            // Для объёма - одно значение
                                            newTemplates[index].conditions[condIndex].count = undefined;
                                            newTemplates[index].conditions[condIndex].timeWindowSeconds = undefined;
                                            newTemplates[index].conditions[condIndex].valueMin = undefined;
                                            newTemplates[index].conditions[condIndex].valueMax = undefined;
                                            newTemplates[index].conditions[condIndex].symbol = undefined;
                                            newTemplates[index].conditions[condIndex].exchange = undefined;
                                            newTemplates[index].conditions[condIndex].market = undefined;
                                            newTemplates[index].conditions[condIndex].direction = undefined;
                                            newTemplates[index].conditions[condIndex].value = 0;
                                          }
                                          // Обновляем описание шаблона
                                          const updatedDescription = generateTemplateDescription(newTemplates[index]);
                                          newTemplates[index].description = updatedDescription;
                                          setConditionalTemplates(newTemplates);
                                        }}
                                        className="w-full px-3 py-2 bg-zinc-700 border border-zinc-600 rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                                      >
                                        <option value="volume">Объём (USDT)</option>
                                        <option value="delta">Дельта (%)</option>
                                        <option value="wick_pct">Тень свечи (%)</option>
                                        <option value="series">Серия стрел</option>
                                        <option value="symbol">Символ (монета)</option>
                                        <option value="exchange">Биржа</option>
                                        <option value="market">Тип рынка</option>
                                        <option value="direction">Направление стрелы</option>
                                      </select>
                                    </div>
                                    
                                    {condition.type === "series" ? (
                                      <>
                                        <div className="flex-1">
                                          <label className="block text-xs text-zinc-400 mb-1">Количество стрел (≥)</label>
                                          <input
                                            type="number"
                                            min="2"
                                            step="1"
                                            value={condition.count || ""}
                                            onChange={(e) => {
                                              const newTemplates = [...conditionalTemplates];
                                              const val = e.target.value === "" ? 2 : parseInt(e.target.value);
                                              newTemplates[index].conditions[condIndex].count = isNaN(val) ? 2 : Math.max(2, val);
                                              const updatedDescription = generateTemplateDescription(newTemplates[index]);
                                              newTemplates[index].description = updatedDescription;
                                              setConditionalTemplates(newTemplates);
                                            }}
                                            className="w-full px-3 py-2 bg-zinc-700 border border-zinc-600 rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
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
                                              const newTemplates = [...conditionalTemplates];
                                              const val = e.target.value === "" ? 300 : parseInt(e.target.value);
                                              newTemplates[index].conditions[condIndex].timeWindowSeconds = isNaN(val) ? 300 : Math.max(60, val);
                                              const updatedDescription = generateTemplateDescription(newTemplates[index]);
                                              newTemplates[index].description = updatedDescription;
                                              setConditionalTemplates(newTemplates);
                                            }}
                                            className="w-full px-3 py-2 bg-zinc-700 border border-zinc-600 rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                                            placeholder="300"
                                          />
                                        </div>
                                      </>
                                    ) : condition.type === "delta" ? (
                                      // Для дельты - диапазон "от/до"
                                      <div className="flex-1">
                                        <label className="block text-xs text-zinc-400 mb-2">Диапазон (%)</label>
                                        <div className="grid grid-cols-2 gap-2">
                                          <div>
                                            <label className="block text-xs text-zinc-500 mb-1">От</label>
                                            <input
                                              type="number"
                                              step="0.1"
                                              min="0"
                                              value={condition.valueMin !== undefined ? condition.valueMin : (condition.value !== undefined ? condition.value : "")}
                                              onChange={(e) => {
                                                const newTemplates = [...conditionalTemplates];
                                                const val = e.target.value === "" ? 0 : parseFloat(e.target.value);
                                                newTemplates[index].conditions[condIndex].valueMin = isNaN(val) ? 0 : val;
                                                // Удаляем старое поле value для обратной совместимости
                                                if (newTemplates[index].conditions[condIndex].value !== undefined) {
                                                  delete newTemplates[index].conditions[condIndex].value;
                                                }
                                                const updatedDescription = generateTemplateDescription(newTemplates[index]);
                                                newTemplates[index].description = updatedDescription;
                                                setConditionalTemplates(newTemplates);
                                              }}
                                              className="w-full px-3 py-2 bg-zinc-700 border border-zinc-600 rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                                              placeholder="0"
                                            />
                                          </div>
                                          <div>
                                            <label className="block text-xs text-zinc-500 mb-1">До</label>
                                            <input
                                              type="text"
                                              value={condition.valueMax === null || condition.valueMax === undefined ? "∞" : condition.valueMax}
                                              onChange={(e) => {
                                                const newTemplates = [...conditionalTemplates];
                                                if (e.target.value === "∞" || e.target.value === "" || e.target.value.trim() === "") {
                                                  newTemplates[index].conditions[condIndex].valueMax = null; // null = бесконечность
                                                } else {
                                                  const numValue = parseFloat(e.target.value);
                                                  if (!isNaN(numValue)) {
                                                    newTemplates[index].conditions[condIndex].valueMax = numValue;
                                                  } else {
                                                    newTemplates[index].conditions[condIndex].valueMax = null;
                                                  }
                                                }
                                                const updatedDescription = generateTemplateDescription(newTemplates[index]);
                                                newTemplates[index].description = updatedDescription;
                                                setConditionalTemplates(newTemplates);
                                              }}
                                              onBlur={(e) => {
                                                // При потере фокуса, если поле пустое, устанавливаем ∞
                                                if (e.target.value === "" || e.target.value.trim() === "") {
                                                  const newTemplates = [...conditionalTemplates];
                                                  newTemplates[index].conditions[condIndex].valueMax = null;
                                                  setConditionalTemplates(newTemplates);
                                                }
                                              }}
                                              placeholder="∞"
                                              className="w-full px-3 py-2 bg-zinc-700 border border-zinc-600 rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                                              title="Введите число или оставьте ∞ для бесконечности"
                                            />
                                          </div>
                                        </div>
                                      </div>
                                    ) : condition.type === "symbol" ? (
                                      // Для символа - поле ввода нормализованного символа
                                      <div className="flex-1">
                                        <label className="block text-xs text-zinc-400 mb-1">Символ (монета)</label>
                                        <input
                                          type="text"
                                          value={condition.symbol || ""}
                                          onChange={(e) => {
                                            const newTemplates = [...conditionalTemplates];
                                            newTemplates[index].conditions[condIndex].symbol = e.target.value.toUpperCase().trim();
                                            const updatedDescription = generateTemplateDescription(newTemplates[index]);
                                            newTemplates[index].description = updatedDescription;
                                            setConditionalTemplates(newTemplates);
                                          }}
                                          className="w-full px-3 py-2 bg-zinc-700 border border-zinc-600 rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                                          placeholder="ETH, BTC, ADA..."
                                          title="Введите нормализованный символ монеты (например: ETH, BTC, ADA). Условие сработает для всех пар с этой монетой на всех биржах."
                                        />
                                        <p className="text-xs text-zinc-500 mt-1">
                                          Используйте нормализованный формат (ETH, BTC). Условие сработает для всех пар с этой монетой.
                                        </p>
                                      </div>
                                    ) : condition.type === "wick_pct" ? (
                                      // Для тени свечи - диапазон "от/до"
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
                                                const newTemplates = [...conditionalTemplates];
                                                const val = e.target.value === "" ? 0 : parseFloat(e.target.value);
                                                newTemplates[index].conditions[condIndex].valueMin = isNaN(val) ? 0 : Math.max(0, Math.min(100, val));
                                                const updatedDescription = generateTemplateDescription(newTemplates[index]);
                                                newTemplates[index].description = updatedDescription;
                                                setConditionalTemplates(newTemplates);
                                              }}
                                              className="w-full px-3 py-2 bg-zinc-700 border border-zinc-600 rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                                              placeholder="0"
                                            />
                                          </div>
                                          <div>
                                            <label className="block text-xs text-zinc-500 mb-1">До</label>
                                            <input
                                              type="text"
                                              value={condition.valueMax === null || condition.valueMax === undefined ? "∞" : condition.valueMax}
                                              onChange={(e) => {
                                                const newTemplates = [...conditionalTemplates];
                                                if (e.target.value === "∞" || e.target.value === "" || e.target.value.trim() === "") {
                                                  newTemplates[index].conditions[condIndex].valueMax = null;
                                                } else {
                                                  const numValue = parseFloat(e.target.value);
                                                  if (!isNaN(numValue)) {
                                                    newTemplates[index].conditions[condIndex].valueMax = Math.max(0, Math.min(100, numValue));
                                                  } else {
                                                    newTemplates[index].conditions[condIndex].valueMax = null;
                                                  }
                                                }
                                                const updatedDescription = generateTemplateDescription(newTemplates[index]);
                                                newTemplates[index].description = updatedDescription;
                                                setConditionalTemplates(newTemplates);
                                              }}
                                              onBlur={(e) => {
                                                if (e.target.value === "" || e.target.value.trim() === "") {
                                                  const newTemplates = [...conditionalTemplates];
                                                  newTemplates[index].conditions[condIndex].valueMax = null;
                                                  const updatedDescription = generateTemplateDescription(newTemplates[index]);
                                                  newTemplates[index].description = updatedDescription;
                                                  setConditionalTemplates(newTemplates);
                                                }
                                              }}
                                              placeholder="∞"
                                              className="w-full px-3 py-2 bg-zinc-700 border border-zinc-600 rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                                              title="Введите число от 0 до 100 или оставьте ∞ для бесконечности"
                                            />
                                          </div>
                                        </div>
                                      </div>
                                    ) : condition.type === "exchange" ? (
                                      // Для биржи - выбор из списка
                                      <div className="flex-1">
                                        <label className="block text-xs text-zinc-400 mb-1">Биржа</label>
                                        <select
                                          value={condition.exchange || "binance"}
                                          onChange={(e) => {
                                            const newTemplates = [...conditionalTemplates];
                                            newTemplates[index].conditions[condIndex].exchange = e.target.value;
                                            const updatedDescription = generateTemplateDescription(newTemplates[index]);
                                            newTemplates[index].description = updatedDescription;
                                            setConditionalTemplates(newTemplates);
                                          }}
                                          className="w-full px-3 py-2 bg-zinc-700 border border-zinc-600 rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                                        >
                                          <option value="binance">Binance</option>
                                          <option value="gate">Gate</option>
                                          <option value="bitget">Bitget</option>
                                          <option value="bybit">Bybit</option>
                                          <option value="hyperliquid">Hyperliquid</option>
                                        </select>
                                      </div>
                                    ) : condition.type === "market" ? (
                                      // Для типа рынка - выбор из списка
                                      <div className="flex-1">
                                        <label className="block text-xs text-zinc-400 mb-1">Тип рынка</label>
                                        <select
                                          value={condition.market || "spot"}
                                          onChange={(e) => {
                                            const newTemplates = [...conditionalTemplates];
                                            newTemplates[index].conditions[condIndex].market = e.target.value as "spot" | "futures" | "linear";
                                            const updatedDescription = generateTemplateDescription(newTemplates[index]);
                                            newTemplates[index].description = updatedDescription;
                                            setConditionalTemplates(newTemplates);
                                          }}
                                          className="w-full px-3 py-2 bg-zinc-700 border border-zinc-600 rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                                        >
                                          <option value="spot">Spot</option>
                                          <option value="futures">Futures</option>
                                          <option value="linear">Linear</option>
                                        </select>
                                      </div>
                                    ) : condition.type === "direction" ? (
                                      // Для направления стрелы - выбор из списка
                                      <div className="flex-1">
                                        <label className="block text-xs text-zinc-400 mb-1">Направление стрелы</label>
                                        <select
                                          value={condition.direction || "up"}
                                          onChange={(e) => {
                                            const newTemplates = [...conditionalTemplates];
                                            newTemplates[index].conditions[condIndex].direction = e.target.value as "up" | "down";
                                            const updatedDescription = generateTemplateDescription(newTemplates[index]);
                                            newTemplates[index].description = updatedDescription;
                                            setConditionalTemplates(newTemplates);
                                          }}
                                          className="w-full px-3 py-2 bg-zinc-700 border border-zinc-600 rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                                        >
                                          <option value="up">Вверх ⬆️</option>
                                          <option value="down">Вниз ⬇️</option>
                                        </select>
                                      </div>
                                    ) : (
                                      // Для объёма - одно значение как было
                                      <div className="flex-1">
                                        <label className="block text-xs text-zinc-400 mb-1">Значение (≥)</label>
                                        <input
                                          type="number"
                                          step="0.01"
                                          value={condition.value || ""}
                                          onChange={(e) => {
                                            const newTemplates = [...conditionalTemplates];
                                            const val = e.target.value === "" ? 0 : parseFloat(e.target.value);
                                            newTemplates[index].conditions[condIndex].value = isNaN(val) ? 0 : val;
                                            const updatedDescription = generateTemplateDescription(newTemplates[index]);
                                            newTemplates[index].description = updatedDescription;
                                            setConditionalTemplates(newTemplates);
                                          }}
                                          className="w-full px-3 py-2 bg-zinc-700 border border-zinc-600 rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                                          placeholder="0"
                                        />
                                      </div>
                                    )}
                                    
                                    {template.conditions.length > 1 && (
                                      <button
                                        onClick={() => {
                                          const newTemplates = [...conditionalTemplates];
                                          newTemplates[index].conditions = newTemplates[index].conditions.filter((_, i) => i !== condIndex);
                                          setConditionalTemplates(newTemplates);
                                        }}
                                        className="px-2 py-2 bg-red-600/50 hover:bg-red-600 text-white text-xs font-medium rounded transition-colors mb-0.5"
                                        title="Удалить условие"
                                      >
                                        ×
                                      </button>
                                    )}
                                  </div>
                                </div>
                              ))}
                            </div>
                          </div>
                          
                          <div>
                            <div className="flex items-center justify-between mb-2">
                              <label className="block text-xs text-zinc-400">
                                Шаблон сообщения
                                <span className="text-xs text-zinc-500 ml-1">(можно вставлять emoji из Telegram через Ctrl+V)</span>
                              </label>
                              <button
                                type="button"
                                ref={(el) => {
                                  if (el) conditionalEmojiButtonRefs.current[index] = el;
                                }}
                                onClick={(e) => {
                                  const button = e.currentTarget;
                                  const rect = button.getBoundingClientRect();
                                  const pickerWidth = 350;
                                  const pickerHeight = 400;
                                  const padding = 8;
                                  
                                  // Вычисляем позицию с учетом границ экрана
                                  let x = rect.left;
                                  let y = rect.bottom + padding;
                                  
                                  // Если picker не помещается справа, сдвигаем влево
                                  if (x + pickerWidth > window.innerWidth) {
                                    x = window.innerWidth - pickerWidth - padding;
                                  }
                                  
                                  // Если picker не помещается снизу, показываем сверху
                                  if (y + pickerHeight > window.innerHeight) {
                                    y = rect.top - pickerHeight - padding;
                                  }
                                  
                                  // Минимальная позиция слева
                                  if (x < padding) {
                                    x = padding;
                                  }
                                  
                                  // Минимальная позиция сверху
                                  if (y < padding) {
                                    y = padding;
                                  }
                                  
                                  setShowEmojiPicker({ 
                                    main: false, 
                                    conditional: showEmojiPicker.conditional === index ? null : index,
                                    position: { x, y }
                                  });
                                }}
                                className="px-2 py-1 bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 hover:border-emerald-500/50 rounded transition-colors text-xs font-medium text-zinc-300 hover:text-white flex items-center gap-1.5"
                                title="Добавить emoji"
                              >
                                <span className="text-sm">😀</span>
                                <span>Emoji</span>
                              </button>
                            </div>
                            
                            {/* Список доступных вставок */}
                            <div className="mb-3">
                              <h4 className="text-xs font-medium text-zinc-400 mb-2">Доступные вставки:</h4>
                              <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                                {[
                                  { friendly: "[[Дельта стрелы]]", label: "Дельта стрелы", desc: "Например: 5.23%" },
                                  { friendly: "[[Направление]]", label: "Направление", desc: "Эмодзи стрелки вверх ⬆️ или вниз ⬇️", descHtml: <>Эмодзи стрелки вверх <span style={{color: '#10b981'}}>⬆️</span> или вниз <span style={{color: '#ef4444'}}>⬇️</span></> },
                                  { friendly: "[[Биржа и тип рынка]]", label: "Биржа и тип рынка", desc: "Название биржи и тип рынка (например: BINANCE | SPOT)" },
                                  { friendly: "[[Торговая пара]]", label: "Торговая пара", desc: "Символ пары (например: BTCUSDT)" },
                                  { friendly: "[[Объём стрелы]]", label: "Объём стрелы", desc: "Объём в USDT" },
                                  { friendly: "[[Тень свечи]]", label: "Тень свечи", desc: "Процент тени свечи (например: 45.2%)" },
                                  { friendly: "[[Время детекта]]", label: "Время детекта", desc: "Дата и время (YYYY-MM-DD HH:MM:SS)" },
                                ].map((placeholder) => (
                                  <button
                                    key={placeholder.friendly}
                                    type="button"
                                    onClick={() => {
                                      const editorId = `conditionalTemplate_${index}`;
                                      const editor = document.getElementById(editorId) as HTMLElement;
                                      if (editor) {
                                        // Устанавливаем фокус на редактор
                                        editor.focus();
                                        
                                        const selection = window.getSelection();
                                        if (selection && selection.rangeCount > 0) {
                                          const range = selection.getRangeAt(0);
                                          range.deleteContents();
                                          
                                          // Создаем красивый визуальный блок для вставки
                                          const block = document.createElement('span');
                                          block.className = 'inline-flex items-center gap-1.5 px-2 py-1 mx-0.5 bg-emerald-500/20 border border-emerald-500/50 rounded text-emerald-300 text-xs font-medium cursor-default';
                                          block.setAttribute('data-placeholder-key', placeholder.friendly);
                                          block.setAttribute('contenteditable', 'false');
                                          block.innerHTML = `
                                            <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 8h10M7 12h4m1 8l-4-4H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-3l-4 4z"></path>
                                            </svg>
                                            <span>${placeholder.label}</span>
                                          `;
                                          
                                          range.insertNode(block);
                                          
                                          // Устанавливаем курсор после блока
                                          const newRange = document.createRange();
                                          newRange.setStartAfter(block);
                                          newRange.collapse(true);
                                          selection.removeAllRanges();
                                          selection.addRange(newRange);
                                        } else {
                                          // Если нет выделения, вставляем в конец
                                          const range = document.createRange();
                                          range.selectNodeContents(editor);
                                          range.collapse(false);
                                          
                                          const block = document.createElement('span');
                                          block.className = 'inline-flex items-center gap-1.5 px-2 py-1 mx-0.5 bg-emerald-500/20 border border-emerald-500/50 rounded text-emerald-300 text-xs font-medium cursor-default';
                                          block.setAttribute('data-placeholder-key', placeholder.friendly);
                                          block.setAttribute('contenteditable', 'false');
                                          block.innerHTML = `
                                            <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 8h10M7 12h4m1 8l-4-4H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-3l-4 4z"></path>
                                            </svg>
                                            <span>${placeholder.label}</span>
                                          `;
                                          
                                          range.insertNode(block);
                                          
                                          const newRange = document.createRange();
                                          newRange.setStartAfter(block);
                                          newRange.collapse(true);
                                          const sel = window.getSelection();
                                          if (sel) {
                                            sel.removeAllRanges();
                                            sel.addRange(newRange);
                                          }
                                        }
                                        
                                        // Обновляем состояние
                                        setTimeout(() => {
                                          const content = editor.innerHTML;
                                          const tempDiv = document.createElement('div');
                                          tempDiv.innerHTML = content;
                                          const blocks = tempDiv.querySelectorAll('[data-placeholder-key]');
                                          let textContent = content;
                                          blocks.forEach((b) => {
                                            const key = b.getAttribute('data-placeholder-key');
                                            if (key) {
                                              const blockHTML = b.outerHTML.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
                                              textContent = textContent.replace(new RegExp(blockHTML, 'g'), key);
                                            }
                                          });
                                          textContent = textContent.replace(/<br\s*\/?>/gi, '\n');
                                          
                                          const newTemplates = [...conditionalTemplates];
                                          newTemplates[index].template = convertToTechnicalKeys(textContent);
                                          setConditionalTemplates(newTemplates);
                                        }, 0);
                                      }
                                    }}
                                    className="text-left px-3 py-2 bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 hover:border-emerald-500/50 rounded-lg transition-colors group"
                                    title={placeholder.desc}
                                  >
                                    <div className="text-sm font-medium text-white group-hover:text-emerald-300 mb-0.5">
                                      {placeholder.label}
                                    </div>
                                    <div className="text-xs text-zinc-500 group-hover:text-zinc-400">
                                      {placeholder.descHtml || placeholder.desc}
                                    </div>
                                  </button>
                                ))}
                              </div>
                            </div>
                            
                            {/* Редактор шаблона */}
                            <div className="relative">
                            <div
                              id={`conditionalTemplate_${index}`}
                              contentEditable
                              suppressContentEditableWarning
                              onInput={(e) => {
                                const editor = e.currentTarget as HTMLElement;
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
                                
                                const newTemplates = [...conditionalTemplates];
                                newTemplates[index].template = convertToTechnicalKeys(textContent);
                                setConditionalTemplates(newTemplates);
                              }}
                              className="w-full min-h-32 px-4 py-3 bg-zinc-800 border border-zinc-700 rounded-lg text-white font-mono text-sm focus:outline-none focus:ring-2 focus:border-transparent focus:ring-emerald-500 resize-none overflow-y-auto template-editor"
                              style={{ whiteSpace: 'pre-wrap' }}
                              onPaste={(e) => {
                                // Разрешаем вставку emoji из буфера обмена
                                e.preventDefault();
                                const text = e.clipboardData.getData('text/plain');
                                const selection = window.getSelection();
                                if (selection && selection.rangeCount > 0) {
                                  const range = selection.getRangeAt(0);
                                  range.deleteContents();
                                  const textNode = document.createTextNode(text);
                                  range.insertNode(textNode);
                                  range.setStartAfter(textNode);
                                  range.collapse(true);
                                  selection.removeAllRanges();
                                  selection.addRange(range);
                                  // Триггерим событие input
                                  const inputEvent = new Event('input', { bubbles: true });
                                  e.currentTarget.dispatchEvent(inputEvent);
                                }
                              }}
                            />
                            </div>
                            
                            {/* Emoji Picker для условного редактора */}
                            {showEmojiPicker.conditional === index && showEmojiPicker.position && (
                              <>
                                <div
                                  className="fixed inset-0 z-40"
                                  onClick={() => setShowEmojiPicker({ main: false, conditional: null })}
                                />
                                <div 
                                  className="fixed z-50"
                                  style={{
                                    left: `${showEmojiPicker.position.x}px`,
                                    top: `${showEmojiPicker.position.y}px`
                                  }}
                                >
                                  <EmojiPicker
                                    onEmojiClick={(emojiData) => insertEmoji(emojiData, `conditionalTemplate_${index}`, true)}
                                    theme={"dark" as any}
                                    width={350}
                                    height={400}
                                    previewConfig={{
                                      showPreview: false
                                    }}
                                  />
                                </div>
                              </>
                            )}
                            
                            <p className="text-xs text-zinc-500 mt-1">
                              Используйте кнопки выше для вставки плейсхолдеров. Emoji можно вставить из Telegram через Ctrl+V или использовать кнопку Emoji.
                            </p>
                          </div>
                          
                          {/* Предварительный просмотр */}
                          <div className="mt-4 pt-4 border-t border-zinc-700">
                            <div className="flex items-center justify-between mb-2">
                              <label className="block text-xs font-medium text-zinc-300">
                                Предварительный просмотр
                              </label>
                            </div>
                            <div className="bg-zinc-900/50 border border-zinc-700/50 rounded-lg p-4">
                              <div 
                                className="text-sm text-white whitespace-pre-wrap"
                                dangerouslySetInnerHTML={{
                                  __html: (() => {
                                    // Генерируем предпросмотр с примерными данными
                                    const previewTemplate = template.template || "";
                                    const previewReplacements: [string, string][] = [
                                      ["{delta_formatted}", "5.23%"],
                                      ["{volume_formatted}", "1,234,567"],
                                      ["{wick_formatted}", "45.2%"],
                                      ["{timestamp}", "1704067200000"],
                                      ["{direction}", "📈"],
                                      ["{exchange_market}", "BINANCE | SPOT"],
                                      ["{exchange}", "BINANCE"],
                                      ["{symbol}", "ETH"],
                                      ["{market}", "SPOT"],
                                      ["{time}", "2024-01-01 12:00:00"],
                                    ];
                                    let preview = previewTemplate;
                                    previewReplacements.forEach(([placeholder, value]) => {
                                      preview = preview.replace(new RegExp(placeholder.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'g'), value);
                                    });
                                    return preview;
                                  })()
                                }}
                              />
                            </div>
                            <p className="text-xs text-zinc-400 mt-2 italic">
                              Это пример того, как будет выглядеть сообщение при выполнении всех условий
                            </p>
                          </div>
                          
                          {/* Блок для отдельного Telegram чата */}
                          <div className="mt-4 pt-4 border-t border-zinc-700">
                            <div className="flex items-center justify-between mb-2">
                              <label className="block text-xs font-medium text-zinc-300">
                                Отправка в Telegram
                              </label>
                              <button
                                type="button"
                                onClick={() => {
                                  const newTemplates = [...conditionalTemplates];
                                  if (newTemplates[index].chatId) {
                                    // Если уже есть Chat ID - убираем его
                                    newTemplates[index].chatId = undefined;
                                  } else {
                                    // Если нет - показываем поле и вставляем основной Chat ID
                                    newTemplates[index].chatId = telegramChatId || "";
                                  }
                                  setConditionalTemplates(newTemplates);
                                }}
                                className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-colors ${
                                  template.chatId
                                    ? "bg-emerald-600 hover:bg-emerald-700 text-white"
                                    : "bg-zinc-700 hover:bg-zinc-600 text-white"
                                }`}
                                title={template.chatId ? "Используется отдельный чат" : "Использовать отдельный Telegram чат для этого шаблона"}
                              >
                                {template.chatId ? "✓ Отдельный чат" : "Использовать отдельный чат"}
                              </button>
                            </div>
                            
                            {template.chatId !== undefined && (
                              <div className="mt-2">
                                <label className="block text-xs text-zinc-400 mb-1">
                                  Telegram Chat ID
                                </label>
                                <div className="flex gap-2 items-center">
                                  <input
                                    type="text"
                                    value={template.chatId || ""}
                                    onChange={(e) => {
                                      const newTemplates = [...conditionalTemplates];
                                      newTemplates[index].chatId = e.target.value.trim() || undefined;
                                      setConditionalTemplates(newTemplates);
                                    }}
                                    placeholder={telegramChatId || "Введите Chat ID"}
                                    className="flex-1 px-3 py-2 bg-zinc-700 border border-zinc-600 rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                                  />
                                  {!template.chatId && (
                                    <button
                                      onClick={() => {
                                        const newTemplates = [...conditionalTemplates];
                                        newTemplates[index].chatId = telegramChatId || "";
                                        setConditionalTemplates(newTemplates);
                                      }}
                                      className="px-3 py-2 bg-zinc-800 hover:bg-zinc-700 border border-zinc-600 rounded-lg text-white text-xs font-medium transition-colors"
                                      title="Вставить основной Chat ID"
                                    >
                                      Вставить основной
                                    </button>
                                  )}
                                </div>
                                <div className="mt-1">
                                  <p className="text-xs text-zinc-500 mb-1">
                                    {template.chatId 
                                      ? `Сообщения будут отправляться в указанный чат (${template.chatId})`
                                      : `Если не указано, сообщения будут отправляться в основной Chat ID (${telegramChatId || "не указан"})`}
                                  </p>
                                  <ChatIdHelp variant="compact" />
                                </div>
                              </div>
                            )}
                            
                            {template.chatId === undefined && (
                              <p className="text-xs text-zinc-500 mt-1">
                                По умолчанию сообщения отправляются в основной Chat ID из настроек Telegram
                              </p>
                            )}
                          </div>
                        </div>
                        )
                      })}
                    </div>
                    
                    <div className="flex gap-3">
                      <button
                        onClick={() => {
                          // Преобразуем messageTemplate в технические ключи перед добавлением
                          const extractedText = extractTextFromEditor();
                          const technicalTemplate = convertToTechnicalKeys(extractedText || messageTemplate);
                          setConditionalTemplates([
                            ...conditionalTemplates,
                            {
                              name: undefined, // Название можно задать позже
                              enabled: true, // По умолчанию включен
                              conditions: [{
                                type: "volume",
                                value: 0,
                              }],
                              template: technicalTemplate,
                            },
                          ]);
                        }}
                        className="px-4 py-2 bg-zinc-700 hover:bg-zinc-600 text-white font-medium rounded-lg smooth-transition"
                      >
                        + Добавить шаблон
                      </button>
                      <button
                        onClick={async () => {
                          await saveAllSettings();
                        }}
                        className="px-4 py-2 bg-gradient-to-r from-emerald-500 to-emerald-600 hover:from-emerald-600 hover:to-emerald-700 text-white font-medium rounded-lg smooth-transition ripple hover-glow shadow-emerald"
                      >
                        Сохранить условные шаблоны
                      </button>
                    </div>
                  </>
                )}
              </div>
              
              {/* Фильтры по биржам */}
              <div className="mb-8 flex gap-4 flex-col lg:flex-row">
                {/* Левая часть - блок с фильтрами */}
                <div className="flex-1 bg-zinc-900 border border-zinc-800 rounded-xl p-6">
                  <div className="flex items-center justify-between mb-1">
                    <div className="flex items-center gap-2">
                      <h2 className="text-xl font-bold text-white">Фильтры по биржам</h2>
                      <svg className="w-5 h-5 text-zinc-400 cursor-help" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <title>Выберите биржи для мониторинга и настройте параметры детектирования для каждой биржи отдельно (Spot и Futures). Можно включить/выключить биржи и настроить минимальные значения дельты, объёма и тени свечи.</title>
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                      </svg>
                    </div>
                    <button
                      onClick={async () => {
                        await saveAllSettings();
                        // Сообщение уже устанавливается в saveAllSettings
                      }}
                      className="px-4 py-2 bg-gradient-to-r from-emerald-500 to-emerald-600 hover:from-emerald-600 hover:to-emerald-700 text-white text-sm font-medium rounded-lg smooth-transition ripple hover-glow shadow-emerald"
                    >
                      Сохранить изменения
                    </button>
                  </div>
                  <p className="text-sm text-zinc-400 mb-6">Выберите биржи для мониторинга и настройте параметры детектирования для каждой биржи отдельно (Spot и Futures). Можно включить/выключить биржи и настроить минимальные значения дельты, объёма и тени свечи.</p>
                  
                  <div className="space-y-2">
                  {["binance", "bybit", "bitget", "gate", "hyperliquid"].map((exchange) => {
                    const isExpanded = expandedExchanges[exchange] || false;
                    const exchangeDisplayName = exchange === "gate" ? "Gate" : exchange === "hyperliquid" ? "Hyperliquid" : exchange.charAt(0).toUpperCase() + exchange.slice(1);
                    const settings = exchangeSettings[exchange];
                    
                    return (
                      <div key={exchange} className="bg-zinc-800 rounded-lg overflow-hidden">
                        {/* Заголовок биржи */}
                        <div className="flex items-center gap-3 p-4">
                          <div
                            className={`w-12 h-6 rounded-full transition-colors cursor-pointer ${
                              exchangeFilters[exchange] ? "bg-emerald-500" : "bg-zinc-600"
                            }`}
                            onClick={(e) => {
                              e.stopPropagation();
                              setExchangeFilters({
                                ...exchangeFilters,
                                [exchange]: !exchangeFilters[exchange],
                              });
                            }}
                          >
                            <div className={`w-5 h-5 bg-white rounded-full transition-transform mt-0.5 ${
                              exchangeFilters[exchange] ? "translate-x-6" : "translate-x-1"
                            }`} />
                          </div>
                          <span
                            className="flex-1 text-white font-medium cursor-pointer hover:text-zinc-300 transition-colors"
                            onClick={() => {
                              setExpandedExchanges({
                                ...expandedExchanges,
                                [exchange]: !isExpanded,
                              });
                            }}
                          >
                            {exchangeDisplayName}
                          </span>
                          <svg
                            className={`w-5 h-5 text-zinc-400 transition-transform cursor-pointer ${
                              isExpanded ? "rotate-180" : ""
                            }`}
                            fill="none"
                            stroke="currentColor"
                            viewBox="0 0 24 24"
                            onClick={() => {
                              setExpandedExchanges({
                                ...expandedExchanges,
                                [exchange]: !isExpanded,
                              });
                            }}
                          >
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                          </svg>
                        </div>
                        
                        {/* Раскрывающийся контент */}
                        {isExpanded && (
                          <div className="px-4 pb-4 space-y-4">
                            {/* Spot секция */}
                            <div className="bg-zinc-900 rounded-lg p-4 space-y-4">
                              <div className="flex items-center justify-between">
                                <div>
                                  <h3 className="text-white font-medium">Spot</h3>
                                  <p className="text-sm text-zinc-400">Все торговые пары</p>
                                </div>
                                <div
                                  className={`w-12 h-6 rounded-full transition-colors cursor-pointer ${
                                    settings.spot.enabled ? "bg-emerald-500" : "bg-zinc-600"
                                  }`}
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    setExchangeSettings({
                                      ...exchangeSettings,
                                      [exchange]: {
                                        ...settings,
                                        spot: { ...settings.spot, enabled: !settings.spot.enabled },
                                      },
                                    });
                                  }}
                                >
                                  <div className={`w-5 h-5 bg-white rounded-full transition-transform mt-0.5 ${
                                    settings.spot.enabled ? "translate-x-6" : "translate-x-1"
                                  }`} />
                                </div>
                              </div>
                              
                              {/* Основная секция со значениями - скрывается при открытии дополнительных пар */}
                              {!openPairs[`${exchange}_spot`] && (
                                <>
                                  <div className="grid grid-cols-3 gap-3">
                                    <div>
                                      <label className="block text-xs text-zinc-400 mb-1">Дельта %</label>
                                      <input
                                        type="number"
                                        value={settings.spot.delta}
                                        onChange={(e) => {
                                          setExchangeSettings({
                                            ...exchangeSettings,
                                            [exchange]: {
                                              ...settings,
                                              spot: { ...settings.spot, delta: e.target.value },
                                            },
                                          });
                                        }}
                                        className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                                      />
                                    </div>
                                    <div>
                                      <label className="block text-xs text-zinc-400 mb-1">Объём USDT</label>
                                      <input
                                        type="number"
                                        value={settings.spot.volume}
                                        onChange={(e) => {
                                          setExchangeSettings({
                                            ...exchangeSettings,
                                            [exchange]: {
                                              ...settings,
                                              spot: { ...settings.spot, volume: e.target.value },
                                            },
                                          });
                                        }}
                                        className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                                      />
                                    </div>
                                    <div>
                                      <label className="block text-xs text-zinc-400 mb-1">Тень %</label>
                                      <input
                                        type="number"
                                        value={settings.spot.shadow}
                                        onChange={(e) => {
                                          setExchangeSettings({
                                            ...exchangeSettings,
                                            [exchange]: {
                                              ...settings,
                                              spot: { ...settings.spot, shadow: e.target.value },
                                            },
                                          });
                                        }}
                                        className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                                      />
                                    </div>
                                  </div>
                                  
                                  {(exchange === "binance" || (exchange === "bybit")) && (
                                    <div className="flex justify-end">
                                      <button
                                        onClick={(e) => {
                                          e.stopPropagation();
                                          const key = `${exchange}_spot`;
                                          setOpenPairs({
                                            ...openPairs,
                                            [key]: !openPairs[key],
                                          });
                                        }}
                                        className="px-3 py-1.5 bg-zinc-700 hover:bg-zinc-600 text-white text-sm font-medium rounded-lg transition-colors"
                                      >
                                        Открыть дополнительные пары
                                      </button>
                                    </div>
                                  )}
                                </>
                              )}
                              
                              {/* Блок с дополнительными парами для Spot */}
                              {((exchange === "binance" || exchange === "bybit") && openPairs[`${exchange}_spot`]) && (
                                <>
                                  <div className="flex justify-end mb-4">
                                    <button
                                      onClick={(e) => {
                                        e.stopPropagation();
                                        const key = `${exchange}_spot`;
                                        setOpenPairs({
                                          ...openPairs,
                                          [key]: false,
                                        });
                                      }}
                                      className="px-3 py-1.5 bg-zinc-700 hover:bg-zinc-600 text-white text-sm font-medium rounded-lg transition-colors"
                                    >
                                      Скрыть пары
                                    </button>
                                  </div>
                                  <div className="bg-zinc-950 rounded-lg p-4 border border-zinc-700">
                                  <h4 className="text-sm font-medium text-white mb-4">Дополнительные пары для Spot</h4>
                                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                                    {getPairsForExchange(exchange, "spot").map((pair) => {
                                      const pairKey = `${exchange}_spot_${pair}`;
                                      const savedPairData = pairSettings[pairKey];
                                      const spotSettings = settings.spot;
                                      
                                      // Используем общие настройки Spot, если для пары не заданы индивидуальные
                                      const pairData = savedPairData || {
                                        enabled: true,
                                        delta: spotSettings.delta || "0",
                                        volume: spotSettings.volume || "0",
                                        shadow: spotSettings.shadow || "0"
                                      };
                                      
                                      return (
                                        <div key={pair} className="bg-zinc-800 rounded-lg p-3 space-y-2">
                                          <div className="flex items-center justify-between mb-2">
                                            <div className="text-white font-medium text-sm">{pair}</div>
                                            <div
                                              className={`w-10 h-5 rounded-full transition-colors cursor-pointer ${
                                                pairData.enabled ? "bg-emerald-500" : "bg-zinc-600"
                                              }`}
                                              onClick={() => {
                                                setPairSettings({
                                                  ...pairSettings,
                                                  [pairKey]: { ...pairData, enabled: !pairData.enabled },
                                                });
                                              }}
                                            >
                                              <div className={`w-4 h-4 bg-white rounded-full transition-transform mt-0.5 ${
                                                pairData.enabled ? "translate-x-5" : "translate-x-1"
                                              }`} />
                                            </div>
                                          </div>
                                          <div>
                                            <label className="block text-xs text-zinc-400 mb-1">Дельта %</label>
                                            <input
                                              type="number"
                                              value={pairData.delta}
                                              onChange={(e) => {
                                                setPairSettings({
                                                  ...pairSettings,
                                                  [pairKey]: { ...pairData, delta: e.target.value },
                                                });
                                              }}
                                              className="w-full px-2 py-1 bg-zinc-900 border border-zinc-700 rounded text-white text-xs focus:outline-none focus:ring-1 focus:ring-emerald-500"
                                              placeholder={spotSettings.delta || "0"}
                                            />
                                          </div>
                                          <div>
                                            <label className="block text-xs text-zinc-400 mb-1">Объём USDT</label>
                                            <input
                                              type="number"
                                              value={pairData.volume}
                                              onChange={(e) => {
                                                setPairSettings({
                                                  ...pairSettings,
                                                  [pairKey]: { ...pairData, volume: e.target.value },
                                                });
                                              }}
                                              className="w-full px-2 py-1 bg-zinc-900 border border-zinc-700 rounded text-white text-xs focus:outline-none focus:ring-1 focus:ring-emerald-500"
                                              placeholder={spotSettings.volume || "0"}
                                            />
                                          </div>
                                          <div>
                                            <label className="block text-xs text-zinc-400 mb-1">Тень %</label>
                                            <input
                                              type="number"
                                              value={pairData.shadow}
                                              onChange={(e) => {
                                                setPairSettings({
                                                  ...pairSettings,
                                                  [pairKey]: { ...pairData, shadow: e.target.value },
                                                });
                                              }}
                                              className="w-full px-2 py-1 bg-zinc-900 border border-zinc-700 rounded text-white text-xs focus:outline-none focus:ring-1 focus:ring-emerald-500"
                                              placeholder={spotSettings.shadow || "0"}
                                            />
                                          </div>
                                        </div>
                                      );
                                    })}
                                  </div>
                                </div>
                                </>
                              )}
                            </div>
                            
                            {/* Futures секция */}
                            <div className="bg-zinc-900 rounded-lg p-4 space-y-4">
                              <div className="flex items-center justify-between">
                                <div>
                                  <h3 className="text-white font-medium">Futures</h3>
                                  <p className="text-sm text-zinc-400">Все торговые пары</p>
                                </div>
                                <div
                                  className={`w-12 h-6 rounded-full transition-colors cursor-pointer ${
                                    settings.futures.enabled ? "bg-emerald-500" : "bg-zinc-600"
                                  }`}
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    setExchangeSettings({
                                      ...exchangeSettings,
                                      [exchange]: {
                                        ...settings,
                                        futures: { ...settings.futures, enabled: !settings.futures.enabled },
                                      },
                                    });
                                  }}
                                >
                                  <div className={`w-5 h-5 bg-white rounded-full transition-transform mt-0.5 ${
                                    settings.futures.enabled ? "translate-x-6" : "translate-x-1"
                                  }`} />
                                </div>
                              </div>
                              
                              {/* Основная секция со значениями - скрывается при открытии дополнительных пар */}
                              {!openPairs[`${exchange}_futures`] && (
                                <>
                                  <div className="grid grid-cols-3 gap-3">
                                    <div>
                                      <label className="block text-xs text-zinc-400 mb-1">Дельта %</label>
                                      <input
                                        type="number"
                                        value={settings.futures.delta}
                                        onChange={(e) => {
                                          setExchangeSettings({
                                            ...exchangeSettings,
                                            [exchange]: {
                                              ...settings,
                                              futures: { ...settings.futures, delta: e.target.value },
                                            },
                                          });
                                        }}
                                        className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                                      />
                                    </div>
                                    <div>
                                      <label className="block text-xs text-zinc-400 mb-1">Объём USDT</label>
                                      <input
                                        type="number"
                                        value={settings.futures.volume}
                                        onChange={(e) => {
                                          setExchangeSettings({
                                            ...exchangeSettings,
                                            [exchange]: {
                                              ...settings,
                                              futures: { ...settings.futures, volume: e.target.value },
                                            },
                                          });
                                        }}
                                        className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                                      />
                                    </div>
                                    <div>
                                      <label className="block text-xs text-zinc-400 mb-1">Тень %</label>
                                      <input
                                        type="number"
                                        value={settings.futures.shadow}
                                        onChange={(e) => {
                                          setExchangeSettings({
                                            ...exchangeSettings,
                                            [exchange]: {
                                              ...settings,
                                              futures: { ...settings.futures, shadow: e.target.value },
                                            },
                                          });
                                        }}
                                        className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                                      />
                                    </div>
                                  </div>
                                  
                                  {exchange === "binance" && (
                                    <div className="flex justify-end">
                                      <button
                                        onClick={(e) => {
                                          e.stopPropagation();
                                          const key = `${exchange}_futures`;
                                          setOpenPairs({
                                            ...openPairs,
                                            [key]: !openPairs[key],
                                          });
                                        }}
                                        className="px-3 py-1.5 bg-zinc-700 hover:bg-zinc-600 text-white text-sm font-medium rounded-lg transition-colors"
                                      >
                                        Открыть дополнительные пары
                                      </button>
                                    </div>
                                  )}
                                </>
                              )}
                              
                              {/* Блок с дополнительными парами для Futures */}
                              {exchange === "binance" && openPairs[`${exchange}_futures`] && (
                                <>
                                  <div className="flex justify-end mb-4">
                                    <button
                                      onClick={(e) => {
                                        e.stopPropagation();
                                        const key = `${exchange}_futures`;
                                        setOpenPairs({
                                          ...openPairs,
                                          [key]: false,
                                        });
                                      }}
                                      className="px-3 py-1.5 bg-zinc-700 hover:bg-zinc-600 text-white text-sm font-medium rounded-lg transition-colors"
                                    >
                                      Скрыть пары
                                    </button>
                                  </div>
                                  <div className="bg-zinc-950 rounded-lg p-4 border border-zinc-700">
                                  <h4 className="text-sm font-medium text-white mb-4">Дополнительные пары для Futures</h4>
                                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                                    {getPairsForExchange(exchange, "futures").map((pair) => {
                                      const pairKey = `${exchange}_futures_${pair}`;
                                      const savedPairData = pairSettings[pairKey];
                                      const futuresSettings = settings.futures;
                                      
                                      // Используем общие настройки Futures, если для пары не заданы индивидуальные
                                      const pairData = savedPairData || {
                                        enabled: true,
                                        delta: futuresSettings.delta || "0",
                                        volume: futuresSettings.volume || "0",
                                        shadow: futuresSettings.shadow || "0"
                                      };
                                      
                                      return (
                                        <div key={pair} className="bg-zinc-800 rounded-lg p-3 space-y-2">
                                          <div className="flex items-center justify-between mb-2">
                                            <div className="text-white font-medium text-sm">{pair}</div>
                                            <div
                                              className={`w-10 h-5 rounded-full transition-colors cursor-pointer ${
                                                pairData.enabled ? "bg-emerald-500" : "bg-zinc-600"
                                              }`}
                                              onClick={() => {
                                                setPairSettings({
                                                  ...pairSettings,
                                                  [pairKey]: { ...pairData, enabled: !pairData.enabled },
                                                });
                                              }}
                                            >
                                              <div className={`w-4 h-4 bg-white rounded-full transition-transform mt-0.5 ${
                                                pairData.enabled ? "translate-x-5" : "translate-x-1"
                                              }`} />
                                            </div>
                                          </div>
                                          <div>
                                            <label className="block text-xs text-zinc-400 mb-1">Дельта %</label>
                                            <input
                                              type="number"
                                              value={pairData.delta}
                                              onChange={(e) => {
                                                setPairSettings({
                                                  ...pairSettings,
                                                  [pairKey]: { ...pairData, delta: e.target.value },
                                                });
                                              }}
                                              className="w-full px-2 py-1 bg-zinc-900 border border-zinc-700 rounded text-white text-xs focus:outline-none focus:ring-1 focus:ring-emerald-500"
                                              placeholder={futuresSettings.delta || "0"}
                                            />
                                          </div>
                                          <div>
                                            <label className="block text-xs text-zinc-400 mb-1">Объём USDT</label>
                                            <input
                                              type="number"
                                              value={pairData.volume}
                                              onChange={(e) => {
                                                setPairSettings({
                                                  ...pairSettings,
                                                  [pairKey]: { ...pairData, volume: e.target.value },
                                                });
                                              }}
                                              className="w-full px-2 py-1 bg-zinc-900 border border-zinc-700 rounded text-white text-xs focus:outline-none focus:ring-1 focus:ring-emerald-500"
                                              placeholder={futuresSettings.volume || "0"}
                                            />
                                          </div>
                                          <div>
                                            <label className="block text-xs text-zinc-400 mb-1">Тень %</label>
                                            <input
                                              type="number"
                                              value={pairData.shadow}
                                              onChange={(e) => {
                                                setPairSettings({
                                                  ...pairSettings,
                                                  [pairKey]: { ...pairData, shadow: e.target.value },
                                                });
                                              }}
                                              className="w-full px-2 py-1 bg-zinc-900 border border-zinc-700 rounded text-white text-xs focus:outline-none focus:ring-1 focus:ring-emerald-500"
                                              placeholder={futuresSettings.shadow || "0"}
                                            />
                                          </div>
                                        </div>
                                      );
                                    })}
                                  </div>
                                </div>
                                </>
                              )}
                            </div>
                          </div>
                        )}
                      </div>
                    );
                  })}
                  </div>
                </div>
                
                {/* Правая часть - таблица с актуальными фильтрами */}
                <div className="lg:w-96 bg-zinc-900 border border-zinc-800 rounded-xl p-3">
                  <h2 className="text-sm font-bold text-white mb-2">Активные фильтры</h2>
                  
                  <div className="overflow-x-auto">
                    {(() => {
                      const tableRows: Array<{
                        exchange: string;
                        market: string;
                        pair: string | null;
                        delta: string;
                        volume: string;
                        shadow: string;
                      }> = [];
                      
                      ["binance", "bybit", "bitget", "gate", "hyperliquid"].forEach((exchange) => {
                        if (exchangeFilters[exchange]) {
                          const exchangeDisplayName = exchange === "gate" ? "Gate" : exchange === "hyperliquid" ? "Hyperliquid" : exchange.charAt(0).toUpperCase() + exchange.slice(1);
                          const settings = exchangeSettings[exchange];
                          
                          if (settings.spot.enabled) {
                            tableRows.push({
                              exchange: exchangeDisplayName,
                              market: "Spot",
                              pair: null,
                              delta: settings.spot.delta || "0",
                              volume: settings.spot.volume || "0",
                              shadow: settings.spot.shadow || "0",
                            });
                          }
                          
                          if (settings.futures.enabled) {
                            tableRows.push({
                              exchange: exchangeDisplayName,
                              market: "Futures",
                              pair: null,
                              delta: settings.futures.delta || "0",
                              volume: settings.futures.volume || "0",
                              shadow: settings.futures.shadow || "0",
                            });
                          }
                          
                          // Проверяем индивидуальные настройки пар
                          Object.entries(pairSettings).forEach(([key, pairData]) => {
                            if (pairData.enabled && key.startsWith(`${exchange}_`)) {
                              const parts = key.split("_");
                              if (parts.length >= 3) {
                                const marketType = parts[1]; // spot или futures
                                const pair = parts.slice(2).join("_");
                                tableRows.push({
                                  exchange: exchangeDisplayName,
                                  market: marketType === "spot" ? "Spot" : "Futures",
                                  pair: pair,
                                  delta: pairData.delta || "0",
                                  volume: pairData.volume || "0",
                                  shadow: pairData.shadow || "0",
                                });
                              }
                            }
                          });
                        }
                      });
                      
                      if (tableRows.length === 0) {
                        return (
                          <div className="text-center py-2">
                            <p className="text-zinc-500 text-xs">Нет активных фильтров</p>
                          </div>
                        );
                      }
                      
                      return (
                        <table className="w-full text-xs">
                          <thead>
                            <tr className="border-b border-zinc-700">
                              <th className="text-left py-1 px-2 text-zinc-400 font-medium">Биржа</th>
                              <th className="text-left py-1 px-2 text-zinc-400 font-medium">Рынок</th>
                              <th className="text-left py-1 px-2 text-zinc-400 font-medium">Пара</th>
                              <th className="text-right py-1 px-2 text-zinc-400 font-medium">Δ%</th>
                              <th className="text-right py-1 px-2 text-zinc-400 font-medium">Объём</th>
                              <th className="text-right py-1 px-2 text-zinc-400 font-medium">Тень%</th>
                            </tr>
                          </thead>
                          <tbody>
                            {tableRows.map((row, idx) => (
                              <tr key={idx} className={`border-b border-zinc-800/50 ${row.pair ? 'bg-zinc-800/30' : ''}`}>
                                <td className="py-1 px-2 text-white">{row.exchange}</td>
                                <td className="py-1 px-2 text-emerald-400">{row.market}</td>
                                <td className="py-1 px-2 text-zinc-400">{row.pair || '-'}</td>
                                <td className="py-1 px-2 text-right text-white">{row.delta}</td>
                                <td className="py-1 px-2 text-right text-white">{row.volume}</td>
                                <td className="py-1 px-2 text-right text-white">{row.shadow}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      );
                    })()}
                  </div>
                </div>
              </div>
              
              {/* Чёрный список монет */}
              <div className="mb-8 bg-zinc-900 border border-zinc-800 rounded-xl p-6">
                <div className="flex items-center gap-2 mb-1">
                  <h2 className="text-xl font-bold text-white">Чёрный список монет</h2>
                  <svg className="w-5 h-5 text-zinc-400 cursor-help" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <title>Добавьте монеты в чёрный список, чтобы исключить их из детектирования. Монеты из этого списка не будут отслеживаться, даже если они соответствуют всем критериям детектирования.</title>
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                </div>
                <p className="text-sm text-zinc-400 mb-6">Исключите монеты из детектирования. Монеты из чёрного списка не будут отслеживаться системой.</p>
                
                <div className="space-y-4">
                  <div className="flex gap-3">
                    <input
                      type="text"
                      value={newBlacklistSymbol}
                      onChange={(e) => setNewBlacklistSymbol(e.target.value.toUpperCase())}
                      placeholder="Символ монеты (например, BTC или ETHUSDT)"
                      className="flex-1 px-4 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent"
                      title="Можно вводить как нормализованный формат (BTC, ETH), так и исходный формат биржи (BTCUSDT, ETH_USDT)"
                    />
                    <button
                      onClick={() => {
                        if (!newBlacklistSymbol.trim()) return;
                        const symbol = newBlacklistSymbol.trim().toUpperCase();
                        if (!blacklist.includes(symbol)) {
                          setBlacklist([...blacklist, symbol]);
                          setNewBlacklistSymbol("");
                        }
                      }}
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
                            onClick={() => {
                              setBlacklist(blacklist.filter((s) => s !== symbol));
                            }}
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
            </div>
          )}

          {/* Админ панель */}
          {activeTab === "admin" && isAdmin && (
            <div className="mb-6 md:mb-8">
              <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 mb-4">
                <div>
                  <h1 className="text-2xl md:text-3xl font-bold text-white mb-2">Админ панель</h1>
                  <p className="text-zinc-400">
                    Управление пользователями системы
                  </p>
                </div>
                {/* Кнопка удаления рыночной статистики */}
                <button
                  onClick={deleteGlobalStats}
                  disabled={deletingGlobalStats}
                  className={`px-6 py-3 rounded-lg text-sm font-medium transition-colors ${
                    deletingGlobalStats
                      ? "bg-zinc-700 text-zinc-400 cursor-not-allowed"
                      : "bg-red-600 hover:bg-red-700 text-white"
                  }`}
                  title="Удалить всю рыночную статистику стрел (пользователь 'Stats')"
                >
                  {deletingGlobalStats ? (
                    <span className="flex items-center gap-2">
                      <span className="w-4 h-4 border-2 border-zinc-400 border-t-transparent rounded-full animate-spin"></span>
                      Удаление...
                    </span>
                  ) : (
                    "🗑️ Удалить рыночную статистику"
                  )}
                </button>
              </div>

              {/* Уведомление админ панели по центру экрана */}
              {adminMsg && (
                <div className="fixed top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2 z-50">
                  <div className="p-6 rounded-xl shadow-2xl max-w-md bg-emerald-500/95 text-white border-2 border-emerald-400">
                    <p className="font-semibold text-lg">{adminMsg}</p>
                  </div>
                </div>
              )}

              {/* Форма создания нового пользователя */}
              <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6 mb-8">
                <h2 className="text-xl font-bold text-white mb-4">Новый пользователь</h2>

                <div className="grid gap-4">
                  <div>
                    <label className="block text-sm font-medium text-zinc-300 mb-2">
                      Имя пользователя
                    </label>
                    <input
                      type="text"
                      value={adminForm}
                      onChange={(e) => setAdminForm(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') {
                          createAdminUser();
                        }
                      }}
                      placeholder="Введите имя пользователя"
                      className="w-full px-4 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
                    />
                    <p className="mt-2 text-xs text-zinc-500">
                      Введите имя пользователя, чтобы дать разрешение на использование сайта
                    </p>
                  </div>

                  <div className="flex gap-3 pt-2">
                    <button
                      onClick={createAdminUser}
                      disabled={adminLoading}
                      className="px-6 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      {adminLoading ? "Создание..." : "Создать пользователя"}
                    </button>
                    <button
                      onClick={() => setAdminForm("")}
                      disabled={adminLoading}
                      className="px-6 py-2 bg-gray-500 text-white rounded-lg hover:bg-gray-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      Очистить
                    </button>
                  </div>
                </div>
              </div>

              {/* Список пользователей */}
              <div className="mb-8 bg-zinc-900 border border-zinc-800 rounded-xl p-6">
                <h2 className="text-xl font-bold text-white mb-4">
                  Пользователи ({adminUsers.length})
                </h2>
                {adminUsers.length === 0 ? (
                  <div className="text-zinc-600">Нет пользователей</div>
                ) : (
                  <div className="space-y-2">
                    {adminUsers.map((user) => {
                      const statuses = getAdminUserStatus(user);
                      const lowerUserName = user.user.trim().toLowerCase();
                      const isSystemUser = lowerUserName === "stats" || lowerUserName === "влад";

                      return (
                        <div
                          key={user.user}
                          className="flex items-center justify-between p-3 bg-зинк-800 rounded-lg hover:bg-зинк-700 transition-colors"
                        >
                          <div className="flex items-center gap-3">
                            <button
                              onClick={() => loadUserSettings(user.user)}
                              className="font-medium text-white hover:text-blue-400 transition-colors text-left"
                            >
                              {user.user}
                            </button>
                            {isSystemUser ? (
                              <span className="px-2 py-0.5 bg-blue-900/30 text-blue-400 border border-blue-500/40 rounded text-xs">
                                Системный
                              </span>
                            ) : (
                              <>
                                <span
                                  className={`px-2 py-0.5 border rounded text-xs ${
                                    statuses.telegramActive
                                      ? "bg-emerald-500/20 text-emerald-300 border-emerald-400/60"
                                      : "bg-red-500/20 text-red-300 border-red-500/50"
                                  }`}
                                >
                                  Telegram: {statuses.telegramActive ? "ON" : "OFF"}
                                </span>
                                <span
                                  className={`px-2 py-0.5 border rounded text-xs ${
                                    statuses.settingsActive
                                      ? "bg-emerald-500/20 text-emerald-300 border-emerald-400/60"
                                      : "bg-red-500/20 text-red-300 border-red-500/50"
                                  }`}
                                >
                                  Настройки: {statuses.settingsActive ? "ON" : "OFF"}
                                </span>
                              </>
                            )}
                          </div>
                          <button
                            onClick={() => deleteAdminUser(user.user)}
                            disabled={isSystemUser}
                            className="px-3 py-1 bg-red-500 text-white rounded hover:bg-red-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                          >
                            Удалить
                          </button>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>

              {/* Панель настроек выбранного пользователя */}
              {selectedUserSettings && (
                <div className="mb-8 bg-zinc-900 border border-zinc-800 rounded-xl p-6">
                  <div className="flex items-center justify-between mb-4">
                    <h2 className="text-xl font-bold text-white">
                      Настройки: {selectedUserSettings.user}
                    </h2>
                    <button
                      onClick={() => setSelectedUserSettings(null)}
                      className="px-3 py-1 bg-zinc-700 text-white rounded hover:bg-zinc-600 transition-colors"
                    >
                      Закрыть
                    </button>
                  </div>

                  <div className="space-y-4">
                    {/* Telegram */}
                    <div className="border-t border-zinc-700 pt-4">
                      <h3 className="text-lg font-semibold text-white mb-3">Telegram</h3>
                      <div className="grid md:grid-cols-2 gap-4">
                        <div>
                          <label className="block text-sm text-zinc-400 mb-1">Chat ID</label>
                          <input
                            type="text"
                            value={selectedUserSettings.chat_id || ""}
                            onChange={(e) =>
                              setSelectedUserSettings({
                                ...selectedUserSettings,
                                chat_id: e.target.value,
                              })
                            }
                            placeholder="Не настроен"
                            className="w-full px-4 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
                          />
                        </div>
                        <div>
                          <label className="block text-sm text-zinc-400 mb-1">Bot Token</label>
                          <input
                            type="text"
                            value={selectedUserSettings.tg_token || ""}
                            onChange={(e) =>
                              setSelectedUserSettings({
                                ...selectedUserSettings,
                                tg_token: e.target.value,
                              })
                            }
                            placeholder="Не настроен"
                            className="w-full px-4 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
                          />
                        </div>
                      </div>
                    </div>

                    {/* Настройки бирж */}
                    <div className="border-t border-zinc-700 pt-4">
                      <div className="flex items-center justify-between mb-3">
                        <h3 className="text-lg font-semibold text-white">Фильтры по биржам</h3>
                        <button
                          onClick={saveAdminUserSettings}
                          disabled={adminLoading}
                          className="px-4 py-2 bg-gradient-to-r from-emerald-500 to-emerald-600 hover:from-emerald-600 hover:to-emerald-700 text-white text-sm font-medium rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                          {adminLoading ? "Сохранение..." : "Сохранить изменения"}
                        </button>
                      </div>
                      <p className="text-sm text-zinc-400 mb-4">Выберите биржи для мониторинга и настройте параметры</p>
                      
                      <div className="space-y-2">
                        {["binance", "bybit", "bitget", "gate", "hyperliquid"].map((exchange) => {
                          const isExpanded = adminExpandedExchanges[exchange] || false;
                          const exchangeDisplayName = exchange === "gate" ? "Gate" : exchange === "hyperliquid" ? "Hyperliquid" : exchange.charAt(0).toUpperCase() + exchange.slice(1);
                          const settings = adminExchangeSettings[exchange] || { spot: { enabled: true, delta: "0", volume: "0", shadow: "0" }, futures: { enabled: true, delta: "0", volume: "0", shadow: "0" } };
                          
                          return (
                            <div key={exchange} className="bg-zinc-800 rounded-lg overflow-hidden">
                              {/* Заголовок биржи */}
                              <div className="flex items-center gap-3 p-4">
                                <div
                                  className={`w-12 h-6 rounded-full transition-colors cursor-pointer ${
                                    adminExchangeFilters[exchange] ? "bg-emerald-500" : "bg-zinc-600"
                                  }`}
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    setAdminExchangeFilters({
                                      ...adminExchangeFilters,
                                      [exchange]: !adminExchangeFilters[exchange],
                                    });
                                  }}
                                >
                                  <div className={`w-5 h-5 bg-white rounded-full transition-transform mt-0.5 ${
                                    adminExchangeFilters[exchange] ? "translate-x-6" : "translate-x-1"
                                  }`} />
                                </div>
                                <span
                                  className="flex-1 text-white font-medium cursor-pointer hover:text-zinc-300 transition-colors"
                                  onClick={() => {
                                    setAdminExpandedExchanges({
                                      ...adminExpandedExchanges,
                                      [exchange]: !isExpanded,
                                    });
                                  }}
                                >
                                  {exchangeDisplayName}
                                </span>
                                <svg
                                  className={`w-5 h-5 text-zinc-400 transition-transform cursor-pointer ${
                                    isExpanded ? "rotate-180" : ""
                                  }`}
                                  fill="none"
                                  stroke="currentColor"
                                  viewBox="0 0 24 24"
                                  onClick={() => {
                                    setAdminExpandedExchanges({
                                      ...adminExpandedExchanges,
                                      [exchange]: !isExpanded,
                                    });
                                  }}
                                >
                                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                                </svg>
                              </div>
                              
                              {/* Раскрывающийся контент */}
                              {isExpanded && (
                                <div className="px-4 pb-4 space-y-4">
                                  {/* Spot секция */}
                                  <div className="bg-zinc-900 rounded-lg p-4 space-y-4">
                                    <div className="flex items-center justify-between">
                                      <div>
                                        <h3 className="text-white font-medium">Spot</h3>
                                        <p className="text-sm text-zinc-400">Все торговые пары</p>
                                      </div>
                                      <div
                                        className={`w-12 h-6 rounded-full transition-colors cursor-pointer ${
                                          settings.spot.enabled ? "bg-emerald-500" : "bg-zinc-600"
                                        }`}
                                        onClick={(e) => {
                                          e.stopPropagation();
                                          setAdminExchangeSettings({
                                            ...adminExchangeSettings,
                                            [exchange]: {
                                              ...settings,
                                              spot: { ...settings.spot, enabled: !settings.spot.enabled },
                                            },
                                          });
                                        }}
                                      >
                                        <div className={`w-5 h-5 bg-white rounded-full transition-transform mt-0.5 ${
                                          settings.spot.enabled ? "translate-x-6" : "translate-x-1"
                                        }`} />
                                      </div>
                                    </div>
                                    
                                    {!adminOpenPairs[`${exchange}_spot`] && (
                                      <div className="grid grid-cols-3 gap-3">
                                        <div>
                                          <label className="block text-xs text-zinc-400 mb-1">Дельта %</label>
                                          <input
                                            type="number"
                                            value={settings.spot.delta}
                                            onChange={(e) => {
                                              setAdminExchangeSettings({
                                                ...adminExchangeSettings,
                                                [exchange]: {
                                                  ...settings,
                                                  spot: { ...settings.spot, delta: e.target.value },
                                                },
                                              });
                                            }}
                                            className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                                          />
                                        </div>
                                        <div>
                                          <label className="block text-xs text-zinc-400 mb-1">Объём USDT</label>
                                          <input
                                            type="number"
                                            value={settings.spot.volume}
                                            onChange={(e) => {
                                              setAdminExchangeSettings({
                                                ...adminExchangeSettings,
                                                [exchange]: {
                                                  ...settings,
                                                  spot: { ...settings.spot, volume: e.target.value },
                                                },
                                              });
                                            }}
                                            className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                                          />
                                        </div>
                                        <div>
                                          <label className="block text-xs text-zinc-400 mb-1">Тень %</label>
                                          <input
                                            type="number"
                                            value={settings.spot.shadow}
                                            onChange={(e) => {
                                              setAdminExchangeSettings({
                                                ...adminExchangeSettings,
                                                [exchange]: {
                                                  ...settings,
                                                  spot: { ...settings.spot, shadow: e.target.value },
                                                },
                                              });
                                            }}
                                            className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                                          />
                                        </div>
                                      </div>
                                    )}
                                    
                                    {/* Дополнительные пары для Spot (если есть) */}
                                    {((exchange === "binance" || exchange === "bybit") && adminOpenPairs[`${exchange}_spot`]) && (
                                      <div className="bg-zinc-950 rounded-lg p-4 border border-zinc-700">
                                        <h4 className="text-sm font-medium text-white mb-4">Дополнительные пары для Spot</h4>
                                        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                                          {getPairsForExchange(exchange, "spot").map((pair) => {
                                            const pairKey = `${exchange}_spot_${pair}`;
                                            const savedPairData = adminPairSettings[pairKey];
                                            const spotSettings = settings.spot;
                                            
                                            const pairData = savedPairData || {
                                              enabled: true,
                                              delta: spotSettings.delta || "0",
                                              volume: spotSettings.volume || "0",
                                              shadow: spotSettings.shadow || "0"
                                            };
                                            
                                            return (
                                              <div key={pair} className="bg-zinc-800 rounded-lg p-3 space-y-2">
                                                <div className="flex items-center justify-between mb-2">
                                                  <div className="text-white font-medium text-sm">{pair}</div>
                                                  <div
                                                    className={`w-10 h-5 rounded-full transition-colors cursor-pointer ${
                                                      pairData.enabled ? "bg-emerald-500" : "bg-zinc-600"
                                                    }`}
                                                    onClick={() => {
                                                      setAdminPairSettings({
                                                        ...adminPairSettings,
                                                        [pairKey]: { ...pairData, enabled: !pairData.enabled },
                                                      });
                                                    }}
                                                  >
                                                    <div className={`w-4 h-4 bg-white rounded-full transition-transform mt-0.5 ${
                                                      pairData.enabled ? "translate-x-5" : "translate-x-1"
                                                    }`} />
                                                  </div>
                                                </div>
                                                <div>
                                                  <label className="block text-xs text-zinc-400 mb-1">Дельта %</label>
                                                  <input
                                                    type="number"
                                                    value={pairData.delta}
                                                    onChange={(e) => {
                                                      setAdminPairSettings({
                                                        ...adminPairSettings,
                                                        [pairKey]: { ...pairData, delta: e.target.value },
                                                      });
                                                    }}
                                                    className="w-full px-2 py-1 bg-zinc-900 border border-zinc-700 rounded text-white text-xs focus:outline-none focus:ring-1 focus:ring-emerald-500"
                                                  />
                                                </div>
                                                <div>
                                                  <label className="block text-xs text-zinc-400 mb-1">Объём USDT</label>
                                                  <input
                                                    type="number"
                                                    value={pairData.volume}
                                                    onChange={(e) => {
                                                      setAdminPairSettings({
                                                        ...adminPairSettings,
                                                        [pairKey]: { ...pairData, volume: e.target.value },
                                                      });
                                                    }}
                                                    className="w-full px-2 py-1 bg-zinc-900 border border-zinc-700 rounded text-white text-xs focus:outline-none focus:ring-1 focus:ring-emerald-500"
                                                  />
                                                </div>
                                                <div>
                                                  <label className="block text-xs text-zinc-400 mb-1">Тень %</label>
                                                  <input
                                                    type="number"
                                                    value={pairData.shadow}
                                                    onChange={(e) => {
                                                      setAdminPairSettings({
                                                        ...adminPairSettings,
                                                        [pairKey]: { ...pairData, shadow: e.target.value },
                                                      });
                                                    }}
                                                    className="w-full px-2 py-1 bg-zinc-900 border border-zinc-700 rounded text-white text-xs focus:outline-none focus:ring-1 focus:ring-emerald-500"
                                                  />
                                                </div>
                                              </div>
                                            );
                                          })}
                                        </div>
                                      </div>
                                    )}
                                    
                                    {(exchange === "binance" || exchange === "bybit") && (
                                      <div className="flex justify-end">
                                        <button
                                          onClick={() => {
                                            const key = `${exchange}_spot`;
                                            setAdminOpenPairs({
                                              ...adminOpenPairs,
                                              [key]: !adminOpenPairs[key],
                                            });
                                          }}
                                          className="px-3 py-1.5 bg-zinc-700 hover:bg-zinc-600 text-white text-sm font-medium rounded-lg transition-colors"
                                        >
                                          {adminOpenPairs[`${exchange}_spot`] ? "Скрыть пары" : "Открыть дополнительные пары"}
                                        </button>
                                      </div>
                                    )}
                                  </div>
                                  
                                  {/* Futures секция */}
                                  <div className="bg-zinc-900 rounded-lg p-4 space-y-4">
                                    <div className="flex items-center justify-between">
                                      <div>
                                        <h3 className="text-white font-medium">Futures</h3>
                                        <p className="text-sm text-zinc-400">Все торговые пары</p>
                                      </div>
                                      <div
                                        className={`w-12 h-6 rounded-full transition-colors cursor-pointer ${
                                          settings.futures.enabled ? "bg-emerald-500" : "bg-zinc-600"
                                        }`}
                                        onClick={(e) => {
                                          e.stopPropagation();
                                          setAdminExchangeSettings({
                                            ...adminExchangeSettings,
                                            [exchange]: {
                                              ...settings,
                                              futures: { ...settings.futures, enabled: !settings.futures.enabled },
                                            },
                                          });
                                        }}
                                      >
                                        <div className={`w-5 h-5 bg-white rounded-full transition-transform mt-0.5 ${
                                          settings.futures.enabled ? "translate-x-6" : "translate-x-1"
                                        }`} />
                                      </div>
                                    </div>
                                    
                                    {!adminOpenPairs[`${exchange}_futures`] && (
                                      <div className="grid grid-cols-3 gap-3">
                                        <div>
                                          <label className="block text-xs text-zinc-400 mb-1">Дельта %</label>
                                          <input
                                            type="number"
                                            value={settings.futures.delta}
                                            onChange={(e) => {
                                              setAdminExchangeSettings({
                                                ...adminExchangeSettings,
                                                [exchange]: {
                                                  ...settings,
                                                  futures: { ...settings.futures, delta: e.target.value },
                                                },
                                              });
                                            }}
                                            className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                                          />
                                        </div>
                                        <div>
                                          <label className="block text-xs text-zinc-400 mb-1">Объём USDT</label>
                                          <input
                                            type="number"
                                            value={settings.futures.volume}
                                            onChange={(e) => {
                                              setAdminExchangeSettings({
                                                ...adminExchangeSettings,
                                                [exchange]: {
                                                  ...settings,
                                                  futures: { ...settings.futures, volume: e.target.value },
                                                },
                                              });
                                            }}
                                            className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                                          />
                                        </div>
                                        <div>
                                          <label className="block text-xs text-zinc-400 mb-1">Тень %</label>
                                          <input
                                            type="number"
                                            value={settings.futures.shadow}
                                            onChange={(e) => {
                                              setAdminExchangeSettings({
                                                ...adminExchangeSettings,
                                                [exchange]: {
                                                  ...settings,
                                                  futures: { ...settings.futures, shadow: e.target.value },
                                                },
                                              });
                                            }}
                                            className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                                          />
                                        </div>
                                      </div>
                                    )}
                                    
                                    {/* Дополнительные пары для Futures (если есть) */}
                                    {exchange === "binance" && adminOpenPairs[`${exchange}_futures`] && (
                                      <div className="bg-zinc-950 rounded-lg p-4 border border-zinc-700">
                                        <h4 className="text-sm font-medium text-white mb-4">Дополнительные пары для Futures</h4>
                                        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                                          {getPairsForExchange(exchange, "futures").map((pair) => {
                                            const pairKey = `${exchange}_futures_${pair}`;
                                            const savedPairData = adminPairSettings[pairKey];
                                            const futuresSettings = settings.futures;
                                            
                                            const pairData = savedPairData || {
                                              enabled: true,
                                              delta: futuresSettings.delta || "0",
                                              volume: futuresSettings.volume || "0",
                                              shadow: futuresSettings.shadow || "0"
                                            };
                                            
                                            return (
                                              <div key={pair} className="bg-zinc-800 rounded-lg p-3 space-y-2">
                                                <div className="flex items-center justify-between mb-2">
                                                  <div className="text-white font-medium text-sm">{pair}</div>
                                                  <div
                                                    className={`w-10 h-5 rounded-full transition-colors cursor-pointer ${
                                                      pairData.enabled ? "bg-emerald-500" : "bg-zinc-600"
                                                    }`}
                                                    onClick={() => {
                                                      setAdminPairSettings({
                                                        ...adminPairSettings,
                                                        [pairKey]: { ...pairData, enabled: !pairData.enabled },
                                                      });
                                                    }}
                                                  >
                                                    <div className={`w-4 h-4 bg-white rounded-full transition-transform mt-0.5 ${
                                                      pairData.enabled ? "translate-x-5" : "translate-x-1"
                                                    }`} />
                                                  </div>
                                                </div>
                                                <div>
                                                  <label className="block text-xs text-zinc-400 mb-1">Дельта %</label>
                                                  <input
                                                    type="number"
                                                    value={pairData.delta}
                                                    onChange={(e) => {
                                                      setAdminPairSettings({
                                                        ...adminPairSettings,
                                                        [pairKey]: { ...pairData, delta: e.target.value },
                                                      });
                                                    }}
                                                    className="w-full px-2 py-1 bg-zinc-900 border border-zinc-700 rounded text-white text-xs focus:outline-none focus:ring-1 focus:ring-emerald-500"
                                                  />
                                                </div>
                                                <div>
                                                  <label className="block text-xs text-zinc-400 mb-1">Объём USDT</label>
                                                  <input
                                                    type="number"
                                                    value={pairData.volume}
                                                    onChange={(e) => {
                                                      setAdminPairSettings({
                                                        ...adminPairSettings,
                                                        [pairKey]: { ...pairData, volume: e.target.value },
                                                      });
                                                    }}
                                                    className="w-full px-2 py-1 bg-zinc-900 border border-zinc-700 rounded text-white text-xs focus:outline-none focus:ring-1 focus:ring-emerald-500"
                                                  />
                                                </div>
                                                <div>
                                                  <label className="block text-xs text-zinc-400 mb-1">Тень %</label>
                                                  <input
                                                    type="number"
                                                    value={pairData.shadow}
                                                    onChange={(e) => {
                                                      setAdminPairSettings({
                                                        ...adminPairSettings,
                                                        [pairKey]: { ...pairData, shadow: e.target.value },
                                                      });
                                                    }}
                                                    className="w-full px-2 py-1 bg-zinc-900 border border-zinc-700 rounded text-white text-xs focus:outline-none focus:ring-1 focus:ring-emerald-500"
                                                  />
                                                </div>
                                              </div>
                                            );
                                          })}
                                        </div>
                                      </div>
                                    )}
                                    
                                    {exchange === "binance" && (
                                      <div className="flex justify-end">
                                        <button
                                          onClick={() => {
                                            const key = `${exchange}_futures`;
                                            setAdminOpenPairs({
                                              ...adminOpenPairs,
                                              [key]: !adminOpenPairs[key],
                                            });
                                          }}
                                          className="px-3 py-1.5 bg-zinc-700 hover:bg-zinc-600 text-white text-sm font-medium rounded-lg transition-colors"
                                        >
                                          {adminOpenPairs[`${exchange}_futures`] ? "Скрыть пары" : "Открыть дополнительные пары"}
                                        </button>
                                      </div>
                                    )}
                                  </div>
                                </div>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    </div>

                    {/* Пороги детектора */}
                    <div className="border-t border-zinc-700 pt-4">
                      <h3 className="text-lg font-semibold text-white mb-3">Пороги детектора</h3>
                      {(() => {
                        try {
                          const options = selectedUserSettings.options_json 
                            ? JSON.parse(selectedUserSettings.options_json) 
                            : {};
                          const thresholds = options.thresholds || { delta_pct: 1.0, volume_usdt: 10000.0, wick_pct: 50.0 };
                          return (
                              <div className="grid md:grid-cols-3 gap-4">
                                <div>
                                  <label className="block text-sm text-zinc-400 mb-1">Дельта %</label>
                                  <input
                                    type="number"
                                    step="0.1"
                                    value={thresholds.delta_pct || 0}
                                    onChange={(e) => {
                                      const newThresholds = { ...thresholds, delta_pct: Number(e.target.value) || 0 };
                                      const newOptions = { ...options, thresholds: newThresholds };
                                      setSelectedUserSettings({
                                        ...selectedUserSettings,
                                        options_json: JSON.stringify(newOptions),
                                      });
                                    }}
                                    className="w-full px-4 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                                  />
                                </div>
                                <div>
                                  <label className="block text-sm text-zinc-400 mb-1">Объём USDT</label>
                                  <input
                                    type="number"
                                    step="1000"
                                    value={thresholds.volume_usdt || 0}
                                    onChange={(e) => {
                                      const newThresholds = { ...thresholds, volume_usdt: Number(e.target.value) || 0 };
                                      const newOptions = { ...options, thresholds: newThresholds };
                                      setSelectedUserSettings({
                                        ...selectedUserSettings,
                                        options_json: JSON.stringify(newOptions),
                                      });
                                    }}
                                    className="w-full px-4 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                                  />
                                </div>
                                <div>
                                  <label className="block text-sm text-zinc-400 mb-1">Тень %</label>
                                  <input
                                    type="number"
                                    step="1"
                                    value={thresholds.wick_pct || 0}
                                    onChange={(e) => {
                                      const newThresholds = { ...thresholds, wick_pct: Number(e.target.value) || 0 };
                                      const newOptions = { ...options, thresholds: newThresholds };
                                      setSelectedUserSettings({
                                        ...selectedUserSettings,
                                        options_json: JSON.stringify(newOptions),
                                      });
                                    }}
                                    className="w-full px-4 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                                  />
                                </div>
                              </div>
                          );
                        } catch (e) {
                          return <p className="text-zinc-500 text-sm">Ошибка парсинга настроек</p>;
                        }
                      })()}
                      
                      {/* Кнопка для копирования значений во все биржи */}
                      <div className="mt-4">
                        <button
                          onClick={copyThresholdsToAllExchanges}
                          className="w-full px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-lg transition-colors"
                          title="Скопировать значения порогов (Дельта %, Объём USDT, Тень %) из общих фильтров во все биржи (Spot и Futures)"
                        >
                          Вставить значения во все биржи
                        </button>
                      </div>
                    </div>

                    {/* Чёрный список */}
                    <div className="border-t border-zinc-700 pt-4">
                      <h3 className="text-lg font-semibold text-white mb-3">Чёрный список</h3>
                      {(() => {
                        try {
                          const options = selectedUserSettings.options_json 
                            ? JSON.parse(selectedUserSettings.options_json) 
                            : {};
                          const blacklist = options.blacklist || [];
                          return blacklist.length > 0 ? (
                            <div className="flex flex-wrap gap-2">
                              {blacklist.map((symbol: string) => (
                                <span key={symbol} className="px-3 py-1 bg-red-900/30 text-red-400 rounded-lg text-sm">
                                  {symbol}
                                </span>
                              ))}
                            </div>
                          ) : (
                            <p className="text-zinc-500 text-sm">Чёрный список пуст</p>
                          );
                        } catch (e) {
                          return <p className="text-zinc-500 text-sm">Ошибка парсинга настроек</p>;
                        }
                      })()}
                    </div>

                    {/* Кнопка сохранения */}
                    <div className="border-t border-zinc-700 pt-4 mt-4">
                      <button
                        onClick={saveAdminUserSettings}
                        disabled={adminLoading}
                        className="w-full px-6 py-3 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed font-semibold"
                      >
                        {adminLoading ? "Сохранение..." : "Сохранить изменения"}
                      </button>
                    </div>
                  </div>
                </div>
              )}

              {/* Блок Логов */}
              <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6">
                <div className="flex items-center justify-between mb-4">
                  <h2 className="text-xl font-bold text-white">Логи ошибок</h2>
                  <div className="flex gap-2">
                    {isAdmin && (
                      <button
                        onClick={deleteAllErrors}
                        disabled={errorLogsLoading}
                        className="px-4 py-2 bg-red-500 text-white rounded-lg hover:bg-red-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed text-sm"
                        title="Удалить все логи ошибок"
                      >
                        Удалить все
                      </button>
                    )}
                    <button
                      onClick={fetchErrorLogs}
                      disabled={errorLogsLoading}
                      className="px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed text-sm"
                    >
                      {errorLogsLoading ? "Загрузка..." : "Обновить"}
                    </button>
                  </div>
                </div>

                {/* Фильтры */}
                <div className="grid md:grid-cols-4 gap-4 mb-4">
                  <div>
                    <label className="block text-sm text-zinc-400 mb-1">Биржа</label>
                    <select
                      value={errorLogsFilter.exchange || ""}
                      onChange={(e) =>
                        setErrorLogsFilter({
                          ...errorLogsFilter,
                          exchange: e.target.value || undefined,
                        })
                      }
                      className="w-full px-4 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                    >
                      <option value="">Все биржи</option>
                      <option value="binance">Binance</option>
                      <option value="bybit">Bybit</option>
                      <option value="bitget">Bitget</option>
                      <option value="gate">Gate.io</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-sm text-zinc-400 mb-1">Тип ошибки</label>
                    <select
                      value={errorLogsFilter.error_type || ""}
                      onChange={(e) =>
                        setErrorLogsFilter({
                          ...errorLogsFilter,
                          error_type: e.target.value || undefined,
                        })
                      }
                      className="w-full px-4 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                    >
                      <option value="">Все типы</option>
                      <option value="reconnect">Reconnect</option>
                      <option value="websocket_error">WebSocket Error</option>
                      <option value="critical">Critical</option>
                      <option value="connection_error">Connection Error</option>
                      <option value="telegram_error">Telegram Error</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-sm text-zinc-400 mb-1">Лимит записей</label>
                    <input
                      type="number"
                      min="10"
                      max="1000"
                      step="10"
                      value={errorLogsFilter.limit}
                      onChange={(e) =>
                        setErrorLogsFilter({
                          ...errorLogsFilter,
                          limit: parseInt(e.target.value) || 100,
                        })
                      }
                      className="w-full px-4 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                    />
                  </div>
                  <div className="flex items-end">
                    <button
                      onClick={() => {
                        setErrorLogsFilter({ limit: 100 });
                      }}
                      className="w-full px-4 py-2 bg-zinc-700 text-white rounded-lg hover:bg-zinc-600 transition-colors text-sm"
                    >
                      Сбросить фильтры
                    </button>
                  </div>
                </div>

                {/* Таблица логов */}
                <div className="overflow-x-auto">
                  {errorLogsLoading ? (
                    <div className="text-center py-8 text-zinc-400">Загрузка логов...</div>
                  ) : errorLogs.length === 0 ? (
                    <div className="text-center py-8 text-zinc-400">Логи отсутствуют</div>
                  ) : (
                    <div className="space-y-2 max-h-96 overflow-y-auto">
                      {errorLogs.map((error) => (
                        <div
                          key={error.id}
                          className="bg-zinc-800 border border-zinc-700 rounded-lg p-4 hover:bg-zinc-750 transition-colors"
                        >
                          <div className="flex items-start justify-between mb-2">
                            <div className="flex items-center gap-2 flex-wrap">
                              <span className="px-2 py-1 bg-red-900/30 text-red-400 rounded text-xs font-medium">
                                {error.error_type}
                              </span>
                              {error.exchange && (
                                <span className="px-2 py-1 bg-blue-900/30 text-blue-400 rounded text-xs">
                                  {error.exchange}
                                </span>
                              )}
                              {error.market && (
                                <span className="px-2 py-1 bg-purple-900/30 text-purple-400 rounded text-xs">
                                  {error.market}
                                </span>
                              )}
                              {error.symbol && (
                                <span className="px-2 py-1 bg-emerald-900/30 text-emerald-400 rounded text-xs">
                                  {error.symbol}
                                </span>
                              )}
                            </div>
                            <div className="flex items-center gap-2">
                              <span className="text-xs text-zinc-500">
                                {new Date(error.timestamp).toLocaleString("ru-RU")}
                              </span>
                              {isAdmin && (
                                <button
                                  onClick={() => deleteError(error.id)}
                                  className="px-2 py-1 bg-red-500/20 text-red-400 rounded text-xs hover:bg-red-500/30 transition-colors"
                                  title="Удалить этот лог"
                                >
                                  ✕
                                </button>
                              )}
                            </div>
                          </div>
                          <div className="text-sm text-white mb-2">{error.error_message}</div>
                          {error.connection_id && (
                            <div className="text-xs text-zinc-500 mb-1">
                              Connection ID: {error.connection_id}
                            </div>
                          )}
                          {error.stack_trace && (
                            <details className="mt-2">
                              <summary className="text-xs text-zinc-400 cursor-pointer hover:text-zinc-300">
                                Показать стек трейс
                              </summary>
                              <pre className="mt-2 p-2 bg-zinc-900 rounded text-xs text-zinc-300 overflow-x-auto">
                                {error.stack_trace}
                              </pre>
                            </details>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}



