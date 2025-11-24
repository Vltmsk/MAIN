"use client";

import { useEffect, useState, useRef } from "react";
import dynamic from "next/dynamic";
import ChatIdHelp from "@/components/ChatIdHelp";

// Динамический импорт EmojiPicker для избежания SSR проблем
const EmojiPicker = dynamic(() => import("emoji-picker-react"), { ssr: false });

// Типы
type ConditionalTemplate = {
  name?: string;
  description?: string;
  enabled?: boolean;
  useGlobalFilters?: boolean; // По умолчанию true, если отсутствует (обратная совместимость)
  conditions: Array<{
    type: "volume" | "delta" | "series" | "symbol" | "wick_pct" | "exchange_market" | "direction";
    value?: number;
    valueMin?: number;
    valueMax?: number | null;
    count?: number;
    timeWindowSeconds?: number;
    symbol?: string;
    exchange_market?: string; // Формат: "exchange_market" (например, "binance_spot", "bybit_futures")
    direction?: "up" | "down";
    // Старые поля для обратной совместимости (deprecated)
    exchange?: string;
    market?: "spot" | "futures" | "linear";
  }>;
  template: string;
  chatId?: string;
};

interface SettingsTabProps {
  userLogin: string;
}

export default function SettingsTab({ userLogin }: SettingsTabProps) {
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
    binance: false,
    bybit: false,
    bitget: false,
    gate: false,
    hyperliquid: false,
  });
  const [expandedExchanges, setExpandedExchanges] = useState<Record<string, boolean>>({});
  
  // Состояния для настроек Spot и Futures каждой биржи
  const [exchangeSettings, setExchangeSettings] = useState<Record<string, {
    spot: { enabled: boolean; delta: string; volume: string; shadow: string; sendChart?: boolean };
    futures: { enabled: boolean; delta: string; volume: string; shadow: string; sendChart?: boolean };
  }>>({
    binance: { spot: { enabled: false, delta: "", volume: "", shadow: "" }, futures: { enabled: false, delta: "", volume: "", shadow: "" } },
    bybit: { spot: { enabled: false, delta: "", volume: "", shadow: "" }, futures: { enabled: false, delta: "", volume: "", shadow: "" } },
    bitget: { spot: { enabled: false, delta: "", volume: "", shadow: "" }, futures: { enabled: false, delta: "", volume: "", shadow: "" } },
    gate: { spot: { enabled: false, delta: "", volume: "", shadow: "" }, futures: { enabled: false, delta: "", volume: "", shadow: "" } },
    hyperliquid: { spot: { enabled: false, delta: "", volume: "", shadow: "" }, futures: { enabled: false, delta: "", volume: "", shadow: "" } },
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

  // Обратный маппинг
  const reversePlaceholderMap: Record<string, string> = Object.fromEntries(
    Object.entries(placeholderMap).map(([key, value]) => [value, key])
  );

  // Состояние для шаблона сообщения
  const [messageTemplate, setMessageTemplate] = useState<string>(`🚨 <b>НАЙДЕНА СТРЕЛА!</b> [[Направление]]

<b>[[Биржа и тип рынка]]</b>
💰 <b>[[Торговая пара]]</b>

📊 <b>Метрики:</b>
• Изменение: <b>[[Дельта стрелы]]</b> [[Направление]]
• Объём: <b>[[Объём стрелы]] USDT</b>
• Тень: <b>[[Тень свечи]]</b>

⏰ <b>[[Время детекта]]</b>`);
  
  // Состояние для условных шаблонов
  const [conditionalTemplates, setConditionalTemplates] = useState<ConditionalTemplate[]>([]);
  const [isConditionalTemplatesExpanded, setIsConditionalTemplatesExpanded] = useState(false);
  
  // Состояние для ошибок валидации стратегий
  const [strategyValidationErrors, setStrategyValidationErrors] = useState<Record<number, {
    hasError: boolean;
    missingFields: string[];
    message: string;
  }>>({});
  
  // Состояние для настройки отправки графиков
  const [chartSettings, setChartSettings] = useState<Record<string, boolean>>({});
  const [isChartSettingsExpanded, setIsChartSettingsExpanded] = useState(false);
  
  // Состояние для управления видимостью блока формата отправки детекта
  const isUserEditingRef = useRef(false);
  // Отдельный флаг для редактирования условных шаблонов, чтобы не сбивать курсор
  const isConditionalUserEditingRef = useRef(false);
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
    conditional: number | null;
    position?: { x: number; y: number };
  }>({ main: false, conditional: null });
  
  // Refs для кнопок emoji picker
  const emojiButtonRef = useRef<HTMLButtonElement>(null);
  const conditionalEmojiButtonRefs = useRef<Record<number, HTMLButtonElement | null>>({});
  
  // Состояния для дополнительных пар
  const [openPairs, setOpenPairs] = useState<Record<string, boolean>>({});
  const [pairSettings, setPairSettings] = useState<Record<string, { enabled: boolean; delta: string; volume: string; shadow: string; sendChart?: boolean }>>({});

  // Состояния для таблицы "Активные фильтры"
  const [editingCell, setEditingCell] = useState<{
    rowId: string;
    field: "delta" | "volume" | "shadow";
    value: string;
    previousValue: string;
  } | null>(null);
  const [highlightedRowId, setHighlightedRowId] = useState<string | null>(null);
  const highlightTimeoutRef = useRef<number | null>(null);
  
  // Состояние для активной подтемы настроек
  const [activeSubTab, setActiveSubTab] = useState<"telegram" | "format" | "spikes" | "blacklist" | "strategies">("spikes");

  // Храним последнюю активную подтему настроек в localStorage (на пользователя)
  useEffect(() => {
    if (typeof window === "undefined") return;

    const storageKey = `settings_active_subtab_${userLogin || "default"}`;
    const stored = window.localStorage.getItem(storageKey) as
      | "telegram"
      | "format"
      | "spikes"
      | "blacklist"
      | "strategies"
      | null;

    if (stored) {
      setActiveSubTab(stored);
    }
  }, [userLogin]);

  useEffect(() => {
    if (typeof window === "undefined") return;

    const storageKey = `settings_active_subtab_${userLogin || "default"}`;
    window.localStorage.setItem(storageKey, activeSubTab);
  }, [activeSubTab, userLogin]);

  // Автоматическое скрытие уведомления через 3 секунды
  useEffect(() => {
    if (saveMessage) {
      const timer = setTimeout(() => {
        setSaveMessage(null);
      }, 3000); // 3 секунды

      return () => clearTimeout(timer);
    }
  }, [saveMessage]);

  const formatNumberCompact = (value: string): string => {
    if (!value) return "0";
    const num = Number(value);
    if (Number.isNaN(num)) return value;
    return new Intl.NumberFormat("ru-RU").format(num);
  };

  // Функции для преобразования шаблонов
  const convertToTechnicalKeys = (template: string): string => {
    let result = template;
    Object.entries(placeholderMap).forEach(([friendly, technical]) => {
      result = result.replace(new RegExp(friendly.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'g'), technical);
    });
    return result;
  };

  const convertToFriendlyNames = (template: string): string => {
    let result = template;
    Object.entries(reversePlaceholderMap).forEach(([technical, friendly]) => {
      result = result.replace(new RegExp(technical.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'g'), friendly);
    });
    return result;
  };

  // Функция для генерации превью сообщения с примерами значений
  const generateMessagePreview = (template: string): string => {
    if (!template || !template.trim()) {
      return "";
    }

    // Примеры значений для превью
    const exampleValues: Record<string, string> = {
      "{delta_formatted}": "5.23%",
      "{volume_formatted}": "1.5K$",
      "{wick_formatted}": "45.2%",
      "{timestamp}": "1699123456789",
      "{direction}": "⬆️",
      "{exchange_market}": "BINANCE | SPOT",
      "{exchange}": "BINANCE",
      "{symbol}": "BTC-USDT",
      "{market}": "SPOT",
      "{time}": "2024-01-15 14:30:25",
      // Friendly names (для поддержки вставок из редактора)
      "[[Дельта стрелы]]": "5.23%",
      "[[Объём стрелы]]": "1.5K$",
      "[[Тень свечи]]": "45.2%",
      "[[Временная метка]]": "1699123456789",
      "[[Направление]]": "⬆️",
      "[[Биржа и тип рынка]]": "BINANCE | SPOT",
      "[[Торговая пара]]": "BTC-USDT",
      "[[Время детекта]]": "2024-01-15 14:30:25",
    };

    // Конвертируем friendly names в technical keys для замены
    let preview = convertToTechnicalKeys(template);

    // Заменяем все плейсхолдеры на примеры значений
    // Важно: сначала заменяем технические ключи, затем friendly names
    Object.entries(exampleValues).forEach(([placeholder, value]) => {
      // Экранируем специальные символы для регулярного выражения
      const escapedPlaceholder = placeholder.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      // Заменяем все вхождения плейсхолдера на пример значения
      preview = preview.replace(new RegExp(escapedPlaceholder, 'g'), value);
    });

    // Очищаем лишние пробелы и переносы строк
    preview = preview.trim();

    return preview;
  };

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
        case "exchange_market":
          if (condition.exchange_market) {
            const [exchange, market] = condition.exchange_market.split("_");
            const exchangeNames: Record<string, string> = {
              binance: "Binance",
              gate: "Gate",
              bitget: "Bitget",
              bybit: "Bybit",
              hyperliquid: "Hyperliquid",
            };
            const marketNames: Record<string, string> = {
              spot: "Spot",
              futures: "Futures",
              linear: "Linear",
            };
            const exchangeName = exchangeNames[exchange] || exchange;
            const marketName = marketNames[market] || market;
            parts.push(`${exchangeName} ${marketName}`);
          } else if (condition.exchange && condition.market) {
            // Обратная совместимость со старым форматом
            const exchangeNames: Record<string, string> = {
              binance: "Binance",
              gate: "Gate",
              bitget: "Bitget",
              bybit: "Bybit",
              hyperliquid: "Hyperliquid",
            };
            const marketNames: Record<string, string> = {
              spot: "Spot",
              futures: "Futures",
              linear: "Linear",
            };
            const exchangeName = exchangeNames[condition.exchange] || condition.exchange;
            const marketName = marketNames[condition.market] || condition.market;
            parts.push(`${exchangeName} ${marketName}`);
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

  // Валидация
  const validateChatId = (chatId: string): string => {
    if (!chatId.trim()) {
      return "";
    }
    const chatIdRegex = /^-?\d{8,20}$/;
    if (!chatIdRegex.test(chatId)) {
      return "Неверный формат Chat ID. Chat ID должен быть числом от 8 до 20 цифр (например: 123456789 для личных чатов или -1001234567890 для групп/каналов). Разверните инструкцию ниже, чтобы узнать, как получить Chat ID.";
    }
    return "";
  };

  const validateBotToken = (token: string): string => {
    if (!token.trim()) {
      return "";
    }
    const botTokenRegex = /^\d{8,12}:[A-Za-z0-9_-]{30,40}$/;
    if (!botTokenRegex.test(token)) {
      return "Неверный формат Bot Token. Формат: число:буквы (например: 1234567890:ABCdefGHIjkIMNOpqrsTUVwxyz)";
    }
    return "";
  };

  // Функции для работы с парами
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
    if (exchange === "bybit" && market === "futures") {
      return ["USDT"];
    }
    if (exchange === "bitget" && market === "spot") {
      return ["USDT"];
    }
    if (exchange === "bitget" && market === "futures") {
      return ["USDT"];
    }
    if (exchange === "gate" && market === "spot") {
      return ["USDT"];
    }
    if (exchange === "gate" && market === "futures") {
      return ["USDT"];
    }
    if (exchange === "hyperliquid" && market === "spot") {
      return ["USDC"];
    }
    if (exchange === "hyperliquid" && market === "futures") {
      return ["USDC"];
    }
    return [];
  };

  const getQuoteCurrencyForExchange = (exchange: string, market: "spot" | "futures"): string | null => {
    const pairs = getPairsForExchange(exchange, market);
    if (pairs.length === 1) {
      return pairs[0];
    }
    return null;
  };

  const shouldShowPairsImmediately = (exchange: string, market: "spot" | "futures"): boolean => {
    return (exchange === "binance" && (market === "spot" || market === "futures")) ||
           (exchange === "bybit" && market === "spot");
  };

  const areAllChartsEnabled = (): boolean => {
    const exchanges = ["binance", "bybit", "bitget", "gate", "hyperliquid"];
    
    for (const exchange of exchanges) {
      const spotCurrencies = getPairsForExchange(exchange, "spot");
      const futuresCurrencies = getPairsForExchange(exchange, "futures");
      
      // Проверяем все валюты в Spot
      for (const currency of spotCurrencies) {
        const currencyKey = `${exchange}_spot_${currency}`;
        if (chartSettings[currencyKey] !== true) {
          return false;
        }
      }
      
      // Проверяем все валюты в Futures
      for (const currency of futuresCurrencies) {
        const currencyKey = `${exchange}_futures_${currency}`;
        if (chartSettings[currencyKey] !== true) {
          return false;
        }
      }
    }
    
    return true;
  };

  const toggleAllCharts = () => {
    const exchanges = ["binance", "bybit", "bitget", "gate", "hyperliquid"];
    const allEnabled = areAllChartsEnabled();
    const newValue = !allEnabled;
    
    const newSettings: Record<string, boolean> = {};
    
    for (const exchange of exchanges) {
      newSettings[`${exchange}_spot`] = newValue;
      newSettings[`${exchange}_futures`] = newValue;
      
      const spotPairs = getPairsForExchange(exchange, "spot");
      const futuresPairs = getPairsForExchange(exchange, "futures");
      
      for (const pair of spotPairs) {
        newSettings[`${exchange}_spot_${pair}`] = newValue;
      }
      
      for (const pair of futuresPairs) {
        newSettings[`${exchange}_futures_${pair}`] = newValue;
      }
    }
    
    setChartSettings({
      ...chartSettings,
      ...newSettings
    });
  };

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
  
  const insertEmoji = (emojiData: { emoji: string }, editorId: string, isConditional: boolean = false) => {
    const editor = document.getElementById(editorId) as HTMLElement;
    if (!editor) return;
    
    editor.focus();
    
    const selection = window.getSelection();
    if (selection && selection.rangeCount > 0) {
      const range = selection.getRangeAt(0);
      range.deleteContents();
      
      const textNode = document.createTextNode(emojiData.emoji);
      range.insertNode(textNode);
      
      const newRange = document.createRange();
      newRange.setStartAfter(textNode);
      newRange.collapse(true);
      selection.removeAllRanges();
      selection.addRange(newRange);
      
      const inputEvent = new Event('input', { bubbles: true });
      editor.dispatchEvent(inputEvent);
    } else {
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

  const handleContextMenu = (e: React.MouseEvent<HTMLElement>) => {
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

  const exampleTemplate = `🚨 <b>НАЙДЕНА СТРЕЛА!</b> [[Направление]]

<b>[[Биржа и тип рынка]]</b>
💰 <b>[[Торговая пара]]</b>

📊 <b>Метрики:</b>
• Изменение: <b>[[Дельта стрелы]]</b> [[Направление]]
• Объём: <b>[[Объём стрелы]] USDT</b>
• Тень: <b>[[Тень свечи]]</b>

⏰ <b>[[Время детекта]]</b>`;

  const isTemplateEmpty = () => {
    const editor = document.getElementById("messageTemplate") as HTMLElement;
    if (!editor) return true;
    const text = editor.textContent || editor.innerText || '';
    return text.trim().length === 0 || editor.innerHTML.trim() === '';
  };

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

  const extractTextFromEditor = (): string => {
    const editor = document.getElementById("messageTemplate") as HTMLElement;
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
  };

  // Функция валидации стратегий
  const validateStrategies = (): boolean => {
    const errors: Record<number, {
      hasError: boolean;
      missingFields: string[];
      message: string;
    }> = {};
    
    let hasErrors = false;
    
    conditionalTemplates.forEach((template, index) => {
      // Проверяем только если стратегия включена и useGlobalFilters = false
      if (template.enabled !== false && template.useGlobalFilters === false) {
        const missingFields: string[] = [];
        
        // Проверяем наличие базовых фильтров
        const hasDelta = template.conditions.some(c => c.type === "delta" && c.valueMin !== undefined);
        const hasVolume = template.conditions.some(c => c.type === "volume" && c.value !== undefined);
        const hasWickPct = template.conditions.some(c => c.type === "wick_pct" && c.valueMin !== undefined);
        
        if (!hasDelta) {
          missingFields.push("Дельта");
        }
        if (!hasVolume) {
          missingFields.push("Объём");
        }
        if (!hasWickPct) {
          missingFields.push("Тень");
        }
        
        if (missingFields.length > 0) {
          hasErrors = true;
          errors[index] = {
            hasError: true,
            missingFields,
            message: `Стратегия "${template.name || `Стратегия #${index + 1}`}" не может работать без базовых фильтров. Пожалуйста, либо включите 'Использовать мои фильтры из глобальных настроек', либо укажите значения для ${missingFields.join(", ")} в условиях стратегии.`
          };
        }
      }
    });
    
    setStrategyValidationErrors(errors);
    return !hasErrors;
  };

  // Сохранение всех настроек
  const saveAllSettings = async (): Promise<boolean> => {
    if (!userLogin) return false;
    
    // Валидация стратегий перед сохранением
    if (!validateStrategies()) {
      setSaveMessage({
        type: "error",
        text: "Не удалось сохранить: обнаружены ошибки в стратегиях. Пожалуйста, исправьте их перед сохранением."
      });
      setTimeout(() => setSaveMessage(null), 5000);
      return false;
    }
    
    const extractedText = extractTextFromEditor();
    
    const pairSettingsWithCharts: Record<string, { enabled: boolean; delta: string; volume: string; shadow: string; sendChart?: boolean }> = { ...pairSettings };
    const exchangeSettingsWithCharts: Record<string, {
      spot: { enabled: boolean; delta: string; volume: string; shadow: string; sendChart?: boolean };
      futures: { enabled: boolean; delta: string; volume: string; shadow: string; sendChart?: boolean };
    }> = { ...exchangeSettings };
    
    Object.keys(chartSettings).forEach((key) => {
      if (pairSettings[key]) {
        // Ключ уже существует в pairSettings - обновляем его
        const currentSettings = pairSettings[key];
        const newSettings: { enabled: boolean; delta: string; volume: string; shadow: string; sendChart?: boolean } = {
          enabled: currentSettings.enabled,
          delta: currentSettings.delta,
          volume: currentSettings.volume,
          shadow: currentSettings.shadow,
          sendChart: chartSettings[key]
        };
        pairSettingsWithCharts[key] = newSettings;
      } else {
        const parts = key.split('_');
        if (parts.length === 3) {
          // Формат: exchange_market_pair (например, binance_spot_BTC)
          const [exchange, market, pair] = parts;
          if (market === "spot" || market === "futures") {
            // Создаем новую запись в pairSettings, если её нет
            const existingSettings = (key in pairSettings ? pairSettings[key] : undefined) as { enabled: boolean; delta: string; volume: string; shadow: string; sendChart?: boolean } | undefined;
            const newSettings: { enabled: boolean; delta: string; volume: string; shadow: string; sendChart?: boolean } = {
              enabled: existingSettings?.enabled || false,
              delta: existingSettings?.delta || "",
              volume: existingSettings?.volume || "",
              shadow: existingSettings?.shadow || "",
              sendChart: chartSettings[key]
            };
            pairSettingsWithCharts[key] = newSettings;
          }
        } else if (parts.length === 2) {
          // Формат: exchange_market (например, binance_spot)
          const [exchange, market] = parts;
          if (!exchangeSettingsWithCharts[exchange]) {
            exchangeSettingsWithCharts[exchange] = {
              spot: { enabled: false, delta: "", volume: "", shadow: "", sendChart: undefined },
              futures: { enabled: false, delta: "", volume: "", shadow: "", sendChart: undefined }
            };
          }
          if (market === "spot" || market === "futures") {
            const currentMarketSettings = exchangeSettingsWithCharts[exchange][market];
            const newMarketSettings: { enabled: boolean; delta: string; volume: string; shadow: string; sendChart?: boolean } = {
              enabled: currentMarketSettings.enabled,
              delta: currentMarketSettings.delta,
              volume: currentMarketSettings.volume,
              shadow: currentMarketSettings.shadow,
              sendChart: chartSettings[key]
            };
            exchangeSettingsWithCharts[exchange][market] = newMarketSettings;
          }
        }
      }
    });
    
    const options = {
      exchanges: exchangeFilters,
      exchangeSettings: exchangeSettingsWithCharts,
      pairSettings: pairSettingsWithCharts,
      blacklist,
      messageTemplate: convertToTechnicalKeys(extractedText),
      conditionalTemplates: conditionalTemplates.map(template => {
        const templateData: any = {
          conditions: template.conditions.map(condition => {
            const baseCondition: any = {
              type: condition.type,
              operator: ">=",
            };
            
            if (condition.type === "series") {
              baseCondition.count = condition.count || 2;
              baseCondition.timeWindowSeconds = condition.timeWindowSeconds || 300;
            } else if (condition.type === "delta" || condition.type === "wick_pct") {
              if (condition.valueMin !== undefined) {
                baseCondition.valueMin = condition.valueMin;
              }
              if (condition.valueMax !== undefined || condition.valueMax === null) {
                baseCondition.valueMax = condition.valueMax;
              }
            } else if (condition.type === "symbol") {
              if (condition.symbol) {
                baseCondition.value = condition.symbol.toUpperCase().trim();
                baseCondition.symbol = condition.symbol.toUpperCase().trim();
              }
            } else if (condition.type === "exchange_market") {
              if (condition.exchange_market) {
                baseCondition.exchange_market = condition.exchange_market.toLowerCase();
              } else if (condition.exchange && condition.market) {
                // Обратная совместимость: мигрируем старый формат
                const market = condition.market === "linear" ? "futures" : condition.market;
                baseCondition.exchange_market = `${condition.exchange.toLowerCase()}_${market.toLowerCase()}`;
              }
            } else if (condition.type === "direction") {
              if (condition.direction) {
                baseCondition.direction = condition.direction.toLowerCase();
              }
            } else {
              baseCondition.value = condition.value || 0;
            }
            
            return baseCondition;
          }),
          template: convertToTechnicalKeys(template.template),
        };
        
        if (template.name) {
          templateData.name = template.name;
        }
        
        if (template.enabled === false) {
          templateData.enabled = false;
        }
        
        // Сохраняем useGlobalFilters (по умолчанию true, если не указано)
        templateData.useGlobalFilters = template.useGlobalFilters !== undefined ? template.useGlobalFilters : true;
        
        if (template.chatId) {
          templateData.chatId = template.chatId;
        }
        
        return templateData;
      }),
      timezone: timezone || "UTC",
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
        const hasTelegram = !!(telegramBotToken && telegramChatId);
        if (hasTelegram) {
          setIsTelegramConfigured(true);
          setIsEditingTelegram(false);
        }
        
        setIsMessageFormatExpanded(false);
        
        setSaveMessage({
          type: "success",
          text: "Настройки успешно сохранены! Изменения применятся в течение 1 минуты (время обновления кэша системы)."
        });
        return true;
      } else {
        const error = await res.json();
        setSaveMessage({ type: "error", text: error.detail || "Ошибка сохранения настроек" });
        return false;
      }
    } catch (err) {
      setSaveMessage({ type: "error", text: "Ошибка при сохранении настроек" });
      console.error(err);
      return false;
    }
  };

  // Загрузка настроек пользователя
  const fetchUserSettings = async () => {
    if (!userLogin) {
      console.log("[SettingsTab] fetchUserSettings: userLogin is empty");
      return;
    }
    
    console.log(`[SettingsTab] fetchUserSettings: Loading settings for user "${userLogin}"`);
    
    try {
      const url = `/api/users/${encodeURIComponent(userLogin)}`;
      console.log(`[SettingsTab] fetchUserSettings: Fetching from ${url}`);
      
      const res = await fetch(url);
      console.log(`[SettingsTab] fetchUserSettings: Response status: ${res.status}`);
      
      if (res.ok) {
        const userData = await res.json();
        console.log(`[SettingsTab] fetchUserSettings: User data received:`, {
          user: userData.user,
          has_tg_token: !!userData.tg_token,
          has_chat_id: !!userData.chat_id,
          has_options_json: !!userData.options_json
        });
        
        const tgToken = (userData.tg_token || "").trim();
        const chatId = (userData.chat_id || "").trim();
        setTelegramBotToken(tgToken);
        setTelegramChatId(chatId);
        
        const hasTelegram = !!(tgToken && chatId);
        setIsTelegramConfigured(hasTelegram);
        setIsEditingTelegram(!hasTelegram);
        
        if (hasTelegram) {
          setTelegramChatIdError("");
          setTelegramBotTokenError("");
        }
        
        try {
          const optionsJson = userData.options_json || "{}";
          const options = typeof optionsJson === "string" ? JSON.parse(optionsJson) : optionsJson;
          
          if (options.messageTemplate && options.messageTemplate.trim() !== '') {
            console.log("Загружен шаблон из БД (технический):", options.messageTemplate);
            let template = options.messageTemplate;
            
            if (template.includes("{exchange}") && template.includes("{market}")) {
              template = template.replace(/\{exchange\}\s*\|\s*\{market\}/g, "{exchange_market}");
              template = template.replace(/\{exchange\}\s*\{market\}/g, "{exchange_market}");
              template = template.replace(/\{market\}\s*\|\s*\{exchange\}/g, "{exchange_market}");
              template = template.replace(/\{market\}\s*\{exchange\}/g, "{exchange_market}");
            }
            
            let friendlyTemplate = convertToFriendlyNames(template);
            friendlyTemplate = friendlyTemplate.replace(/\[\[Объём торгов\]\]/g, "[[Объём стрелы]]");
            
            if (friendlyTemplate.includes("[[Биржа]]") && friendlyTemplate.includes("[[Тип рынка]]")) {
              friendlyTemplate = friendlyTemplate.replace(/\[\[Биржа\]\]\s*\|\s*\[\[Тип рынка\]\]/g, "[[Биржа и тип рынка]]");
              friendlyTemplate = friendlyTemplate.replace(/\[\[Биржа\]\]\s*\[\[Тип рынка\]\]/g, "[[Биржа и тип рынка]]");
              friendlyTemplate = friendlyTemplate.replace(/\[\[Тип рынка\]\]\s*\|\s*\[\[Биржа\]\]/g, "[[Биржа и тип рынка]]");
              friendlyTemplate = friendlyTemplate.replace(/\[\[Тип рынка\]\]\s*\[\[Биржа\]\]/g, "[[Биржа и тип рынка]]");
            }
            
            console.log("Шаблон после преобразования (понятный):", friendlyTemplate);
            setMessageTemplate(friendlyTemplate);
          } else {
            console.log("Шаблон не найден в БД, используем дефолтный");
            setMessageTemplate(exampleTemplate);
          }
          
          if (options.exchanges && typeof options.exchanges === "object") {
            setExchangeFilters({
              binance: options.exchanges.binance === true,
              bybit: options.exchanges.bybit === true,
              bitget: options.exchanges.bitget === true,
              gate: options.exchanges.gate === true,
              hyperliquid: options.exchanges.hyperliquid === true,
            });
          } else {
            setExchangeFilters({
              binance: false,
              bybit: false,
              bitget: false,
              gate: false,
              hyperliquid: false,
            });
          }
          
          if (options.exchangeSettings && typeof options.exchangeSettings === "object") {
            setExchangeSettings((prevSettings) => {
              const merged = { ...prevSettings };
              Object.keys(options.exchangeSettings).forEach((exchange) => {
                if (merged[exchange]) {
                  merged[exchange] = {
                    spot: {
                      enabled: options.exchangeSettings[exchange].spot?.enabled === true,
                      delta: options.exchangeSettings[exchange].spot?.delta || "",
                      volume: options.exchangeSettings[exchange].spot?.volume || "",
                      shadow: options.exchangeSettings[exchange].spot?.shadow || "",
                    },
                    futures: {
                      enabled: options.exchangeSettings[exchange].futures?.enabled === true,
                      delta: options.exchangeSettings[exchange].futures?.delta || "",
                      volume: options.exchangeSettings[exchange].futures?.volume || "",
                      shadow: options.exchangeSettings[exchange].futures?.shadow || "",
                    },
                  };
                } else {
                  merged[exchange] = {
                    spot: {
                      enabled: options.exchangeSettings[exchange].spot?.enabled === true,
                      delta: options.exchangeSettings[exchange].spot?.delta || "",
                      volume: options.exchangeSettings[exchange].spot?.volume || "",
                      shadow: options.exchangeSettings[exchange].spot?.shadow || "",
                    },
                    futures: {
                      enabled: options.exchangeSettings[exchange].futures?.enabled === true,
                      delta: options.exchangeSettings[exchange].futures?.delta || "",
                      volume: options.exchangeSettings[exchange].futures?.volume || "",
                      shadow: options.exchangeSettings[exchange].futures?.shadow || "",
                    },
                  };
                }
              });
              return merged;
            });
          }
          
          if (options.pairSettings && typeof options.pairSettings === "object") {
            const migratedPairSettings: Record<string, { enabled: boolean; delta: string; volume: string; shadow: string }> = {};
            Object.entries(options.pairSettings).forEach(([key, value]: [string, any]) => {
              if (value && typeof value === 'object' && !('enabled' in value)) {
                migratedPairSettings[key] = {
                  enabled: false,
                  delta: value.delta || "",
                  volume: value.volume || "",
                  shadow: value.shadow || ""
                };
              } else {
                migratedPairSettings[key] = {
                  enabled: value?.enabled === true,
                  delta: value?.delta || "",
                  volume: value?.volume || "",
                  shadow: value?.shadow || ""
                };
              }
            });
            setPairSettings(migratedPairSettings);
          }
          
          if (options.blacklist) {
            setBlacklist(options.blacklist || []);
          }
          
          if (options.conditionalTemplates && Array.isArray(options.conditionalTemplates)) {
            const templatesWithFriendlyNames = options.conditionalTemplates.map((template: any) => {
              let conditions = [];
              if (template.conditions && Array.isArray(template.conditions)) {
                conditions = template.conditions.map((cond: any) => {
                  const condType = cond.type === "wick" ? "delta" : (cond.type || "volume");
                  if (condType === "series") {
                    return {
                      type: "series",
                      count: cond.count || 2,
                      timeWindowSeconds: cond.timeWindowSeconds || 300,
                    };
                  } else if (condType === "delta" || condType === "wick_pct") {
                    if (cond.valueMin !== undefined || cond.valueMax !== undefined) {
                      return {
                        type: condType,
                        valueMin: cond.valueMin !== undefined ? cond.valueMin : 0,
                        valueMax: cond.valueMax !== undefined ? cond.valueMax : null,
                      };
                    } else {
                      return {
                        type: condType,
                        valueMin: cond.value !== undefined ? cond.value : 0,
                        valueMax: null,
                      };
                    }
                  } else if (condType === "symbol") {
                    return {
                      type: "symbol",
                      symbol: (cond.symbol || cond.value || "").toUpperCase().trim(),
                    };
                  } else if (condType === "exchange_market") {
                    // Новый формат: объединенное условие
                    if (cond.exchange_market) {
                      return {
                        type: "exchange_market",
                        exchange_market: cond.exchange_market.toLowerCase(),
                      };
                    } else {
                      // Обратная совместимость: мигрируем старый формат из полей exchange и market
                      const exchange = (cond.exchange || "binance").toLowerCase();
                      const market = (cond.market || "spot").toLowerCase();
                      const marketNormalized = market === "linear" ? "futures" : market;
                      return {
                        type: "exchange_market",
                        exchange_market: `${exchange}_${marketNormalized}`,
                      };
                    }
                  } else if (condType === "exchange") {
                    // Миграция старого условия exchange в новый формат (используем spot по умолчанию)
                    const exchange = (cond.exchange || "binance").toLowerCase();
                    return {
                      type: "exchange_market",
                      exchange_market: `${exchange}_spot`,
                    };
                  } else if (condType === "market") {
                    // Миграция старого условия market в новый формат (используем binance по умолчанию)
                    const market = (cond.market || "spot").toLowerCase();
                    const marketNormalized = market === "linear" ? "futures" : market;
                    return {
                      type: "exchange_market",
                      exchange_market: `binance_${marketNormalized}`,
                    };
                  } else if (condType === "direction") {
                    return {
                      type: "direction",
                      direction: (cond.direction || "up").toLowerCase() as "up" | "down",
                    };
                  } else {
                    return {
                      type: condType,
                      value: cond.value || 0,
                    };
                  }
                });
              } else if (template.condition) {
                const condType = template.condition.type === "wick" ? "delta" : (template.condition.type || "volume");
                if (condType === "delta") {
                  conditions = [{
                    type: "delta",
                    valueMin: template.condition.value !== undefined ? template.condition.value : 0,
                    valueMax: null,
                  }];
                } else {
                  conditions = [{
                    type: condType,
                    value: template.condition.value || 0,
                  }];
                }
              } else {
                conditions = [{ type: "volume", value: 0 }];
              }
              
              return {
                name: template.name || undefined,
                enabled: template.enabled !== undefined ? template.enabled : true,
                useGlobalFilters: template.useGlobalFilters !== undefined ? template.useGlobalFilters : true, // Обратная совместимость: по умолчанию true
                conditions,
                template: convertToFriendlyNames(template.template || ""),
                chatId: template.chatId || undefined,
              };
            });
            setConditionalTemplates(templatesWithFriendlyNames);
          } else {
            setConditionalTemplates([]);
          }
          
          const chartSettingsMap: Record<string, boolean> = {};
          
          if (options.pairSettings && typeof options.pairSettings === "object") {
            Object.entries(options.pairSettings).forEach(([key, value]: [string, any]) => {
              if (value && typeof value === 'object' && 'sendChart' in value) {
                chartSettingsMap[key] = value.sendChart === true;
              }
            });
          }
          
          if (options.exchangeSettings && typeof options.exchangeSettings === "object") {
            Object.keys(options.exchangeSettings).forEach((exchange) => {
              const exchangeConfig = options.exchangeSettings[exchange];
              if (exchangeConfig && typeof exchangeConfig === "object") {
                ["spot", "futures"].forEach((market) => {
                  const marketConfig = exchangeConfig[market];
                  if (marketConfig && typeof marketConfig === "object" && 'sendChart' in marketConfig) {
                    const key = `${exchange}_${market}`;
                    chartSettingsMap[key] = marketConfig.sendChart === true;
                  }
                });
              }
            });
          }
          
          setChartSettings(chartSettingsMap);
          
          if (options.timezone && typeof options.timezone === "string") {
            setTimezone(options.timezone);
          } else {
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
          setExchangeFilters({
            binance: false,
            bybit: false,
            bitget: false,
            gate: false,
            hyperliquid: false,
          });
        }
      } else if (res.status === 404) {
        console.log(`Пользователь "${userLogin}" не найден в БД. Будет создан при сохранении настроек.`);
      } else {
        const errorText = await res.text().catch(() => "Unknown error");
        console.error(`Ошибка загрузки настроек пользователя ${userLogin}:`, res.status, errorText);
      }
    } catch (err) {
      console.error("Ошибка загрузки настроек пользователя:", err);
    }
  };

  // Загрузка настроек при монтировании компонента
  useEffect(() => {
    if (userLogin) {
      fetchUserSettings();
    }
  }, [userLogin]);

  // Инициализация редактора при загрузке шаблона
  useEffect(() => {
    const initEditor = () => {
      const editor = document.getElementById("messageTemplate") as HTMLElement;
      if (!editor) return;
      
      if (!isUserEditingRef.current) {
        const html = convertTemplateToHTML(convertToFriendlyNames(messageTemplate));
        if (editor.innerHTML !== html) {
          editor.innerHTML = html;
        }
      }
    };
    
    setTimeout(initEditor, 100);
    setTimeout(initEditor, 500);
  }, [messageTemplate, isMessageFormatExpanded]);

  // Инициализация редакторов стратегий
  useEffect(() => {
    if (activeSubTab === "strategies") {
      const timer = setTimeout(() => {
        // Не трогаем содержимое, пока пользователь редактирует, чтобы не сбивать курсор
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
    }
  }, [activeSubTab, conditionalTemplates]);
  
  return (
    <div className="mb-6 md:mb-8">
      {/* Центральный контейнер с ограничением ширины */}
      <div className="max-w-[1400px] mx-auto px-6 md:px-8">
        {/* Заголовок страницы */}
        <div className="mb-8">
          <h1 className="text-2xl md:text-3xl font-bold text-white mb-2">Настройки</h1>
          <p className="text-sm md:text-base text-zinc-400 max-w-2xl">
            Управление профилями, фильтрами и интеграциями
          </p>
        </div>
        
        {/* Переключатель подтем */}
        <div className="mb-6">
          <div className="flex flex-wrap gap-3 bg-zinc-900 border border-zinc-800 rounded-xl p-2">
            <button
              onClick={() => setActiveSubTab("spikes")}
              className={`flex-1 min-w-[200px] px-6 py-3 rounded-lg font-medium smooth-transition ripple ${
                activeSubTab === "spikes"
                  ? "bg-zinc-700 text-white"
                  : "text-zinc-400 hover:text-white hover:bg-zinc-800/50"
              }`}
            >
              Настройки прострелов
            </button>
            <button
              onClick={() => setActiveSubTab("telegram")}
              className={`flex-1 min-w-[200px] px-6 py-3 rounded-lg font-medium smooth-transition ripple ${
                activeSubTab === "telegram"
                  ? "bg-zinc-700 text-white"
                  : "text-zinc-400 hover:text-white hover:bg-zinc-800/50"
              }`}
            >
              Настройка Телеграм
            </button>
            <button
              onClick={() => setActiveSubTab("format")}
              className={`flex-1 min-w-[200px] px-6 py-3 rounded-lg font-medium smooth-transition ripple ${
                activeSubTab === "format"
                  ? "bg-zinc-700 text-white"
                  : "text-zinc-400 hover:text-white hover:bg-zinc-800/50"
              }`}
            >
              Формат отправки детекта
            </button>
            <button
              onClick={() => setActiveSubTab("strategies")}
              className={`flex-1 min-w-[200px] px-6 py-3 rounded-lg font-medium smooth-transition ripple ${
                activeSubTab === "strategies"
                  ? "bg-zinc-700 text-white"
                  : "text-zinc-400 hover:text-white hover:bg-zinc-800/50"
              }`}
            >
              Стратегии
            </button>
            <button
              onClick={() => setActiveSubTab("blacklist")}
              className={`flex-1 min-w-[200px] px-6 py-3 rounded-lg font-medium smooth-transition ripple ${
                activeSubTab === "blacklist"
                  ? "bg-zinc-700 text-white"
                  : "text-zinc-400 hover:text-white hover:bg-zinc-800/50"
              }`}
            >
              Чёрный список
            </button>
          </div>
        </div>

        {/* Предупреждение о незаполненных Telegram-данных */}
        {(!telegramChatId || !telegramChatId.trim() || !telegramBotToken || !telegramBotToken.trim()) && (
          <div className="mb-6">
            <div className="bg-red-500/15 border border-red-500/60 text-red-300 px-4 py-3 rounded-lg text-sm flex items-start gap-2">
              <svg
                className="w-5 h-5 mt-0.5 flex-shrink-0"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M12 9v2m0 4h.01M10.29 3.86L1.82 18a1 1 0 00.86 1.5h18.64a1 1 0 00.86-1.5L13.71 3.86a1 1 0 00-1.72 0z"
                />
              </svg>
              <span>Введите данные Телеграм для получения детектов</span>
            </div>
          </div>
        )}
        
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
        
        {/* Контент в зависимости от выбранной подтемы */}
        {activeSubTab === "telegram" && (
          <div className="grid grid-cols-1 md:grid-cols-12 gap-6">
            {/* Интеграция с Telegram - всегда на всю ширину */}
            <div className="col-span-1 md:col-span-12">
                <div className={`bg-zinc-900 border border-zinc-800 rounded-xl transition-all duration-300 ${
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
                              <ChatIdHelp showBotTokenWarning={true} forBotToken={true} />
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
              </div>
          </div>
        )}
        
        {activeSubTab === "format" && (
          <div className="grid grid-cols-1 md:grid-cols-12 gap-6">
              {/* Карточки настроек - показываем только когда нет раскрытых карточек */}
              {!isMessageFormatExpanded && !isChartSettingsExpanded && (
                <>
                  {/* Формат отправки детекта - карточка */}
                  <div className="col-span-1 md:col-span-4">
                    <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6 hover:border-zinc-700 transition-colors cursor-pointer h-full flex flex-col" onClick={() => setIsMessageFormatExpanded(true)}>
                      <div className="flex items-center gap-2 mb-2">
                        <h2 className="text-xl font-bold text-white">Формат отправки детекта</h2>
                        <svg className="w-5 h-5 text-zinc-400 cursor-help" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <title>Настройте формат сообщений, которые будут отправляться в Telegram при обнаружении стрелы. Используйте вставки для добавления данных о детекте (дельта, объём, биржа и т.д.).</title>
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                      </div>
                      <p className="text-sm text-zinc-400 mb-4 flex-grow">
                        Настройте формат сообщений, которые будут отправляться в Telegram при обнаружении стрелы. Используйте вставки для добавления данных о детекте.
                      </p>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setIsMessageFormatExpanded(true);
                        }}
                        className="w-full px-4 py-2 bg-gradient-to-r from-emerald-500 to-emerald-600 hover:from-emerald-600 hover:to-emerald-700 text-white font-medium rounded-lg smooth-transition ripple hover-glow shadow-emerald"
                      >
                        Настроить формат
                      </button>
                    </div>
                  </div>
                  
                  
                  {/* Отправка графиков прострелов - карточка */}
                  <div className="col-span-1 md:col-span-4">
                    <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6 hover:border-zinc-700 transition-colors cursor-pointer h-full flex flex-col" onClick={() => setIsChartSettingsExpanded(true)}>
                      <div className="flex items-center gap-2 mb-2">
                        <h2 className="text-xl font-bold text-white">Отправка графиков прострелов</h2>
                        <svg className="w-5 h-5 text-zinc-400 cursor-help" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <title>Включите отправку тиковых графиков для выбранных торговых пар. Графики будут отправляться вместе с текстовыми детектами и показывать движение цены за 30 минут до момента детекта.</title>
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                      </div>
                      <p className="text-sm text-zinc-400 mb-4 flex-grow">
                        Включите отправку тиковых графиков для выбранных торговых пар. Графики будут отправляться вместе с текстовыми детектами.
                      </p>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setIsChartSettingsExpanded(true);
                        }}
                        className="w-full px-4 py-2 bg-gradient-to-r from-emerald-500 to-emerald-600 hover:from-emerald-600 hover:to-emerald-700 text-white font-medium rounded-lg smooth-transition ripple hover-glow shadow-emerald"
                      >
                        Настроить графики
                      </button>
                    </div>
                  </div>
                </>
              )}
              
              {/* Формат отправки детекта - раскрытый режим */}
              {isMessageFormatExpanded && (
                <div className="col-span-1 md:col-span-12">
                  <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6">
                    <div className="flex items-center justify-between mb-1">
                      <div className="flex items-center gap-2">
                        <h2 className="text-xl font-bold text-white">Формат отправки детекта</h2>
                        <svg className="w-5 h-5 text-zinc-400 cursor-help" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <title>Настройте формат сообщений, которые будут отправляться в Telegram при обнаружении стрелы. Используйте вставки для добавления данных о детекте (дельта, объём, биржа и т.д.).</title>
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                      </div>
                      <button
                        onClick={() => setIsMessageFormatExpanded(false)}
                        className="px-4 py-2 bg-zinc-700 hover:bg-zinc-600 text-white text-sm font-medium rounded-lg smooth-transition"
                      >
                        Скрыть
                      </button>
                    </div>
                    
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
                          { friendly: "[[Торговая пара]]", label: "Торговая пара", desc: "Символ пары (например: BTC-USDT)" },
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
                            className="text-left px-3 py-2 bg-zinc-800 hover:bg-zinc-700 border-2 border-zinc-600 hover:border-emerald-500 rounded-lg transition-all cursor-pointer group shadow-sm hover:shadow-md"
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
                        </label>
                      </div>
                      <div className="relative">
                        <div
                          id="messageTemplate"
                          contentEditable
                          suppressContentEditableWarning
                          onInput={(e) => {
                            const editor = e.currentTarget as HTMLElement;
                            const content = editor.innerHTML;

                            // Извлекаем технические ключи из визуальных блоков
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

                            // Заменяем <br> обратно на переносы строк
                            textContent = textContent.replace(/<br\s*\/?>/gi, '\n');

                            // Обновляем только состояние, не пересоздавая HTML,
                            // чтобы не сбивать позицию курсора при вводе
                            isUserEditingRef.current = true;
                            setMessageTemplate(textContent);
                          }}
                          onContextMenu={handleContextMenu}
                          onKeyDown={handleKeyDown}
                          onClick={() => setContextMenu(null)}
                          className="w-full min-h-64 px-4 py-3 bg-zinc-800 border-2 border-zinc-600 rounded-lg text-white font-mono text-sm focus:outline-none focus:ring-2 focus:border-emerald-500 focus:ring-emerald-500 resize-none overflow-y-auto template-editor cursor-text"
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

                    {/* Превью сообщения */}
                    <div className="mb-4">
                      <label className="block text-sm font-medium text-zinc-300 mb-2">
                        Превью сообщения в Telegram
                      </label>
                      <div className="bg-zinc-800 border-2 border-zinc-700 rounded-lg p-4 min-h-[120px]">
                        <div 
                          className="text-white text-sm whitespace-pre-wrap font-sans"
                          dangerouslySetInnerHTML={{ __html: generateMessagePreview(messageTemplate).replace(/\n/g, '<br>') }}
                        />
                      </div>
                      <p className="text-xs text-zinc-500 mt-2">
                        💡 Это пример того, как будет выглядеть сообщение в Telegram с примерами значений
                      </p>
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
                  </div>
                </div>
              )}
              
              {/* Отправка графиков прострелов - раскрытый режим */}
              {isChartSettingsExpanded && (
                <div className="col-span-1 md:col-span-12">
                  <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6">
                    {/* Шапка карточки */}
                    <div className="flex items-start justify-between mb-4">
                      <div className="flex-1">
                        <div className="flex items-center gap-2 mb-2">
                          <h2 className="text-xl font-bold text-white">Отправка графиков прострелов</h2>
                          <svg className="w-5 h-5 text-zinc-400 cursor-help" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <title>Включите отправку тиковых графиков для выбранных торговых пар. Графики будут отправляться вместе с текстовыми детектами и показывать движение цены за 30 минут до момента детекта.</title>
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                          </svg>
                        </div>
                        <p className="text-sm text-zinc-400">
                          Включите отправку тиковых графиков для выбранных торговых пар. Графики будут отправляться вместе с текстовыми детектами и показывать движение цены за 30 минут до момента детекта.
                        </p>
                      </div>
                      <div className="flex items-center gap-2 ml-4">
                        <button
                          onClick={toggleAllCharts}
                          className="px-4 py-2 bg-gradient-to-r from-blue-500 to-blue-600 hover:from-blue-600 hover:to-blue-700 text-white text-sm font-medium rounded-lg smooth-transition ripple hover-glow shadow-blue"
                        >
                          {areAllChartsEnabled() ? "Отключить все графики" : "Включить все графики"}
                        </button>
                        <button
                          onClick={() => setIsChartSettingsExpanded(false)}
                          className="px-4 py-2 bg-zinc-700 hover:bg-zinc-600 text-white text-sm font-medium rounded-lg smooth-transition"
                        >
                          Скрыть
                        </button>
                      </div>
                    </div>
            
                    {/* Компактная таблица настроек */}
                    <div className="overflow-x-auto w-full mb-4">
                      <table className="border-collapse w-full">
                        <thead>
                          <tr className="border-b border-zinc-700">
                            <th className="text-left py-2 px-4 text-sm font-semibold text-zinc-300">Биржа</th>
                            <th className="text-left py-2 px-4 text-sm font-semibold text-zinc-300">Spot</th>
                            <th className="text-left py-2 px-4 text-sm font-semibold text-zinc-300">Futures</th>
                          </tr>
                        </thead>
                        <tbody>
                          {["binance", "bybit", "bitget", "gate", "hyperliquid"].map((exchange) => {
                            const exchangeDisplayName = exchange === "gate" ? "Gate" : exchange === "hyperliquid" ? "Hyperliquid" : exchange.charAt(0).toUpperCase() + exchange.slice(1);
                            const spotCurrencies = getPairsForExchange(exchange, "spot");
                            const futuresCurrencies = getPairsForExchange(exchange, "futures");
                            
                            return (
                              <tr key={exchange} className="border-t border-zinc-800 hover:bg-zinc-800/50">
                                <td className="py-2.5 px-4 align-top">
                                  <span className="text-sm font-medium text-white">{exchangeDisplayName}</span>
                                </td>
                                <td className="py-2.5 px-4 align-top">
                                  {spotCurrencies.length > 0 ? (
                                    <div className="flex flex-wrap gap-1.5">
                                      {spotCurrencies.map((currency) => {
                                        const currencyKey = `${exchange}_spot_${currency}`;
                                        const isEnabled = chartSettings[currencyKey] === true;
                                        return (
                                          <button
                                            key={currencyKey}
                                            onClick={(e) => {
                                              e.stopPropagation();
                                              setChartSettings({
                                                ...chartSettings,
                                                [currencyKey]: !isEnabled
                                              });
                                            }}
                                            className={`px-2 py-1 text-xs font-medium rounded transition-colors ${
                                              isEnabled
                                                ? "bg-emerald-600 hover:bg-emerald-700 text-white"
                                                : "bg-zinc-700 hover:bg-zinc-600 text-zinc-300"
                                            }`}
                                          >
                                            {currency}
                                          </button>
                                        );
                                      })}
                                    </div>
                                  ) : (
                                    <span className="text-xs text-zinc-500">Нет пар</span>
                                  )}
                                </td>
                                <td className="py-2.5 px-4 align-top">
                                  {futuresCurrencies.length > 0 ? (
                                    <div className="flex flex-wrap gap-1.5">
                                      {futuresCurrencies.map((currency) => {
                                        const currencyKey = `${exchange}_futures_${currency}`;
                                        const isEnabled = chartSettings[currencyKey] === true;
                                        return (
                                          <button
                                            key={currencyKey}
                                            onClick={(e) => {
                                              e.stopPropagation();
                                              setChartSettings({
                                                ...chartSettings,
                                                [currencyKey]: !isEnabled
                                              });
                                            }}
                                            className={`px-2 py-1 text-xs font-medium rounded transition-colors ${
                                              isEnabled
                                                ? "bg-emerald-600 hover:bg-emerald-700 text-white"
                                                : "bg-zinc-700 hover:bg-zinc-600 text-zinc-300"
                                            }`}
                                          >
                                            {currency}
                                          </button>
                                        );
                                      })}
                                    </div>
                                  ) : (
                                    <span className="text-xs text-zinc-500">Нет пар</span>
                                  )}
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </div>
              )}
              
              {/* Отправка графиков прострелов - раскрытый режим */}
              {isChartSettingsExpanded && (
                <div className="col-span-1 md:col-span-12">
                  <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6">
                    {/* Шапка карточки */}
                    <div className="flex items-start justify-between mb-4">
                      <div className="flex-1">
                        <div className="flex items-center gap-2 mb-2">
                          <h2 className="text-xl font-bold text-white">Отправка графиков прострелов</h2>
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
                                      setConditionalTemplates(newTemplates);
                                    }}
                                    className="inline-flex items-center justify-center px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 text-white text-xs font-medium rounded-lg border border-zinc-700 hover:border-emerald-500/60 transition-colors"
                                  >
                                    <span className="mr-1 text-emerald-400 text-sm">+</span>
                                    Добавить условие
                                  </button>
                                </div>
                                
                                <div className="space-y-3">
                                  {template.conditions.map((condition, condIndex) => (
                                    <div
                                      key={condIndex}
                                      className="bg-zinc-900/50 border border-zinc-700/50 rounded-lg p-3 md:p-4 max-w-4xl"
                                    >
                                      <div className="flex gap-2 items-end mb-2">
                                        <div className="w-full md:w-56">
                                          <label className="block text-xs text-zinc-400 mb-1">Параметр</label>
                                          <select
                                            value={condition.type}
                                            onChange={(e) => {
                                              const newTemplates = [...conditionalTemplates];
                                              const newType = e.target.value as "volume" | "delta" | "series" | "symbol" | "wick_pct" | "exchange_market" | "direction";
                                              newTemplates[index].conditions[condIndex].type = newType;
                                              // Очищаем значения при смене типа
                                              if (newType === "series") {
                                                newTemplates[index].conditions[condIndex].value = undefined;
                                                newTemplates[index].conditions[condIndex].valueMin = undefined;
                                                newTemplates[index].conditions[condIndex].valueMax = undefined;
                                                newTemplates[index].conditions[condIndex].symbol = undefined;
                                                newTemplates[index].conditions[condIndex].exchange_market = undefined;
                                                newTemplates[index].conditions[condIndex].direction = undefined;
                                                newTemplates[index].conditions[condIndex].count = 2;
                                                newTemplates[index].conditions[condIndex].timeWindowSeconds = 300;
                                              } else if (newType === "delta" || newType === "wick_pct") {
                                                // Для дельты и тени используем диапазон
                                                newTemplates[index].conditions[condIndex].count = undefined;
                                                newTemplates[index].conditions[condIndex].timeWindowSeconds = undefined;
                                                newTemplates[index].conditions[condIndex].symbol = undefined;
                                                newTemplates[index].conditions[condIndex].exchange_market = undefined;
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
                                                newTemplates[index].conditions[condIndex].exchange_market = undefined;
                                                newTemplates[index].conditions[condIndex].direction = undefined;
                                                newTemplates[index].conditions[condIndex].symbol = "";
                                              } else if (newType === "exchange_market") {
                                                newTemplates[index].conditions[condIndex].value = undefined;
                                                newTemplates[index].conditions[condIndex].valueMin = undefined;
                                                newTemplates[index].conditions[condIndex].valueMax = undefined;
                                                newTemplates[index].conditions[condIndex].count = undefined;
                                                newTemplates[index].conditions[condIndex].timeWindowSeconds = undefined;
                                                newTemplates[index].conditions[condIndex].symbol = undefined;
                                                newTemplates[index].conditions[condIndex].direction = undefined;
                                                newTemplates[index].conditions[condIndex].exchange_market = "binance_spot";
                                              } else if (newType === "direction") {
                                                newTemplates[index].conditions[condIndex].value = undefined;
                                                newTemplates[index].conditions[condIndex].valueMin = undefined;
                                                newTemplates[index].conditions[condIndex].valueMax = undefined;
                                                newTemplates[index].conditions[condIndex].count = undefined;
                                                newTemplates[index].conditions[condIndex].timeWindowSeconds = undefined;
                                                newTemplates[index].conditions[condIndex].symbol = undefined;
                                                newTemplates[index].conditions[condIndex].exchange_market = undefined;
                                                newTemplates[index].conditions[condIndex].direction = "up";
                                              } else {
                                                // Для объёма - одно значение
                                                newTemplates[index].conditions[condIndex].count = undefined;
                                                newTemplates[index].conditions[condIndex].timeWindowSeconds = undefined;
                                                newTemplates[index].conditions[condIndex].valueMin = undefined;
                                                newTemplates[index].conditions[condIndex].valueMax = undefined;
                                                newTemplates[index].conditions[condIndex].symbol = undefined;
                                                newTemplates[index].conditions[condIndex].exchange_market = undefined;
                                                newTemplates[index].conditions[condIndex].direction = undefined;
                                                newTemplates[index].conditions[condIndex].value = 0;
                                              }
                                              // Обновляем описание шаблона
                                              const updatedDescription = generateTemplateDescription(newTemplates[index]);
                                              newTemplates[index].description = updatedDescription;
                                              setConditionalTemplates(newTemplates);
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
                                                  const newTemplates = [...conditionalTemplates];
                                                  const val = e.target.value === "" ? 300 : parseInt(e.target.value);
                                                  newTemplates[index].conditions[condIndex].timeWindowSeconds = isNaN(val) ? 300 : Math.max(60, val);
                                                  const updatedDescription = generateTemplateDescription(newTemplates[index]);
                                                  newTemplates[index].description = updatedDescription;
                                                  setConditionalTemplates(newTemplates);
                                                }}
                                                className="w-full px-3 py-2.5 bg-zinc-700 border border-zinc-600 rounded-lg text-white text-sm text-center focus:outline-none focus:ring-2 focus:ring-emerald-500"
                                                placeholder="300"
                                              />
                                            </div>
                                          </>
                                        ) : condition.type === "delta" ? (
                                          // Для дельты - только минимум, максимум всегда бесконечность
                                          <div className="flex-1">
                                            <label className="block text-xs text-zinc-400 mb-1">Дельта от (%)</label>
                                            <input
                                              type="number"
                                              step="0.1"
                                              min="0"
                                              value={condition.valueMin !== undefined ? condition.valueMin : (condition.value !== undefined ? condition.value : "")}
                                              onChange={(e) => {
                                                const newTemplates = [...conditionalTemplates];
                                                const val = e.target.value === "" ? 0 : parseFloat(e.target.value);
                                                newTemplates[index].conditions[condIndex].valueMin = isNaN(val) ? 0 : val;
                                                // Всегда устанавливаем valueMax = null (бесконечность) для дельты
                                                newTemplates[index].conditions[condIndex].valueMax = null;
                                                // Удаляем старое поле value для обратной совместимости
                                                if (newTemplates[index].conditions[condIndex].value !== undefined) {
                                                  delete newTemplates[index].conditions[condIndex].value;
                                                }
                                                const updatedDescription = generateTemplateDescription(newTemplates[index]);
                                                newTemplates[index].description = updatedDescription;
                                                setConditionalTemplates(newTemplates);
                                              }}
                                              className="w-full px-3 py-2.5 bg-zinc-700 border border-zinc-600 rounded-lg text-white text-sm text-center focus:outline-none focus:ring-2 focus:ring-emerald-500"
                                              placeholder="0"
                                            />
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
                                              className="w-40 px-3 py-2 bg-zinc-700 border border-zinc-600 rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
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
                                                  className="w-full max-w-[140px] px-3 py-2.5 bg-zinc-700 border border-zinc-600 rounded-lg text-white text-sm text-center focus:outline-none focus:ring-2 focus:ring-emerald-500"
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
                                                  className="w-full max-w-[140px] px-3 py-2.5 bg-zinc-700 border border-zinc-600 rounded-lg text-white text-sm text-center focus:outline-none focus:ring-2 focus:ring-emerald-500"
                                                  title="Введите число от 0 до 100 или оставьте ∞ для бесконечности"
                                                />
                                              </div>
                                            </div>
                                          </div>
                                        ) : condition.type === "exchange_market" ? (
                                          // Для биржи и типа рынка - объединенный выбор
                                          <div className="flex-1">
                                            <label className="block text-xs text-zinc-400 mb-1">Биржа и тип рынка</label>
                                            <select
                                              value={condition.exchange_market || (condition.exchange && condition.market ? `${condition.exchange}_${condition.market === "linear" ? "futures" : condition.market}` : "binance_spot")}
                                              onChange={(e) => {
                                                const newTemplates = [...conditionalTemplates];
                                                newTemplates[index].conditions[condIndex].exchange_market = e.target.value;
                                                // Удаляем старые поля для обратной совместимости
                                                delete newTemplates[index].conditions[condIndex].exchange;
                                                delete newTemplates[index].conditions[condIndex].market;
                                                const updatedDescription = generateTemplateDescription(newTemplates[index]);
                                                newTemplates[index].description = updatedDescription;
                                                setConditionalTemplates(newTemplates);
                                              }}
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
                                              className="w-40 px-3 py-2 bg-zinc-700 border border-zinc-600 rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                                            >
                                              <option value="up">Вверх ⬆️</option>
                                              <option value="down">Вниз ⬇️</option>
                                            </select>
                                          </div>
                                        ) : (
                                          // Для объёма - одно значение как было
                                          <div className="w-full md:w-auto md:min-w-[220px]">
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
                                              className="w-full px-3 py-2.5 bg-zinc-700 border border-zinc-600 rounded-lg text-white text-sm text-center focus:outline-none focus:ring-2 focus:ring-emerald-500"
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
                              
                              {/* Редактор шаблона сообщения для условного шаблона с теми же вставками, что и в основном формате */}
                              <div className="mb-4">
                                <div className="flex items-center justify-between mb-2">
                                  <label className="block text-xs text-zinc-400">
                                    Шаблон сообщения
                                  </label>
                                </div>

                                {/* Доступные вставки для условного шаблона */}
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
                                        onClick={() => {
                                          const editor = document.getElementById(`conditionalTemplate_${index}`) as HTMLElement;
                                          if (editor) {
                                            const selection = window.getSelection();
                                            if (selection && selection.rangeCount > 0) {
                                              const range = selection.getRangeAt(0);
                                              range.deleteContents();

                                              const block = document.createElement("span");
                                              block.className =
                                                "inline-flex items-center gap-1.5 px-2 py-1 mx-0.5 bg-emerald-500/20 border border-emerald-500/50 rounded text-emerald-300 text-xs font-medium cursor-default";
                                              block.setAttribute("data-placeholder-key", placeholder.friendly);
                                              block.setAttribute("contenteditable", "false");
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
                                              newTemplates[index].template = convertToTechnicalKeys(
                                                textContent.replace(/<br\s*\/?>/gi, "\n")
                                              );
                                              setConditionalTemplates(newTemplates);
                                            }
                                          }
                                        }}
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
                                      // Заменяем HTML-переносы строк на обычные \n
                                      textContent = textContent.replace(/<br\s*\/?>/gi, "\n");

                                      // Помечаем, что пользователь сейчас редактирует условный шаблон,
                                      // чтобы эффект инициализации не перезатирал содержимое и не сбивал курсор
                                      isConditionalUserEditingRef.current = true;

                                      const newTemplates = [...conditionalTemplates];
                                      newTemplates[index].template = convertToTechnicalKeys(textContent);
                                      setConditionalTemplates(newTemplates);

                                      // Через небольшой таймаут снимаем флаг редактирования
                                      setTimeout(() => {
                                        isConditionalUserEditingRef.current = false;
                                      }, 150);
                                    }}
                                    className="w-full min-h-32 px-4 py-3 bg-zinc-800 border-2 border-zinc-600 rounded-lg text-white font-mono text-sm focus:outline-none focus:ring-2 focus:border-emerald-500 focus:ring-emerald-500 resize-none overflow-y-auto template-editor cursor-text"
                                    style={{ whiteSpace: "pre-wrap" }}
                                  />

                                  {/* Emoji Picker для условных шаблонов */}
                                  {showEmojiPicker.conditional === index && showEmojiPicker.position && (
                                    <>
                                      <div
                                        className="fixed inset-0 z-40"
                                        onClick={() =>
                                          setShowEmojiPicker({ main: false, conditional: null, position: undefined })
                                        }
                                      />
                                      <div
                                        className="fixed z-50"
                                        style={{
                                          left: `${showEmojiPicker.position.x}px`,
                                          top: `${showEmojiPicker.position.y}px`,
                                        }}
                                      >
                                        <EmojiPicker
                                          onEmojiClick={(emojiData) =>
                                            insertEmoji(emojiData as any, `conditionalTemplate_${index}`, true)
                                          }
                                          theme={"dark" as any}
                                          width={350}
                                          height={400}
                                          previewConfig={{
                                            showPreview: false,
                                          }}
                                        />
                                      </div>
                                    </>
                                  )}
                                </div>

                                {/* Превью сообщения для условного шаблона */}
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
                          useGlobalFilters: true, // По умолчанию используем глобальные фильтры
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
              {/* Отправка графиков прострелов - раскрытый режим */}
              {isChartSettingsExpanded && (
                <div className="col-span-1 md:col-span-12">
                  <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6">
                    {/* Шапка карточки */}
                    <div className="flex items-start justify-between mb-4">
                      <div className="flex-1">
                        <div className="flex items-center gap-2 mb-2">
                          <h2 className="text-xl font-bold text-white">Отправка графиков прострелов</h2>
                          <svg className="w-5 h-5 text-zinc-400 cursor-help" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <title>Включите отправку тиковых графиков для выбранных торговых пар. Графики будут отправляться вместе с текстовыми детектами и показывать движение цены за 30 минут до момента детекта.</title>
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                          </svg>
                        </div>
                        <p className="text-sm text-zinc-400">
                          Включите отправку тиковых графиков для выбранных торговых пар. Графики будут отправляться вместе с текстовыми детектами и показывать движение цены за 30 минут до момента детекта.
                        </p>
                      </div>
                      <div className="flex items-center gap-2 ml-4">
                        <button
                          onClick={toggleAllCharts}
                          className="px-4 py-2 bg-gradient-to-r from-blue-500 to-blue-600 hover:from-blue-600 hover:to-blue-700 text-white text-sm font-medium rounded-lg smooth-transition ripple hover-glow shadow-blue"
                        >
                          {areAllChartsEnabled() ? "Отключить все графики" : "Включить все графики"}
                        </button>
                        <button
                          onClick={() => setIsChartSettingsExpanded(false)}
                          className="px-4 py-2 bg-zinc-700 hover:bg-zinc-600 text-white text-sm font-medium rounded-lg smooth-transition"
                        >
                          Скрыть
                        </button>
                      </div>
                    </div>
            
                    {/* Компактная таблица настроек */}
                    <div className="overflow-x-auto w-full mb-4">
                      <table className="border-collapse w-full">
                        <thead>
                          <tr className="border-b border-zinc-700">
                            <th className="text-left py-2 px-4 text-sm font-semibold text-zinc-300">Биржа</th>
                            <th className="text-left py-2 px-4 text-sm font-semibold text-zinc-300">Spot</th>
                            <th className="text-left py-2 px-4 text-sm font-semibold text-zinc-300">Futures</th>
                          </tr>
                        </thead>
                        <tbody>
                          {["binance", "bybit", "bitget", "gate", "hyperliquid"].map((exchange) => {
                            const exchangeDisplayName = exchange === "gate" ? "Gate" : exchange === "hyperliquid" ? "Hyperliquid" : exchange.charAt(0).toUpperCase() + exchange.slice(1);
                            const spotCurrencies = getPairsForExchange(exchange, "spot");
                            const futuresCurrencies = getPairsForExchange(exchange, "futures");
                            
                            return (
                              <tr key={exchange} className="border-t border-zinc-800 hover:bg-zinc-800/50">
                                <td className="py-2.5 px-4 align-top">
                                  <span className="text-sm font-medium text-white">{exchangeDisplayName}</span>
                                </td>
                                <td className="py-2.5 px-4 align-top">
                                  {spotCurrencies.length > 0 ? (
                                    <div className="flex flex-wrap gap-1.5">
                                      {spotCurrencies.map((currency) => {
                                        const currencyKey = `${exchange}_spot_${currency}`;
                                        const isEnabled = chartSettings[currencyKey] === true;
                                        return (
                                          <button
                                            key={currencyKey}
                                            onClick={(e) => {
                                              e.stopPropagation();
                                              setChartSettings({
                                                ...chartSettings,
                                                [currencyKey]: !isEnabled
                                              });
                                            }}
                                            className={`inline-flex items-center justify-center h-6 px-2 text-xs font-medium rounded transition-all ${
                                              isEnabled
                                                ? "bg-emerald-500/20 border border-emerald-500 text-emerald-300 hover:bg-emerald-500/30"
                                                : "bg-zinc-800 border border-zinc-700 text-zinc-400 hover:bg-zinc-700 hover:text-zinc-300"
                                            }`}
                                          >
                                            {currency}
                                          </button>
                                        );
                                      })}
                                    </div>
                                  ) : (
                                    <span className="text-sm text-zinc-500">—</span>
                                  )}
                                </td>
                                <td className="py-2.5 px-4 align-top">
                                  {futuresCurrencies.length > 0 ? (
                                    <div className="flex flex-wrap gap-1.5">
                                      {futuresCurrencies.map((currency) => {
                                        const currencyKey = `${exchange}_futures_${currency}`;
                                        const isEnabled = chartSettings[currencyKey] === true;
                                        return (
                                          <button
                                            key={currencyKey}
                                            onClick={(e) => {
                                              e.stopPropagation();
                                              setChartSettings({
                                                ...chartSettings,
                                                [currencyKey]: !isEnabled
                                              });
                                            }}
                                            className={`inline-flex items-center justify-center h-6 px-2 text-xs font-medium rounded transition-all ${
                                              isEnabled
                                                ? "bg-emerald-500/20 border border-emerald-500 text-emerald-300 hover:bg-emerald-500/30"
                                                : "bg-zinc-800 border border-zinc-700 text-zinc-400 hover:bg-zinc-700 hover:text-zinc-300"
                                            }`}
                                          >
                                            {currency}
                                          </button>
                                        );
                                      })}
                                    </div>
                                  ) : (
                                    <span className="text-sm text-zinc-500">—</span>
                                  )}
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                    
                    {/* Кнопка сохранения */}
                    <button
                      onClick={async () => {
                        await saveAllSettings();
                      }}
                      className="w-full px-4 py-2 bg-gradient-to-r from-emerald-500 to-emerald-600 hover:from-emerald-600 hover:to-emerald-700 text-white font-medium rounded-lg smooth-transition ripple hover-glow shadow-emerald"
                    >
                      Сохранить настройки графиков
                    </button>
                  </div>
                </div>
              )}
          </div>
        )}
        
        {activeSubTab === "spikes" && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {/* Фильтры по биржам */}
              <>
                  <div className="space-y-6">
                    {/* Фильтры по биржам */}
                    <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6">
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
                          }}
                          className="px-4 py-2 bg-gradient-to-r from-emerald-500 to-emerald-600 hover:from-emerald-600 hover:to-emerald-700 text-white text-sm font-medium rounded-lg smooth-transition ripple hover-glow shadow-emerald"
                        >
                          Сохранить изменения
                        </button>
                      </div>
                      <p className="text-sm text-zinc-400 mb-6">Выберите биржи для мониторинга и настройте параметры детектирования для каждой биржи отдельно (Spot и Futures). Можно включить/выключить биржи и настроить минимальные значения дельты, объёма и тени свечи.</p>
                      
                      <div className="space-y-2">
                        {(() => {
                          // Создаем массив всех комбинаций биржа + рынок
                          const exchangeMarketCombinations: Array<{exchange: string, market: "spot" | "futures"}> = [];
                          ["binance", "bybit", "bitget", "gate", "hyperliquid"].forEach((exchange) => {
                            exchangeMarketCombinations.push({exchange, market: "spot"});
                            exchangeMarketCombinations.push({exchange, market: "futures"});
                          });
                          
                          return exchangeMarketCombinations.map(({exchange, market}) => {
                            const sectionKey = `${exchange}_${market}`;
                            const isExpanded = expandedExchanges[sectionKey] || false;
                            const exchangeDisplayName = exchange === "gate" ? "Gate" : exchange === "hyperliquid" ? "Hyperliquid" : exchange.charAt(0).toUpperCase() + exchange.slice(1);
                            const marketDisplayName = market === "spot" ? "Spot" : "Futures";
                            const settings = exchangeSettings[exchange];
                            const marketSettings = market === "spot" ? settings.spot : settings.futures;
                            const pairs = getPairsForExchange(exchange, market);
                            const quoteCurrency = getQuoteCurrencyForExchange(exchange, market);
                            const showPairsImmediately = shouldShowPairsImmediately(exchange, market);
                            
                            return (
                              <div key={sectionKey} className="bg-zinc-800 rounded-lg overflow-hidden">
                                {/* Заголовок секции */}
                                <div className="flex items-center gap-3 p-4">
                                  <div
                                    className={`w-12 h-6 rounded-full transition-colors cursor-pointer ${
                                      marketSettings.enabled ? "bg-emerald-500" : "bg-zinc-600"
                                    }`}
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      setExchangeSettings({
                                        ...exchangeSettings,
                                        [exchange]: {
                                          ...settings,
                                          [market]: { ...marketSettings, enabled: !marketSettings.enabled },
                                        },
                                      });
                                    }}
                                  >
                                    <div className={`w-5 h-5 bg-white rounded-full transition-transform mt-0.5 ${
                                      marketSettings.enabled ? "translate-x-6" : "translate-x-1"
                                    }`} />
                                  </div>
                                  <span
                                    className="flex-1 text-white font-medium cursor-pointer hover:text-zinc-300 transition-colors"
                                    onClick={() => {
                                      setExpandedExchanges({
                                        ...expandedExchanges,
                                        [sectionKey]: !isExpanded,
                                      });
                                    }}
                                  >
                                    {exchangeDisplayName} {marketDisplayName}
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
                                        [sectionKey]: !isExpanded,
                                      });
                                    }}
                                  >
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                                  </svg>
                                </div>
                                
                                {/* Раскрывающийся контент */}
                                {isExpanded && (
                                  <div className="px-4 pb-4">
                                    {showPairsImmediately ? (
                                      // Для Binance Spot, Binance Futures и Bybit Spot - показываем таблицу всех пар
                                      <div className="bg-zinc-900 rounded-lg p-4 border border-zinc-700 w-full">
                                        <h4 className="text-sm font-medium text-white mb-4">Торговые пары</h4>
                                        <div className="overflow-x-auto w-full">
                                          <table className="border-collapse w-full">
                                            <thead>
                                              <tr className="border-b border-zinc-700">
                                                <th className="text-left py-2 px-3 text-xs font-semibold text-zinc-300">Пара</th>
                                                <th className="text-left py-2 px-3 text-xs font-semibold text-zinc-300">Включено</th>
                                                <th className="text-left py-2 px-3 text-xs font-semibold text-zinc-300">Дельта %</th>
                                                <th className="text-left py-2 px-3 text-xs font-semibold text-zinc-300">Объём USDT</th>
                                                <th className="text-left py-2 px-3 text-xs font-semibold text-zinc-300">Тень %</th>
                                              </tr>
                                            </thead>
                                            <tbody>
                                              {pairs.map((pair) => {
                                                const pairKey = `${exchange}_${market}_${pair}`;
                                                const savedPairData = pairSettings[pairKey];
                                                
                                                // Используем общие настройки рынка, если для пары не заданы индивидуальные
                                                const pairData = savedPairData || {
                                                  enabled: false,
                                                  delta: marketSettings.delta || "",
                                                  volume: marketSettings.volume || "",
                                                  shadow: marketSettings.shadow || ""
                                                };
                                                
                                                return (
                                                  <tr key={pair} className={`border-b border-zinc-800 hover:bg-zinc-800/50 ${!pairData.enabled ? "opacity-60" : ""}`}>
                                                    <td className="py-2 px-3 text-white font-medium text-sm">{pair}</td>
                                                    <td className="py-2 px-3">
                                                      <div
                                                        className={`w-10 h-5 rounded-full transition-colors cursor-pointer inline-flex ${
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
                                                    </td>
                                                    <td className="py-2 px-3">
                                                      <input
                                                        type="number"
                                                        value={pairData.delta}
                                                        onChange={(e) => {
                                                          setPairSettings({
                                                            ...pairSettings,
                                                            [pairKey]: { ...pairData, delta: e.target.value },
                                                          });
                                                        }}
                                                        className="w-20 px-2 py-1 bg-zinc-800 border border-zinc-700 rounded text-white text-xs focus:outline-none focus:ring-1 focus:ring-emerald-500"
                                                        placeholder=""
                                                      />
                                                    </td>
                                                    <td className="py-2 px-3">
                                                      <input
                                                        type="number"
                                                        value={pairData.volume}
                                                        onChange={(e) => {
                                                          setPairSettings({
                                                            ...pairSettings,
                                                            [pairKey]: { ...pairData, volume: e.target.value },
                                                          });
                                                        }}
                                                        className="w-24 px-2 py-1 bg-zinc-800 border border-zinc-700 rounded text-white text-xs focus:outline-none focus:ring-1 focus:ring-emerald-500"
                                                        placeholder=""
                                                      />
                                                    </td>
                                                    <td className="py-2 px-3">
                                                      <input
                                                        type="number"
                                                        value={pairData.shadow}
                                                        onChange={(e) => {
                                                          setPairSettings({
                                                            ...pairSettings,
                                                            [pairKey]: { ...pairData, shadow: e.target.value },
                                                          });
                                                        }}
                                                        className="w-20 px-2 py-1 bg-zinc-800 border border-zinc-700 rounded text-white text-xs focus:outline-none focus:ring-1 focus:ring-emerald-500"
                                                        placeholder=""
                                                      />
                                                    </td>
                                                  </tr>
                                                );
                                              })}
                                            </tbody>
                                          </table>
                                        </div>
                                      </div>
                                    ) : (
                                      // Для остальных бирж - показываем настройки для одной пары
                                      <div className="bg-zinc-900 rounded-lg p-4 space-y-4">
                                        {quoteCurrency && (
                                          <div className="flex items-center justify-between mb-4">
                                            <div>
                                              <h3 className="text-white font-medium">{quoteCurrency}</h3>
                                              <p className="text-sm text-zinc-400">Торговая пара</p>
                                            </div>
                                          </div>
                                        )}
                                        
                                        <div className="grid grid-cols-3 gap-3">
                                          <div>
                                            <label className="block text-xs text-zinc-400 mb-1">Дельта %</label>
                                            <input
                                              type="number"
                                              value={marketSettings.delta}
                                              onChange={(e) => {
                                                setExchangeSettings({
                                                  ...exchangeSettings,
                                                  [exchange]: {
                                                    ...settings,
                                                    [market]: { ...marketSettings, delta: e.target.value },
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
                                              value={marketSettings.volume}
                                              onChange={(e) => {
                                                setExchangeSettings({
                                                  ...exchangeSettings,
                                                  [exchange]: {
                                                    ...settings,
                                                    [market]: { ...marketSettings, volume: e.target.value },
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
                                              value={marketSettings.shadow}
                                              onChange={(e) => {
                                                setExchangeSettings({
                                                  ...exchangeSettings,
                                                  [exchange]: {
                                                    ...settings,
                                                    [market]: { ...marketSettings, shadow: e.target.value },
                                                  },
                                                });
                                              }}
                                              className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                                            />
                                          </div>
                                        </div>
                                      </div>
                                    )}
                                  </div>
                                )}
                              </div>
                            );
                          });
                        })()}
                      </div>
                    </div>
                  </div>
                  
                  {/* Правая колонка - Активные фильтры */}
                  <div>
                    <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6">
                      <h2 className="text-xl font-bold text-white mb-1">Активные фильтры</h2>
                      <p className="text-xs text-zinc-500 mb-4">
                        Сводная таблица по всем включённым фильтрам прострелов
                      </p>

                      {(() => {
                        type ActiveFilterRow = {
                          id: string;
                          exchangeKey: string;
                          exchangeLabel: string;
                          marketKey: "spot" | "futures";
                          marketLabel: string;
                          pair: string | null;
                          delta: string;
                          volume: string;
                          shadow: string;
                          enabled: boolean;
                        };

                        const rows: ActiveFilterRow[] = [];

                        ["binance", "bybit", "bitget", "gate", "hyperliquid"].forEach((exchangeKey) => {
                          const exchangeDisplayName =
                            exchangeKey === "gate"
                              ? "Gate"
                              : exchangeKey === "hyperliquid"
                              ? "Hyperliquid"
                              : exchangeKey.charAt(0).toUpperCase() + exchangeKey.slice(1);

                          const settings = exchangeSettings[exchangeKey];
                          if (!settings) return;

                          (["spot", "futures"] as const).forEach((marketKey) => {
                            const marketSettings = marketKey === "spot" ? settings.spot : settings.futures;
                            const marketLabel = marketKey === "spot" ? "Spot" : "Futures";

                            // Проверяем, есть ли дополнительные пары для данного рынка
                            const hasAdditionalPairs = Object.keys(pairSettings).some(
                              (key) => key.startsWith(`${exchangeKey}_${marketKey}_`) && pairSettings[key]?.enabled
                            );

                            // Общий фильтр по рынку (все пары)
                            if (marketSettings.enabled && !hasAdditionalPairs) {
                              const id = `${exchangeKey}_${marketKey}_ALL`;
                              rows.push({
                                id,
                                exchangeKey,
                                exchangeLabel: exchangeDisplayName,
                                marketKey,
                                marketLabel,
                                pair: null,
                                delta: marketSettings.delta || "0",
                                volume: marketSettings.volume || "0",
                                shadow: marketSettings.shadow || "0",
                                enabled: marketSettings.enabled,
                              });
                            }

                            // Индивидуальные настройки пар
                            Object.entries(pairSettings).forEach(([key, pairData]) => {
                              if (!key.startsWith(`${exchangeKey}_${marketKey}_`)) return;
                              if (!pairData?.enabled) return;

                              const parts = key.split("_");
                              if (parts.length < 3) return;
                              const pair = parts.slice(2).join("_");
                              const id = `${exchangeKey}_${marketKey}_${pair}`;

                              rows.push({
                                id,
                                exchangeKey,
                                exchangeLabel: exchangeDisplayName,
                                marketKey,
                                marketLabel,
                                pair,
                                delta: pairData.delta || "0",
                                volume: pairData.volume || "0",
                                shadow: pairData.shadow || "0",
                                enabled: pairData.enabled,
                              });
                            });
                          });
                        });

                        if (rows.length === 0) {
                          return (
                            <div className="text-center py-8">
                              <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-zinc-800/50 mb-3">
                                <svg className="w-8 h-8 text-zinc-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                  <path
                                    strokeLinecap="round"
                                    strokeLinejoin="round"
                                    strokeWidth={2}
                                    d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                                  />
                                </svg>
                              </div>
                              <p className="text-zinc-400 text-sm">Нет активных фильтров</p>
                              <p className="text-zinc-500 text-xs mt-1">
                                Включите биржи и пары в левом блоке для отображения активных фильтров
                              </p>
                            </div>
                          );
                        }

                        const handleToggleStatus = async (row: ActiveFilterRow) => {
                          if (row.pair === null) {
                            const settings = exchangeSettings[row.exchangeKey];
                            if (!settings) return;
                            const marketSettings =
                              row.marketKey === "spot" ? settings.spot : settings.futures;

                            const updatedMarket = {
                              ...marketSettings,
                              enabled: !marketSettings.enabled,
                            };

                            setExchangeSettings({
                              ...exchangeSettings,
                              [row.exchangeKey]: {
                                ...settings,
                                [row.marketKey]: updatedMarket,
                              },
                            });
                          } else {
                            const pairKey = `${row.exchangeKey}_${row.marketKey}_${row.pair}`;
                            const currentPair = pairSettings[pairKey] || {
                              enabled: false,
                              delta: row.delta,
                              volume: row.volume,
                              shadow: row.shadow,
                            };

                            setPairSettings({
                              ...pairSettings,
                              [pairKey]: { ...currentPair, enabled: !currentPair.enabled },
                            });
                          }

                          await saveAllSettings();
                        };

                        const commitInlineEdit = async (
                          row: ActiveFilterRow,
                          field: "delta" | "volume" | "shadow",
                          newValue: string,
                          previousValue: string
                        ) => {
                          // Обновляем состояние
                          if (row.pair === null) {
                            const settings = exchangeSettings[row.exchangeKey];
                            if (!settings) return;
                            const marketSettings =
                              row.marketKey === "spot" ? settings.spot : settings.futures;

                            const updatedMarket = {
                              ...marketSettings,
                              [field]: newValue,
                            };

                            setExchangeSettings({
                              ...exchangeSettings,
                              [row.exchangeKey]: {
                                ...settings,
                                [row.marketKey]: updatedMarket,
                              },
                            });
                          } else {
                            const pairKey = `${row.exchangeKey}_${row.marketKey}_${row.pair}`;
                            const currentPair = pairSettings[pairKey] || {
                              enabled: true,
                              delta: row.delta,
                              volume: row.volume,
                              shadow: row.shadow,
                            };

                            setPairSettings({
                              ...pairSettings,
                              [pairKey]: {
                                ...currentPair,
                                [field]: newValue,
                              },
                            });
                          }

                          const success = await saveAllSettings();

                          if (!success) {
                            // Откатываем в случае ошибки
                            if (row.pair === null) {
                              const settings = exchangeSettings[row.exchangeKey];
                              if (!settings) return;
                              const marketSettings =
                                row.marketKey === "spot" ? settings.spot : settings.futures;

                              const revertedMarket = {
                                ...marketSettings,
                                [field]: previousValue,
                              };

                              setExchangeSettings({
                                ...exchangeSettings,
                                [row.exchangeKey]: {
                                  ...settings,
                                  [row.marketKey]: revertedMarket,
                                },
                              });
                            } else {
                              const pairKey = `${row.exchangeKey}_${row.marketKey}_${row.pair}`;
                              const currentPair = pairSettings[pairKey];
                              if (!currentPair) return;

                              setPairSettings({
                                ...pairSettings,
                                [pairKey]: {
                                  ...currentPair,
                                  [field]: previousValue,
                                },
                              });
                            }
                          } else {
                            // Подсветка строки при успешном сохранении
                            if (highlightTimeoutRef.current) {
                              window.clearTimeout(highlightTimeoutRef.current);
                            }
                            setHighlightedRowId(row.id);
                            highlightTimeoutRef.current = window.setTimeout(() => {
                              setHighlightedRowId(null);
                            }, 2000);
                          }

                          setEditingCell(null);
                        };

                        const handleCellKeyDown = async (
                          e: React.KeyboardEvent<HTMLInputElement>,
                          row: ActiveFilterRow,
                          field: "delta" | "volume" | "shadow"
                        ) => {
                          if (!editingCell) return;

                          if (e.key === "Enter") {
                            e.preventDefault();
                            await commitInlineEdit(row, field, editingCell.value, editingCell.previousValue);
                          } else if (e.key === "Escape") {
                            e.preventDefault();
                            setEditingCell(null);
                          }
                        };

                        const handleCellBlur = async (
                          row: ActiveFilterRow,
                          field: "delta" | "volume" | "shadow"
                        ) => {
                          if (!editingCell) return;
                          await commitInlineEdit(row, field, editingCell.value, editingCell.previousValue);
                        };

                        return (
                          <div className="mt-2 border border-zinc-800/80 rounded-lg bg-zinc-900/60">
                            <div className="overflow-x-auto rounded-lg">
                              <table className="w-full text-xs md:text-sm border-separate border-spacing-0">
                                <thead className="sticky top-0 z-10 bg-zinc-900/95 backdrop-blur border-b border-zinc-800">
                                  <tr>
                                    <th className="px-3 md:px-4 py-2 md:py-3 text-left font-semibold text-zinc-300 text-xs md:text-sm">
                                      Биржа
                                    </th>
                                    <th className="px-3 md:px-4 py-2 md:py-3 text-left font-semibold text-zinc-300 text-xs md:text-sm">
                                      Рынок
                                    </th>
                                    <th className="px-3 md:px-4 py-2 md:py-3 text-left font-semibold text-zinc-300 text-xs md:text-sm">
                                      Пара
                                    </th>
                                    <th className="px-3 md:px-4 py-2 md:py-3 text-right font-semibold text-zinc-300 text-xs md:text-sm">
                                      Дельта %
                                    </th>
                                    <th className="px-3 md:px-4 py-2 md:py-3 text-right font-semibold text-zinc-300 text-xs md:text-sm">
                                      Объём, USDT
                                    </th>
                                    <th className="px-3 md:px-4 py-2 md:py-3 text-right font-semibold text-zinc-300 text-xs md:text-sm">
                                      Тень %
                                    </th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {rows.map((row, index) => {
                                    const isHighlighted = highlightedRowId === row.id;
                                    return (
                                      <tr
                                        key={row.id}
                                        className={`border-b border-zinc-800/70 transition-colors ${
                                          index % 2 === 0
                                            ? "bg-zinc-900/40"
                                            : "bg-zinc-900/20"
                                        } hover:bg-zinc-800/60 ${
                                          isHighlighted ? "ring-1 ring-emerald-500/60 bg-emerald-500/10" : ""
                                        }`}
                                      >
                                        <td className="px-3 md:px-4 py-2 md:py-2.5 text-white text-xs md:text-sm whitespace-nowrap">
                                          {row.exchangeLabel}
                                        </td>
                                        <td className="px-3 md:px-4 py-2 md:py-2.5 text-xs md:text-sm whitespace-nowrap">
                                          <span
                                            className={`inline-flex items-center px-2 py-0.5 rounded-full border text-[10px] md:text-xs ${
                                              row.marketKey === "spot"
                                                ? "bg-emerald-500/10 border-emerald-500/40 text-emerald-300"
                                                : "bg-blue-500/10 border-blue-500/40 text-blue-300"
                                            }`}
                                          >
                                            {row.marketLabel}
                                          </span>
                                        </td>
                                        <td className="px-3 md:px-4 py-2 md:py-2.5 text-xs md:text-sm text-zinc-200 whitespace-nowrap">
                                          {row.pair ?? "USDT"}
                                        </td>
                                        <td
                                          className="px-3 md:px-4 py-2 md:py-2.5 text-right text-xs md:text-sm text-zinc-100 cursor-pointer"
                                          onClick={() => {
                                            setEditingCell({
                                              rowId: row.id,
                                              field: "delta",
                                              value: row.delta,
                                              previousValue: row.delta,
                                            });
                                          }}
                                        >
                                          {editingCell &&
                                          editingCell.rowId === row.id &&
                                          editingCell.field === "delta" ? (
                                            <input
                                              type="number"
                                              className="w-full px-2 py-1 bg-zinc-800 border border-emerald-500 rounded text-right text-xs md:text-sm text-white focus:outline-none focus:ring-1 focus:ring-emerald-500"
                                              value={editingCell.value}
                                              autoFocus
                                              onChange={(e) =>
                                                setEditingCell((prev) =>
                                                  prev
                                                    ? { ...prev, value: e.target.value }
                                                    : prev
                                                )
                                              }
                                              onBlur={() => handleCellBlur(row, "delta")}
                                              onKeyDown={(e) => handleCellKeyDown(e, row, "delta")}
                                            />
                                          ) : (
                                            formatNumberCompact(row.delta)
                                          )}
                                        </td>
                                        <td
                                          className="px-3 md:px-4 py-2 md:py-2.5 text-right text-xs md:text-sm text-zinc-100 cursor-pointer whitespace-nowrap"
                                          onClick={() => {
                                            setEditingCell({
                                              rowId: row.id,
                                              field: "volume",
                                              value: row.volume,
                                              previousValue: row.volume,
                                            });
                                          }}
                                        >
                                          {editingCell &&
                                          editingCell.rowId === row.id &&
                                          editingCell.field === "volume" ? (
                                            <input
                                              type="number"
                                              className="w-full px-2 py-1 bg-zinc-800 border border-emerald-500 rounded text-right text-xs md:text-sm text-white focus:outline-none focus:ring-1 focus:ring-emerald-500"
                                              value={editingCell.value}
                                              autoFocus
                                              onChange={(e) =>
                                                setEditingCell((prev) =>
                                                  prev
                                                    ? { ...prev, value: e.target.value }
                                                    : prev
                                                )
                                              }
                                              onBlur={() => handleCellBlur(row, "volume")}
                                              onKeyDown={(e) => handleCellKeyDown(e, row, "volume")}
                                            />
                                          ) : (
                                            formatNumberCompact(row.volume)
                                          )}
                                        </td>
                                        <td
                                          className="px-3 md:px-4 py-2 md:py-2.5 text-right text-xs md:text-sm text-zinc-100 cursor-pointer"
                                          onClick={() => {
                                            setEditingCell({
                                              rowId: row.id,
                                              field: "shadow",
                                              value: row.shadow,
                                              previousValue: row.shadow,
                                            });
                                          }}
                                        >
                                          {editingCell &&
                                          editingCell.rowId === row.id &&
                                          editingCell.field === "shadow" ? (
                                            <input
                                              type="number"
                                              className="w-full px-2 py-1 bg-zinc-800 border border-emerald-500 rounded text-right text-xs md:text-sm text-white focus:outline-none focus:ring-1 focus:ring-emerald-500"
                                              value={editingCell.value}
                                              autoFocus
                                              onChange={(e) =>
                                                setEditingCell((prev) =>
                                                  prev
                                                    ? { ...prev, value: e.target.value }
                                                    : prev
                                                )
                                              }
                                              onBlur={() => handleCellBlur(row, "shadow")}
                                              onKeyDown={(e) => handleCellKeyDown(e, row, "shadow")}
                                            />
                                          ) : (
                                            formatNumberCompact(row.shadow)
                                          )}
                                        </td>
                                      </tr>
                                    );
                                  })}
                                </tbody>
                              </table>
                            </div>
                          </div>
                        );
                      })()}
                    </div>
                  </div>
                </>
          </div>
        )}
        
        {/* Стратегии - отдельная подтема */}
        {activeSubTab === "strategies" && (
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
                    const isEnabled = template.enabled !== false; // По умолчанию true
                    const templateDescription = template.description || generateTemplateDescription(template);
                    const templateName = template.name || `Стратегия #${index + 1}`;
                    
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
                                    setConditionalTemplates(newTemplates);
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
                      
                      {/* Галочка "Использовать мои фильтры из глобальных настроек" */}
                      <div className="mb-4 p-3 bg-zinc-900/50 border border-zinc-700/50 rounded-lg">
                        <label className="flex items-start gap-3 cursor-pointer group">
                          <input
                            type="checkbox"
                            checked={template.useGlobalFilters !== false} // По умолчанию true
                            onChange={(e) => {
                              const newTemplates = [...conditionalTemplates];
                              newTemplates[index].useGlobalFilters = e.target.checked;
                              // Если выключаем глобальные фильтры, удаляем базовые фильтры из условий (если они были)
                              if (!e.target.checked) {
                                // Удаляем условия delta, volume, wick_pct, если они есть
                                newTemplates[index].conditions = newTemplates[index].conditions.filter(
                                  cond => cond.type !== "delta" && cond.type !== "volume" && cond.type !== "wick_pct"
                                );
                              } else {
                                // Если включаем глобальные фильтры, очищаем ошибки валидации для этой стратегии
                                const newErrors = { ...strategyValidationErrors };
                                delete newErrors[index];
                                setStrategyValidationErrors(newErrors);
                              }
                              setConditionalTemplates(newTemplates);
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
                                  Если включено: стратегия будет использовать фильтры дельты, объёма и тени из ваших глобальных настроек прострела (exchangeSettings/pairSettings/thresholds).
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
                              <div className="relative">
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
                                    // Ищем существующее условие delta
                                    const deltaIndex = newTemplates[index].conditions.findIndex(c => c.type === "delta");
                                    if (deltaIndex >= 0) {
                                      // Обновляем существующее
                                      newTemplates[index].conditions[deltaIndex].valueMin = val !== undefined && !isNaN(val) ? Math.max(0.01, Math.min(100, val)) : undefined;
                                      newTemplates[index].conditions[deltaIndex].valueMax = null; // Бесконечность
                                    } else {
                                      // Создаём новое условие delta
                                      newTemplates[index].conditions.unshift({
                                        type: "delta",
                                        valueMin: val !== undefined && !isNaN(val) ? Math.max(0.01, Math.min(100, val)) : undefined,
                                        valueMax: null,
                                      });
                                    }
                                    const updatedDescription = generateTemplateDescription(newTemplates[index]);
                                    newTemplates[index].description = updatedDescription;
                                    setConditionalTemplates(newTemplates);
                                    // Очищаем ошибку для этого поля при изменении
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
                                        setStrategyValidationErrors(newErrors);
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
                              </div>
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
                              <div className="relative">
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
                                    // Ищем существующее условие volume
                                    const volumeIndex = newTemplates[index].conditions.findIndex(c => c.type === "volume");
                                    if (volumeIndex >= 0) {
                                      // Обновляем существующее
                                      newTemplates[index].conditions[volumeIndex].value = val !== undefined && !isNaN(val) ? Math.max(1, val) : undefined;
                                    } else {
                                      // Создаём новое условие volume
                                      newTemplates[index].conditions.unshift({
                                        type: "volume",
                                        value: val !== undefined && !isNaN(val) ? Math.max(1, val) : undefined,
                                      });
                                    }
                                    const updatedDescription = generateTemplateDescription(newTemplates[index]);
                                    newTemplates[index].description = updatedDescription;
                                    setConditionalTemplates(newTemplates);
                                    // Очищаем ошибку для этого поля при изменении
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
                                        setStrategyValidationErrors(newErrors);
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
                              </div>
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
                                      // Ищем существующее условие wick_pct
                                      const wickIndex = newTemplates[index].conditions.findIndex(c => c.type === "wick_pct");
                                      if (wickIndex >= 0) {
                                        // Обновляем существующее
                                        newTemplates[index].conditions[wickIndex].valueMin = val !== undefined && !isNaN(val) ? Math.max(0, Math.min(100, val)) : undefined;
                                      } else {
                                        // Создаём новое условие wick_pct
                                        newTemplates[index].conditions.unshift({
                                          type: "wick_pct",
                                          valueMin: val !== undefined && !isNaN(val) ? Math.max(0, Math.min(100, val)) : undefined,
                                          valueMax: null,
                                        });
                                      }
                                      const updatedDescription = generateTemplateDescription(newTemplates[index]);
                                      newTemplates[index].description = updatedDescription;
                                      setConditionalTemplates(newTemplates);
                                      // Очищаем ошибку для этого поля при изменении
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
                                          setStrategyValidationErrors(newErrors);
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
                                        : template.conditions.find(c => c.type === "wick_pct")?.valueMax
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
                                      setConditionalTemplates(newTemplates);
                                    }}
                                    onBlur={(e) => {
                                      if (e.target.value === "" || e.target.value.trim() === "") {
                                        const newTemplates = [...conditionalTemplates];
                                        const wickIndex = newTemplates[index].conditions.findIndex(c => c.type === "wick_pct");
                                        if (wickIndex >= 0) {
                                          newTemplates[index].conditions[wickIndex].valueMax = null;
                                          const updatedDescription = generateTemplateDescription(newTemplates[index]);
                                          newTemplates[index].description = updatedDescription;
                                          setConditionalTemplates(newTemplates);
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
                      
                      {/* Список условий для этой стратегии */}
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
                              setConditionalTemplates(newTemplates);
                            }}
                            className="inline-flex items-center justify-center px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 text-white text-xs font-medium rounded-lg border border-zinc-700 hover:border-emerald-500/60 transition-colors"
                          >
                            <span className="mr-1 text-emerald-400 text-sm">+</span>
                            Добавить условие
                          </button>
                        </div>
                        
                        <div className="space-y-3">
                          {template.conditions.map((condition, condIndex) => (
                            <div
                              key={condIndex}
                              className="bg-zinc-900/50 border border-zinc-700/50 rounded-lg p-3 md:p-4 max-w-4xl"
                            >
                              <div className="flex gap-2 items-end mb-2">
                                <div className="w-full md:w-56">
                                  <label className="block text-xs text-zinc-400 mb-1">Параметр</label>
                                  <select
                                    value={condition.type}
                                    onChange={(e) => {
                                      const newTemplates = [...conditionalTemplates];
                                      const newType = e.target.value as "volume" | "delta" | "series" | "symbol" | "wick_pct" | "exchange_market" | "direction";
                                      newTemplates[index].conditions[condIndex].type = newType;
                                      // Очищаем значения при смене типа
                                      if (newType === "series") {
                                        newTemplates[index].conditions[condIndex].value = undefined;
                                        newTemplates[index].conditions[condIndex].valueMin = undefined;
                                        newTemplates[index].conditions[condIndex].valueMax = undefined;
                                        newTemplates[index].conditions[condIndex].symbol = undefined;
                                        newTemplates[index].conditions[condIndex].exchange_market = undefined;
                                        newTemplates[index].conditions[condIndex].direction = undefined;
                                        newTemplates[index].conditions[condIndex].count = 2;
                                        newTemplates[index].conditions[condIndex].timeWindowSeconds = 300;
                                      } else if (newType === "delta" || newType === "wick_pct") {
                                        // Для дельты и тени используем диапазон
                                        newTemplates[index].conditions[condIndex].count = undefined;
                                        newTemplates[index].conditions[condIndex].timeWindowSeconds = undefined;
                                        newTemplates[index].conditions[condIndex].symbol = undefined;
                                        newTemplates[index].conditions[condIndex].exchange_market = undefined;
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
                                        newTemplates[index].conditions[condIndex].exchange_market = undefined;
                                        newTemplates[index].conditions[condIndex].direction = undefined;
                                        newTemplates[index].conditions[condIndex].symbol = "";
                                      } else if (newType === "exchange_market") {
                                        newTemplates[index].conditions[condIndex].value = undefined;
                                        newTemplates[index].conditions[condIndex].valueMin = undefined;
                                        newTemplates[index].conditions[condIndex].valueMax = undefined;
                                        newTemplates[index].conditions[condIndex].count = undefined;
                                        newTemplates[index].conditions[condIndex].timeWindowSeconds = undefined;
                                        newTemplates[index].conditions[condIndex].symbol = undefined;
                                        newTemplates[index].conditions[condIndex].direction = undefined;
                                        newTemplates[index].conditions[condIndex].exchange_market = "binance_spot";
                                      } else if (newType === "direction") {
                                        newTemplates[index].conditions[condIndex].value = undefined;
                                        newTemplates[index].conditions[condIndex].valueMin = undefined;
                                        newTemplates[index].conditions[condIndex].valueMax = undefined;
                                        newTemplates[index].conditions[condIndex].count = undefined;
                                        newTemplates[index].conditions[condIndex].timeWindowSeconds = undefined;
                                        newTemplates[index].conditions[condIndex].symbol = undefined;
                                        newTemplates[index].conditions[condIndex].exchange_market = undefined;
                                        newTemplates[index].conditions[condIndex].direction = "up";
                                      } else {
                                        // Для объёма - одно значение
                                        newTemplates[index].conditions[condIndex].count = undefined;
                                        newTemplates[index].conditions[condIndex].timeWindowSeconds = undefined;
                                        newTemplates[index].conditions[condIndex].valueMin = undefined;
                                        newTemplates[index].conditions[condIndex].valueMax = undefined;
                                        newTemplates[index].conditions[condIndex].symbol = undefined;
                                        newTemplates[index].conditions[condIndex].exchange_market = undefined;
                                        newTemplates[index].conditions[condIndex].direction = undefined;
                                        newTemplates[index].conditions[condIndex].value = 0;
                                      }
                                      // Обновляем описание стратегии
                                      const updatedDescription = generateTemplateDescription(newTemplates[index]);
                                      newTemplates[index].description = updatedDescription;
                                      setConditionalTemplates(newTemplates);
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
                                          const newTemplates = [...conditionalTemplates];
                                          const val = e.target.value === "" ? 300 : parseInt(e.target.value);
                                          newTemplates[index].conditions[condIndex].timeWindowSeconds = isNaN(val) ? 300 : Math.max(60, val);
                                          const updatedDescription = generateTemplateDescription(newTemplates[index]);
                                          newTemplates[index].description = updatedDescription;
                                          setConditionalTemplates(newTemplates);
                                        }}
                                        className="w-full px-3 py-2.5 bg-zinc-700 border border-zinc-600 rounded-lg text-white text-sm text-center focus:outline-none focus:ring-2 focus:ring-emerald-500"
                                        placeholder="300"
                                      />
                                    </div>
                                  </>
                                ) : condition.type === "delta" ? (
                                  // Для дельты - только минимум, максимум всегда бесконечность
                                  <div className="flex-1">
                                    <label className="block text-xs text-zinc-400 mb-1">Дельта от (%)</label>
                                    <input
                                      type="number"
                                      step="0.1"
                                      min="0"
                                      value={condition.valueMin !== undefined ? condition.valueMin : (condition.value !== undefined ? condition.value : "")}
                                      onChange={(e) => {
                                        const newTemplates = [...conditionalTemplates];
                                        const val = e.target.value === "" ? 0 : parseFloat(e.target.value);
                                        newTemplates[index].conditions[condIndex].valueMin = isNaN(val) ? 0 : val;
                                        // Всегда устанавливаем valueMax = null (бесконечность) для дельты
                                        newTemplates[index].conditions[condIndex].valueMax = null;
                                        // Удаляем старое поле value для обратной совместимости
                                        if (newTemplates[index].conditions[condIndex].value !== undefined) {
                                          delete newTemplates[index].conditions[condIndex].value;
                                        }
                                        const updatedDescription = generateTemplateDescription(newTemplates[index]);
                                        newTemplates[index].description = updatedDescription;
                                        setConditionalTemplates(newTemplates);
                                      }}
                                      className="w-full px-3 py-2.5 bg-zinc-700 border border-zinc-600 rounded-lg text-white text-sm text-center focus:outline-none focus:ring-2 focus:ring-emerald-500"
                                      placeholder="0"
                                    />
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
                                      className="w-40 px-3 py-2 bg-zinc-700 border border-zinc-600 rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
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
                                          className="w-full max-w-[140px] px-3 py-2.5 bg-zinc-700 border border-zinc-600 rounded-lg text-white text-sm text-center focus:outline-none focus:ring-2 focus:ring-emerald-500"
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
                                          className="w-full max-w-[140px] px-3 py-2.5 bg-zinc-700 border border-zinc-600 rounded-lg text-white text-sm text-center focus:outline-none focus:ring-2 focus:ring-emerald-500"
                                          title="Введите число от 0 до 100 или оставьте ∞ для бесконечности"
                                        />
                                      </div>
                                    </div>
                                  </div>
                                ) : condition.type === "exchange_market" ? (
                                  // Для биржи и типа рынка - объединенный выбор
                                  <div className="flex-1">
                                    <label className="block text-xs text-zinc-400 mb-1">Биржа и тип рынка</label>
                                    <select
                                      value={condition.exchange_market || (condition.exchange && condition.market ? `${condition.exchange}_${condition.market === "linear" ? "futures" : condition.market}` : "binance_spot")}
                                      onChange={(e) => {
                                        const newTemplates = [...conditionalTemplates];
                                        newTemplates[index].conditions[condIndex].exchange_market = e.target.value;
                                        // Удаляем старые поля для обратной совместимости
                                        delete newTemplates[index].conditions[condIndex].exchange;
                                        delete newTemplates[index].conditions[condIndex].market;
                                        const updatedDescription = generateTemplateDescription(newTemplates[index]);
                                        newTemplates[index].description = updatedDescription;
                                        setConditionalTemplates(newTemplates);
                                      }}
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
                                      className="w-40 px-3 py-2 bg-zinc-700 border border-zinc-600 rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                                    >
                                      <option value="up">Вверх ⬆️</option>
                                      <option value="down">Вниз ⬇️</option>
                                    </select>
                                  </div>
                                ) : (
                                  // Для объёма - одно значение
                                  <div className="w-full md:w-auto md:min-w-[220px]">
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
                                      className="w-full px-3 py-2.5 bg-zinc-700 border border-zinc-600 rounded-lg text-white text-sm text-center focus:outline-none focus:ring-2 focus:ring-emerald-500"
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
                                onClick={() => {
                                  const editor = document.getElementById(`conditionalTemplate_${index}`) as HTMLElement;
                                  if (editor) {
                                    const selection = window.getSelection();
                                    if (selection && selection.rangeCount > 0) {
                                      const range = selection.getRangeAt(0);
                                      range.deleteContents();

                                      const block = document.createElement("span");
                                      block.className =
                                        "inline-flex items-center gap-1.5 px-2 py-1 mx-0.5 bg-emerald-500/20 border border-emerald-500/50 rounded text-emerald-300 text-xs font-medium cursor-default";
                                      block.setAttribute("data-placeholder-key", placeholder.friendly);
                                      block.setAttribute("contenteditable", "false");
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
                                      newTemplates[index].template = convertToTechnicalKeys(
                                        textContent.replace(/<br\s*\/?>/gi, "\n")
                                      );
                                      setConditionalTemplates(newTemplates);
                                    }
                                  }
                                }}
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
                              // Заменяем HTML-переносы строк на обычные \n
                              textContent = textContent.replace(/<br\s*\/?>/gi, "\n");

                              // Помечаем, что пользователь сейчас редактирует стратегию,
                              // чтобы эффект инициализации не перезатирал содержимое и не сбивал курсор
                              isConditionalUserEditingRef.current = true;

                              const newTemplates = [...conditionalTemplates];
                              newTemplates[index].template = convertToTechnicalKeys(textContent);
                              setConditionalTemplates(newTemplates);

                              // Через небольшой таймаут снимаем флаг редактирования
                              setTimeout(() => {
                                isConditionalUserEditingRef.current = false;
                              }, 150);
                            }}
                            className="w-full min-h-32 px-4 py-3 bg-zinc-800 border-2 border-zinc-600 rounded-lg text-white font-mono text-sm focus:outline-none focus:ring-2 focus:border-emerald-500 focus:ring-emerald-500 resize-none overflow-y-auto template-editor cursor-text"
                            style={{ whiteSpace: "pre-wrap" }}
                          />

                          {/* Emoji Picker для стратегий */}
                          {showEmojiPicker.conditional === index && showEmojiPicker.position && (
                            <>
                              <div
                                className="fixed inset-0 z-40"
                                onClick={() =>
                                  setShowEmojiPicker({ main: false, conditional: null, position: undefined })
                                }
                              />
                              <div
                                className="fixed z-50"
                                style={{
                                  left: `${showEmojiPicker.position.x}px`,
                                  top: `${showEmojiPicker.position.y}px`,
                                }}
                              >
                                <EmojiPicker
                                  onEmojiClick={(emojiData) =>
                                    insertEmoji(emojiData as any, `conditionalTemplate_${index}`, true)
                                  }
                                  theme={"dark" as any}
                                  width={350}
                                  height={400}
                                  previewConfig={{
                                    showPreview: false,
                                  }}
                                />
                              </div>
                            </>
                          )}
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
                          enabled: true, // По умолчанию включена
                          useGlobalFilters: true, // По умолчанию используем глобальные фильтры
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
                    + Добавить стратегию
                  </button>
                  <button
                    onClick={async () => {
                      await saveAllSettings();
                    }}
                    className="px-4 py-2 bg-gradient-to-r from-emerald-500 to-emerald-600 hover:from-emerald-600 hover:to-emerald-700 text-white font-medium rounded-lg smooth-transition ripple hover-glow shadow-emerald"
                  >
                    Сохранить стратегии
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}
        
        {/* Чёрный список монет - отдельная подтема рядом с "Настройки прострелов" */}
        {activeSubTab === "blacklist" && (
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6 mt-6">
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
        )}
      </div>
    </div>
  );
}

