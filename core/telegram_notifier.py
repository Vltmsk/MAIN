"""
Модуль для отправки уведомлений в Telegram
"""
import asyncio
import aiohttp
import re
from typing import Optional, Tuple, List, Dict, Any
from core.candle_builder import Candle
from core.logger import get_logger

logger = get_logger(__name__)


def format_volume_compact(volume: float) -> str:
    """
    Форматирует объём в кратком виде (тысячи, миллионы)
    
    Args:
        volume: Объём в USDT
        
    Returns:
        Строка в формате "1.5K$" или "2.5M$" или "500$"
    """
    if volume >= 1000000:
        millions = volume / 1000000
        if millions >= 100:
            return f"{millions:.0f}M$"
        return f"{millions:.1f}M$"
    elif volume >= 1000:
        thousands = volume / 1000
        if thousands >= 100:
            return f"{thousands:.0f}K$"
        return f"{thousands:.1f}K$"
    return f"{volume:.0f}$"


# ID кастомных emoji из пака https://t.me/addemoji/Strelk167
# Зеленая стрела вверх и красная стрела вниз
# 
# Как получить ID emoji:
# 1. Добавьте пак emoji в Telegram: https://t.me/addemoji/Strelk167
# 2. Отправьте сообщение с кастомным emoji боту @RawDataBot
# 3. Бот вернет JSON с полем "custom_emoji_id" - это и есть нужный ID
# 4. Или используйте метод getCustomEmojiStickers через Bot API
# 
# Если ID не указаны, будут использоваться стандартные emoji (fallback: 🟢/🔴)
CUSTOM_EMOJI_UP_ID = "5285307907448014606"  # ID зеленой стрелы вверх из пака Strelk167
CUSTOM_EMOJI_DOWN_ID = "5287552508896507917"  # ID красной стрелы вниз из пака Strelk167

# Кэш для emoji ID (чтобы не запрашивать каждый раз)
_emoji_id_cache: Dict[str, Optional[str]] = {}


class TelegramNotifier:
    """Класс для отправки уведомлений в Telegram"""
    
    TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/sendMessage"
    TELEGRAM_PHOTO_API_URL = "https://api.telegram.org/bot{token}/sendPhoto"
    TELEGRAM_CUSTOM_EMOJI_API_URL = "https://api.telegram.org/bot{token}/getCustomEmojiStickers"
    
    # Семафор для ограничения параллельных запросов к Telegram API
    # Создаётся семафор на 30, что означает максимум 30 параллельных запросов одновременно
    # (это concurrency limit, а не rate limit - не путать с лимитом "30 сообщений в секунду")
    _rate_limit_semaphore: Optional[asyncio.Semaphore] = None
    _semaphore_lock: Optional[asyncio.Lock] = None
    
    # Переиспользуемая HTTP-сессия для всех запросов
    _http_session: Optional[aiohttp.ClientSession] = None
    _session_lock: Optional[asyncio.Lock] = None
    
    @classmethod
    async def _get_semaphore(cls) -> asyncio.Semaphore:
        """
        Получает или создаёт семафор для rate limit Telegram API.
        Использует блокировку для потокобезопасной инициализации.
        
        Returns:
            asyncio.Semaphore: Семафор на 30 параллельных запросов
        """
        # Двойная проверка с блокировкой для потокобезопасности
        if cls._rate_limit_semaphore is None:
            if cls._semaphore_lock is None:
                cls._semaphore_lock = asyncio.Lock()
            
            async with cls._semaphore_lock:
                # Проверяем ещё раз после получения блокировки
                if cls._rate_limit_semaphore is None:
                    # 30 запросов в секунду = семафор на 30
                    cls._rate_limit_semaphore = asyncio.Semaphore(30)
        
        return cls._rate_limit_semaphore
    
    @classmethod
    async def _get_http_session(cls) -> aiohttp.ClientSession:
        """
        Получает или создаёт переиспользуемую HTTP-сессию для запросов к Telegram API.
        Использует блокировку для потокобезопасной инициализации.
        
        Returns:
            aiohttp.ClientSession: Переиспользуемая HTTP-сессия
        """
        # Двойная проверка с блокировкой для потокобезопасности
        if cls._http_session is None or cls._http_session.closed:
            if cls._session_lock is None:
                cls._session_lock = asyncio.Lock()
            
            async with cls._session_lock:
                # Проверяем ещё раз после получения блокировки
                if cls._http_session is None or cls._http_session.closed:
                    # Создаём сессию с настройками для оптимизации
                    timeout = aiohttp.ClientTimeout(total=7, connect=5)
                    connector = aiohttp.TCPConnector(limit=100, limit_per_host=30)
                    cls._http_session = aiohttp.ClientSession(
                        timeout=timeout,
                        connector=connector
                    )
        
        return cls._http_session
    
    @staticmethod
    async def _get_custom_emoji_id(token: str, emoji_name: str = "up") -> Optional[str]:
        """
        Получает ID кастомного emoji из пака.
        
        Логика работы:
        1. Сначала проверяет глобальные константы CUSTOM_EMOJI_UP_ID и CUSTOM_EMOJI_DOWN_ID (приоритет)
        2. Если константы не установлены, пытается получить через Telegram Bot API (не реализовано полностью)
        
        Args:
            token: Telegram Bot Token
            emoji_name: Название emoji ("up" для зеленой стрелы вверх, "down" для красной вниз)
            
        Returns:
            ID emoji или None если не удалось получить
            
        Примечание:
            Для работы этого метода нужно:
            1. Указать ID вручную через константы CUSTOM_EMOJI_UP_ID и CUSTOM_EMOJI_DOWN_ID (рекомендуется)
            2. Или добавить бота в пак emoji (https://t.me/addemoji/Strelk167) и реализовать получение через Bot API
            3. ID можно получить через @BotFather или из сообщения с кастомным emoji
        """
        global _emoji_id_cache
        
        # Проверяем кэш
        cache_key = f"{token}_{emoji_name}"
        if cache_key in _emoji_id_cache:
            return _emoji_id_cache[cache_key]
        
        # Проверяем глобальные константы (приоритет)
        if emoji_name == "up" and CUSTOM_EMOJI_UP_ID:
            _emoji_id_cache[cache_key] = CUSTOM_EMOJI_UP_ID
            return CUSTOM_EMOJI_UP_ID
        if emoji_name == "down" and CUSTOM_EMOJI_DOWN_ID:
            _emoji_id_cache[cache_key] = CUSTOM_EMOJI_DOWN_ID
            return CUSTOM_EMOJI_DOWN_ID
        
        # Пытаемся получить через Bot API (getCustomEmojiStickers)
        # Это требует, чтобы бот был добавлен в пак emoji
        try:
            url = TelegramNotifier.TELEGRAM_CUSTOM_EMOJI_API_URL.format(token=token)
            session = await TelegramNotifier._get_http_session()
            async with session.post(url, json={"custom_emoji_ids": []}) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("ok") and data.get("result"):
                        # Ищем нужный emoji в результате
                        # Пока возвращаем None, так как нужно знать конкретные ID из пака
                        pass
        except Exception as e:
            logger.debug(f"Не удалось получить emoji ID через Bot API: {e}")
            # Не логируем в БД - это не критичная ошибка
        
        # Если не удалось получить, возвращаем None (будет использован fallback)
        _emoji_id_cache[cache_key] = None
        return None
    
    @staticmethod
    def _format_custom_emoji(emoji_id: Optional[str], fallback_emoji: str) -> str:
        """
        Форматирует кастомное emoji или возвращает fallback
        
        Логика работы:
        1. Сначала пытается использовать кастомное emoji из пака Strelk167
        2. Если кастомное emoji недоступно (ID пустой или пак не установлен у получателя),
           Telegram автоматически покажет fallback emoji (🟢/🔴)
        
        Args:
            emoji_id: ID кастомного emoji из пака Strelk167
            fallback_emoji: Стандартный emoji для fallback (🟢 или 🔴)
            
        Returns:
            Отформатированная строка с кастомным emoji (если доступно) или fallback
        
        Примечание:
            Используется формат Telegram: <tg-emoji emoji-id="{emoji_id}">{fallback_emoji}</tg-emoji>
            Telegram сначала попытается показать кастомное emoji из пака, а если не получится -
            автоматически покажет fallback emoji, указанный внутри тега.
        """
        if emoji_id and emoji_id.strip():  # Проверяем, что ID не пустой
            # Используем формат Telegram для кастомных emoji
            # Telegram сначала попытается показать кастомное emoji из пака
            # Если пак не установлен у получателя, автоматически покажет fallback emoji
            return f'<tg-emoji emoji-id="{emoji_id}">{fallback_emoji}</tg-emoji>'
        else:
            # Если ID не указан, сразу используем стандартный emoji
            return fallback_emoji
    
    @staticmethod
    def _sanitize_html(message: str) -> str:
        """
        Очищает HTML от неподдерживаемых Telegram тегов
        
        Telegram поддерживает только ограниченный набор HTML-тегов:
        - <b>, <strong> - жирный
        - <i>, <em> - курсив
        - <u> - подчеркивание
        - <s>, <strike>, <del> - зачеркивание
        - <code> - моноширинный
        - <pre> - предформатированный текст
        - <a> - ссылка
        - <tg-spoiler> или <span class="tg-spoiler"> - спойлер
        
        Args:
            message: Исходное сообщение с HTML
            
        Returns:
            Очищенное сообщение с только поддерживаемыми тегами
        """
        if not message:
            return message
        
        # Сначала заменяем валидные <span class="tg-spoiler"> на <tg-spoiler> для единообразия
        message = re.sub(
            r'<span\s+class=["\']tg-spoiler["\']\s*>(.*?)</span>',
            r'<tg-spoiler>\1</tg-spoiler>',
            message,
            flags=re.IGNORECASE | re.DOTALL
        )
        
        # Теперь удаляем все оставшиеся <span> теги (оставляем только содержимое)
        # Все валидные спойлеры уже заменены на <tg-spoiler>, поэтому остальные span можно безопасно удалить
        message = re.sub(
            r'<span(?:\s+[^>]*)?>(.*?)</span>',
            r'\1',
            message,
            flags=re.IGNORECASE | re.DOTALL
        )
        
        # Удаляем другие неподдерживаемые теги (div, p, br можно оставить, но лучше удалить для безопасности)
        # Удаляем <div> теги (оставляем содержимое)
        message = re.sub(r'<div(?:\s+[^>]*)?>(.*?)</div>', r'\1', message, flags=re.IGNORECASE | re.DOTALL)
        
        # Удаляем <p> теги, заменяем на перенос строки
        message = re.sub(r'<p(?:\s+[^>]*)?>(.*?)</p>', r'\1\n', message, flags=re.IGNORECASE | re.DOTALL)
        
        # Удаляем одиночные <br> и <br/> (Telegram не поддерживает, используем \n)
        message = re.sub(r'<br\s*/?>', '\n', message, flags=re.IGNORECASE)
        
        return message
    
    @staticmethod
    async def send_message(
        token: str,
        chat_id: str,
        message: str,
        *,
        max_retries: int = 3,
        base_delay: float = 1.0,
    ) -> Tuple[bool, str]:
        """
        Отправляет сообщение в Telegram
        
        Args:
            token: Telegram Bot Token
            chat_id: Telegram Chat ID
            message: Текст сообщения
            max_retries: Максимальное количество попыток отправки (по умолчанию 3)
            base_delay: Базовая задержка между попытками в секундах (по умолчанию 1.0)
            
        Returns:
            tuple[bool, str]: (успех, сообщение_об_ошибке)
        """
        if not token or not chat_id:
            error_msg = "Не указан token или chat_id для отправки сообщения"
            logger.warning(error_msg)
            return False, error_msg
        
        # Очищаем HTML от неподдерживаемых тегов перед отправкой
        sanitized_message = TelegramNotifier._sanitize_html(message)
        
        url = TelegramNotifier.TELEGRAM_API_URL.format(token=token)
        
        payload = {
            "chat_id": chat_id,
            "text": sanitized_message,
            "parse_mode": "HTML"  # Для поддержки HTML разметки
        }
        
        last_error_msg = ""
        semaphore = await TelegramNotifier._get_semaphore()
        session = await TelegramNotifier._get_http_session()
        
        for attempt in range(1, max_retries + 1):
            try:
                async with semaphore:
                    async with session.post(
                        url,
                        json=payload,
                    ) as response:
                            if response.status == 200:
                                logger.info(f"Сообщение успешно отправлено в Telegram (chat_id: {chat_id})")
                                return True, ""
                            
                            # Получаем детали ошибки от Telegram API
                            try:
                                error_data = await response.json()
                                error_description = error_data.get("description", "Unknown error")
                                error_code = error_data.get("error_code", response.status)
                                last_error_msg = f"Telegram API error {error_code}: {error_description}"
                            except Exception:
                                error_text = await response.text()
                                last_error_msg = f"HTTP {response.status}: {error_text[:200]}"

                            # Логические ошибки (например, неверный chat_id, блокировка бота)
                            log_extra = {
                                "log_to_db": True,
                                "error_type": "telegram_error",
                                "market": "telegram",
                                "symbol": chat_id,
                            }
                            # Для промежуточных попыток логируем как warning, финальную - как error
                            if attempt < max_retries:
                                logger.warning(
                                    f"Ошибка отправки в Telegram (попытка {attempt}/{max_retries}): {last_error_msg}",
                                    extra=log_extra,
                                )
                            else:
                                logger.error(
                                    f"Ошибка отправки в Telegram после {attempt} попыток: {last_error_msg}",
                                    extra=log_extra,
                                )
                            return False, last_error_msg
            except asyncio.TimeoutError:
                last_error_msg = "Таймаут при подключении к Telegram API (проверьте интернет-соединение)"
                # Таймауты считаем временными сетевыми ошибками
                log_extra = {
                    "log_to_db": attempt == max_retries,
                    "error_type": "telegram_timeout",
                    "market": "telegram",
                    "symbol": chat_id,
                }
                log_func = logger.warning if attempt < max_retries else logger.error
                log_func(
                    f"{last_error_msg} (попытка {attempt}/{max_retries})",
                    extra=log_extra,
                )
            except aiohttp.ClientError as e:
                last_error_msg = f"Ошибка сети при отправке в Telegram: {str(e)}"
                log_extra = {
                    "log_to_db": attempt == max_retries,
                    "error_type": "telegram_network_error",
                    "market": "telegram",
                    "symbol": chat_id,
                }
                log_func = logger.warning if attempt < max_retries else logger.error
                log_func(
                    f"{last_error_msg} (попытка {attempt}/{max_retries})",
                    extra=log_extra,
                )
            except Exception as e:
                last_error_msg = f"Неожиданная ошибка при отправке в Telegram: {str(e)}"
                log_extra = {
                    "log_to_db": True,
                    "error_type": "telegram_error",
                    "market": "telegram",
                    "symbol": chat_id,
                }
                logger.error(last_error_msg, exc_info=True, extra=log_extra)
                return False, last_error_msg
            
            # Экспоненциальная задержка между попытками при временных ошибках
            if attempt < max_retries:
                delay = base_delay * (2 ** (attempt - 1))
                await asyncio.sleep(delay)
        
        # Если дошли сюда, все попытки исчерпаны
        return False, last_error_msg
    
    @staticmethod
    async def _check_condition(condition: Dict[str, Any], delta: float, volume_usdt: float, wick_pct: float,
                        candle: Optional[Candle] = None, user_id: Optional[int] = None,
                        all_conditions: Optional[List[Dict[str, Any]]] = None) -> bool:
        """
        Проверяет условие для условного шаблона
        
        **Расширяемость:** Для добавления нового типа условия:
        1. Добавьте новый elif блок в этом методе с проверкой `cond_type == "new_type"`
        2. Реализуйте логику проверки условия
        3. Новое условие автоматически будет работать в стратегиях, так как `_check_strategy_conditions()` 
           в `spike_detector.py` использует этот метод
        
        Поддерживаемые типы условий:
        - "volume": проверка объёма (volume_usdt >= value)
        - "delta": проверка дельты (valueMin <= delta <= valueMax)
        - "wick_pct": проверка тени (wick_pct >= valueMin)
        - "series": проверка серии стрел (count >= condition.count за timeWindowSeconds)
        - "symbol": проверка символа (с нормализацией)
        - "exchange_market": проверка биржи и рынка
        - "direction": проверка направления стрелы ("up" или "down")
        
        Args:
            condition: Словарь с условием {type: "volume"|"delta"|"series", operator: ">=", value: number, timeWindowSeconds?: number, count?: number}
            delta: Дельта в процентах
            volume_usdt: Объём в USDT
            wick_pct: Процент тени (не используется, но оставлен для совместимости)
            candle: Свеча (нужна для проверки серий)
            user_id: ID пользователя (нужен для проверки серий)
            all_conditions: Все условия из шаблона (нужно для проверки серий, чтобы учитывать условия volume и delta)
            
        Returns:
            bool: True если условие выполнено
        """
        try:
            cond_type = condition.get("type")
            operator = condition.get("operator", ">=")  # По умолчанию >=
            value = condition.get("value")
            
            if not cond_type:
                return False
            
            # Проверка типа "series" (серия стрел)
            if cond_type == "series":
                if candle is None or user_id is None:
                    logger.warning("Для проверки серии нужны candle и user_id")
                    return False
                
                count = condition.get("count")
                time_window_seconds = condition.get("timeWindowSeconds")
                
                if count is None or time_window_seconds is None:
                    logger.warning("Для типа 'series' нужны параметры 'count' и 'timeWindowSeconds'")
                    return False
                
                # Получаем количество стрел за временное окно
                # Передаем все условия из шаблона, чтобы фильтровать только те стрелы,
                # которые соответствуют условиям volume и delta
                from core.spike_detector import spike_detector
                series_count = spike_detector.get_series_count(user_id, candle, time_window_seconds, all_conditions)
                
                # Проверяем условие (>= count)
                return series_count >= count
            
            # Обычные условия (volume, delta)
            # Для дельты может быть диапазон (valueMin, valueMax), для объёма - одно значение (value)
            if cond_type == "volume":
                if value is None:
                    return False
                # Для объёма - проверка >= value
                return volume_usdt >= value
            elif cond_type == "delta":
                # Для дельты - поддержка диапазона (valueMin, valueMax) или старого формата (value)
                value_min = condition.get("valueMin")
                value_max = condition.get("valueMax")
                
                # Поддержка старого формата для обратной совместимости
                if value_min is None and value is not None:
                    # Старый формат: используем value как минимальное значение
                    value_min = value
                    value_max = None  # Бесконечность
                
                if value_min is None:
                    return False
                
                # Проверяем минимальное значение
                if delta < value_min:
                    return False
                
                # Проверяем максимальное значение, если оно указано (не None)
                if value_max is not None and delta > value_max:
                    return False
                
                return True
            elif cond_type == "symbol":
                # Проверка условия по символу (с нормализацией)
                if candle is None:
                    return False
                
                condition_symbol = condition.get("value") or condition.get("symbol")
                if not condition_symbol:
                    return False
                
                # Нормализуем символ из условия
                from core.symbol_utils import normalize_symbol, is_normalized, symbols_match
                
                # Нормализуем символ свечи
                candle_symbol_normalized = await normalize_symbol(
                    candle.symbol,
                    candle.exchange,
                    candle.market
                )
                
                # Нормализуем символ из условия (если он не нормализован)
                condition_symbol_normalized = condition_symbol.upper()
                if not is_normalized(condition_symbol):
                    # Пытаемся нормализовать символ из условия
                    # Используем биржу и рынок свечи
                    try:
                        condition_symbol_normalized = await normalize_symbol(
                            condition_symbol,
                            candle.exchange,
                            candle.market
                        )
                    except Exception as e:
                        logger.debug(f"Не удалось нормализовать символ из условия: {e}")
                        # Если не удалось нормализовать, используем прямое сравнение
                        condition_symbol_normalized = condition_symbol.upper()
                
                # Сравниваем нормализованные символы
                return candle_symbol_normalized == condition_symbol_normalized
            elif cond_type == "wick_pct":
                # Проверка условия по тени свечи (только от)
                value_min = condition.get("valueMin")
                
                if value_min is None:
                    return False
                
                # Проверяем минимальное значение
                if wick_pct < value_min:
                    return False
                
                return True
            elif cond_type == "exchange_market":
                # Проверка условия по бирже и типу рынка (объединенное условие)
                if candle is None:
                    return False
                
                condition_exchange_market = condition.get("exchange_market")
                if condition_exchange_market:
                    # Новый формат: "exchange_market" (например, "binance_spot", "bybit_futures")
                    parts = condition_exchange_market.lower().split("_", 1)
                    if len(parts) != 2:
                        return False
                    
                    condition_exchange, condition_market = parts
                    
                    # Нормализуем рынок: "futures" и "linear" - одно и то же
                    if condition_market == "linear":
                        condition_market = "futures"
                    
                    # Сравниваем биржу
                    if candle.exchange.lower() != condition_exchange.lower():
                        return False
                    
                    # Нормализуем и сравниваем тип рынка
                    market_mapping = {
                        "futures": "linear",  # Futures и Linear - одно и то же
                        "linear": "linear",
                        "spot": "spot"
                    }
                    
                    candle_market = market_mapping.get(candle.market.lower(), candle.market.lower())
                    condition_market_normalized = market_mapping.get(condition_market.lower(), condition_market.lower())
                    
                    return candle_market == condition_market_normalized
                
                # Обратная совместимость: проверяем старый формат (отдельные поля exchange и market)
                condition_exchange = condition.get("exchange")
                condition_market = condition.get("market")
                
                if condition_exchange:
                    # Проверяем биржу
                    if candle.exchange.lower() != condition_exchange.lower():
                        return False
                
                if condition_market:
                    # Проверяем тип рынка
                    market_mapping = {
                        "futures": "linear",  # Futures и Linear - одно и то же
                        "linear": "linear",
                        "spot": "spot"
                    }
                    
                    candle_market = market_mapping.get(candle.market.lower(), candle.market.lower())
                    condition_market_normalized = market_mapping.get(condition_market.lower(), condition_market.lower())
                    
                    if candle_market != condition_market_normalized:
                        return False
                
                # Если указаны оба условия - оба должны совпадать
                # Если указано только одно - проверяем только его
                return condition_exchange is not None or condition_market is not None
            elif cond_type == "direction":
                # Проверка условия по направлению стрелы
                if candle is None:
                    return False
                
                condition_direction = condition.get("direction")
                if not condition_direction:
                    return False
                
                # Определяем направление свечи
                is_up = candle.close > candle.open
                candle_direction = "up" if is_up else "down"
                
                return candle_direction == condition_direction.lower()
            else:
                logger.warning(f"Неизвестный тип условия: {cond_type}")
                return False
        except Exception as e:
            logger.warning(f"Ошибка при проверке условия: {e}", extra={
                "log_to_db": True,
                "error_type": "template_condition_error",
                "market": "telegram",
            })
            return False
    
    @staticmethod
    async def _select_templates(delta: float, wick_pct: float, volume_usdt: float,
                        conditional_templates: Optional[List[Dict[str, Any]]] = None,
                        default_template: Optional[str] = None,
                        candle: Optional[Candle] = None,
                        user_id: Optional[int] = None,
                        default_chat_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Выбирает все подходящие шаблоны на основе условий из conditionalTemplates
        
        Args:
            delta: Дельта в процентах
            wick_pct: Процент тени
            volume_usdt: Объём в USDT
            conditional_templates: Список условных шаблонов
            default_template: Шаблон по умолчанию (messageTemplate)
            candle: Свеча (нужна для проверки серий)
            user_id: ID пользователя (нужен для проверки серий)
            default_chat_id: Основной Chat ID пользователя (используется если в условии не указан отдельный)
            
        Returns:
            List[Dict[str, Any]]: Список словарей с ключами 'template' и 'chatId' для всех подходящих шаблонов
        """
        matched_templates = []
        
        # Проверяем все условные шаблоны
        if conditional_templates:
            for cond_template in conditional_templates:
                try:
                    # Проверяем флаг enabled (по умолчанию true, если не указан)
                    enabled = cond_template.get("enabled")
                    if enabled is False:
                        continue  # Пропускаем выключенные шаблоны
                    
                    conditions = cond_template.get("conditions")  # Новый формат: массив условий
                    # Миграция: поддерживаем старый формат с одним condition
                    if not conditions:
                        condition = cond_template.get("condition")
                        if condition:
                            conditions = [condition]
                    
                    template = cond_template.get("template")
                    
                    if conditions and template:
                        # Проверяем все условия - все должны выполняться (AND логика)
                        # Передаем все условия в _check_condition, чтобы при проверке серии
                        # учитывались условия volume и delta
                        all_conditions_met = True
                        
                        for condition in conditions:
                            if not await TelegramNotifier._check_condition(condition, delta, volume_usdt, wick_pct, candle, user_id, conditions):
                                all_conditions_met = False
                                break
                        
                        if all_conditions_met:
                            logger.debug(f"Найден подходящий условный шаблон: {conditions}")
                            # Используем Chat ID из шаблона, если указан, иначе основной
                            template_chat_id = cond_template.get("chatId")
                            chat_id = template_chat_id if template_chat_id else default_chat_id
                            matched_templates.append({
                                "template": template,
                                "chatId": chat_id
                            })
                except Exception as e:
                    logger.warning(f"Ошибка при обработке условного шаблона: {e}", extra={
                        "log_to_db": True,
                        "error_type": "template_processing_error",
                        "market": "telegram",
                    })
                    continue
        
        # Если найдены подходящие условные шаблоны, возвращаем их
        if matched_templates:
            return matched_templates
        
        # Если не найдено подходящих условных шаблонов, возвращаем дефолтный
        # ВАЖНО: Если default_template пустой или None, возвращаем пустой список
        # Дефолтный шаблон будет создан в format_spike_messages, если messages пустой
        if default_template and default_template.strip():
            return [{
                "template": default_template,
                "chatId": default_chat_id
            }]
        
        # Если default_template пустой, возвращаем пустой список
        # format_spike_messages создаст дефолтный шаблон, если messages пустой
        return []
    
    @staticmethod
    async def format_spike_messages(candle: Candle, delta: float, wick_pct: float, volume_usdt: float, 
                            template: Optional[str] = None,
                            conditional_templates: Optional[List[Dict[str, Any]]] = None,
                            user_id: Optional[int] = None,
                            token: Optional[str] = None,
                            timezone: str = "UTC",
                            default_chat_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Форматирует все подходящие сообщения о найденной стреле
        
        Args:
            candle: Свеча
            delta: Дельта в процентах
            wick_pct: Процент тени
            volume_usdt: Объём в USDT
            template: Пользовательский шаблон сообщения (опционально, дефолтный)
            conditional_templates: Список условных шаблонов с условиями
            user_id: ID пользователя (нужен для проверки серий)
            timezone: Временная зона пользователя (по умолчанию UTC)
            default_chat_id: Основной Chat ID пользователя (используется если в условии не указан отдельный)
            
        Returns:
            List[Dict[str, Any]]: Список словарей с ключами 'message' и 'chatId' для всех отформатированных сообщений
        """
        from datetime import datetime
        import pytz
        
        # Форматируем время в указанной временной зоне
        timestamp = candle.ts_ms / 1000
        try:
            # Создаем datetime объект из timestamp
            dt_utc = datetime.fromtimestamp(timestamp, tz=pytz.UTC)
            
            # Конвертируем в указанную временную зону
            if timezone and timezone != "UTC":
                try:
                    user_tz = pytz.timezone(timezone)
                    dt_local = dt_utc.astimezone(user_tz)
                except Exception as e:
                    logger.debug(f"Не удалось конвертировать в timezone {timezone}, используем UTC: {e}")
                    dt_local = dt_utc
            else:
                dt_local = dt_utc
            
            # Форматируем время
            time_str = dt_local.strftime("%d.%m.%y %H:%M:%S")
        except Exception as e:
            logger.debug(f"Ошибка при форматировании времени: {e}, используем UTC")
            # Не логируем в БД - это не критичная ошибка, есть fallback
            time_str = datetime.fromtimestamp(timestamp).strftime("%d.%m.%y %H:%M:%S")
        
        # Определяем направление стрелы с использованием кастомных emoji
        is_up = candle.close > candle.open
        direction_text = "ВЫРОС" if is_up else "УПАЛ"
        
        # Используем кастомные emoji из пака Strelk167 (https://t.me/addemoji/Strelk167)
        # Сначала пытаемся использовать кастомные эмодзи, если не получится - используем стандартные 🟢/🔴
        # Получаем ID кастомных emoji из констант
        if is_up:
            emoji_id = CUSTOM_EMOJI_UP_ID
        else:
            emoji_id = CUSTOM_EMOJI_DOWN_ID
        
        # Форматируем emoji: сначала кастомные из пака, если недоступны - стандартные Telegram эмодзи 🟢/🔴
        fallback_emoji = "🟢" if is_up else "🔴"
        direction_emoji = TelegramNotifier._format_custom_emoji(emoji_id, fallback_emoji)
        
        # Форматируем числа
        delta_formatted = f"{delta:.2f}%"
        volume_formatted = format_volume_compact(volume_usdt)
        wick_formatted = f"{wick_pct:.1f}%"
        
        # Цветные эмодзи для бирж
        exchange_emoji = {
            "binance": "🟡",
            "gate": "🔵",
            "bitget": "🟢",
            "bybit": "🟠",
        }
        emoji = exchange_emoji.get(candle.exchange.lower(), "⚪")
        
        # Тип рынка
        market_text = "SPOT" if candle.market == "spot" else "FUTURES"
        
        # Сокращения бирж для короткой версии
        exchange_short_map = {
            "binance": "Bin",
            "bybit": "Byb",
            "bitget": "Bit",
            "gate": "Gate",
            "hyperliquid": "Hyper",
        }
        exchange_short = exchange_short_map.get(candle.exchange.lower(), candle.exchange.upper()[:4])
        
        # Сокращение типа рынка для короткой версии
        market_short = "_S" if candle.market == "spot" else "_F"
        exchange_market_short = f"{exchange_short}{market_short}"
        
        # Получаем символ с торговой парой для плейсхолдеров (например, "BTC-USDT")
        from core.symbol_utils import get_symbol_with_pair
        symbol_with_pair = await get_symbol_with_pair(
            candle.symbol,
            candle.exchange,
            candle.market
        )
        
        # Подготовка замен плейсхолдеров
        replacements = [
            ("{delta_formatted}", delta_formatted),
            ("{volume_formatted}", volume_formatted),
            ("{wick_formatted}", wick_formatted),
            ("{timestamp}", str(candle.ts_ms)),
            ("{direction}", direction_emoji),  # Используем emoji (кастомное или fallback)
            ("{exchange_market}", f"{candle.exchange.upper()} | {market_text}"),  # Объединенная вставка (длинная)
            ("{exchange_market_short}", exchange_market_short),  # Короткая версия (например, "Bin_S", "Byb_F")
            ("{exchange}", candle.exchange.upper()),  # Оставляем для обратной совместимости
            ("{symbol}", symbol_with_pair),  # Используем символ с торговой парой (например, "BTC-USDT")
            ("{market}", market_text),  # Оставляем для обратной совместимости
            ("{time}", time_str),
        ]
        
        # Выбираем все подходящие шаблоны с Chat ID
        selected_templates = await TelegramNotifier._select_templates(
            delta, wick_pct, volume_usdt, conditional_templates, template, candle, user_id, default_chat_id
        )
        
        # Форматируем все шаблоны
        messages = []
        for template_info in selected_templates:
            template_text = template_info.get("template", "")
            chat_id = template_info.get("chatId", default_chat_id)
            message = template_text
            
            # Заменяем плейсхолдеры
            for placeholder, value in replacements:
                message = message.replace(placeholder, value)
            
            messages.append({
                "message": message.strip(),
                "chatId": chat_id
            })
        
        # Если нет подходящих шаблонов, используем дефолтный
        if not messages:
            # Проверяем, что default_chat_id не пустой и не None
            if default_chat_id and default_chat_id.strip():
                default_message = f"""
🚨 <b>НАЙДЕНА СТРЕЛА!</b> {direction_emoji}

<b>{candle.exchange.upper()} | {market_text}</b>
💰 <b>{symbol_with_pair}</b>

📊 <b>Метрики:</b>
• Изменение: <b>{delta_formatted}</b> {direction_emoji}
• Объём: <b>{volume_formatted}</b>
• Тень: <b>{wick_formatted}</b>

⏰ <b>{time_str}</b>
                """.strip()
                messages.append({
                    "message": default_message,
                    "chatId": default_chat_id
                })
            else:
                logger.warning(f"Не удалось создать дефолтное сообщение: default_chat_id не указан или пустой для {candle.exchange} {candle.market} {candle.symbol}")
        
        return messages
    
    @staticmethod
    async def notify_spike(candle: Candle, token: str, chat_id: str, 
                          delta: float, wick_pct: float, volume_usdt: float,
                          template: Optional[str] = None,
                          conditional_templates: Optional[List[Dict[str, Any]]] = None,
                          user_id: Optional[int] = None,
                          timezone: str = "UTC") -> Tuple[bool, str]:
        """
        Отправляет все подходящие уведомления о найденной стреле
        
        Args:
            candle: Свеча
            token: Telegram Bot Token
            chat_id: Telegram Chat ID (основной, используется если в условии не указан отдельный)
            delta: Дельта в процентах
            wick_pct: Процент тени
            volume_usdt: Объём в USDT
            template: Пользовательский шаблон сообщения (опционально, дефолтный)
            conditional_templates: Список условных шаблонов с условиями
            user_id: ID пользователя (нужен для проверки серий в условных шаблонах)
            timezone: Временная зона пользователя (по умолчанию UTC)
            
        Returns:
            tuple[bool, str]: (успех, сообщение_об_ошибке)
        """
        messages = await TelegramNotifier.format_spike_messages(
            candle, delta, wick_pct, volume_usdt, template, conditional_templates, user_id, token, timezone, chat_id
        )
        
        # Отправляем все подходящие сообщения в соответствующие чаты
        # Если детект подходит под несколько условных шаблонов с разными Chat ID - отправляем во все указанные чаты
        # Если несколько шаблонов имеют одинаковый Chat ID - отправляем все сообщения в этот чат
        success = True
        error_message = ""
        
        for msg_info in messages:
            message_text = msg_info.get("message", "")
            target_chat_id = msg_info.get("chatId") or chat_id  # Используем Chat ID из условия или основной
            
            if target_chat_id:
                msg_success, msg_error = await TelegramNotifier.send_message(token, target_chat_id, message_text)
                if not msg_success:
                    success = False
                    if error_message:
                        error_message += "; "
                    error_message += f"Chat {target_chat_id}: {msg_error}"
            else:
                logger.warning(f"Не указан Chat ID для отправки сообщения")
                success = False
                if error_message:
                    error_message += "; "
                error_message += "Не указан Chat ID"
        
        return success, error_message
    
    @staticmethod
    async def send_photo(
        token: str,
        chat_id: str,
        photo_bytes: bytes,
        caption: Optional[str] = None,
        *,
        max_retries: int = 3,
        base_delay: float = 1.0,
    ) -> Tuple[bool, str]:
        """
        Отправляет фото в Telegram
        
        Args:
            token: Telegram Bot Token
            chat_id: Telegram Chat ID
            photo_bytes: Байты изображения
            caption: Подпись к фото (опционально)
            
        Returns:
            tuple[bool, str]: (успех, сообщение_об_ошибке)
        """
        if not token or not chat_id:
            error_msg = "Не указан token или chat_id для отправки фото"
            logger.warning(error_msg)
            return False, error_msg
        
        if not photo_bytes:
            error_msg = "Пустые байты изображения"
            logger.warning(error_msg)
            return False, error_msg
        
        url = TelegramNotifier.TELEGRAM_PHOTO_API_URL.format(token=token)
        
        last_error_msg = ""
        semaphore = await TelegramNotifier._get_semaphore()
        session = await TelegramNotifier._get_http_session()
        
        for attempt in range(1, max_retries + 1):
            # Формируем FormData внутри цикла, так как его нельзя переиспользовать
            form_data = aiohttp.FormData()
            form_data.add_field("chat_id", chat_id)
            form_data.add_field("photo", photo_bytes, filename="chart.png", content_type="image/png")
            if caption:
                # Очищаем HTML от неподдерживаемых тегов перед отправкой
                sanitized_caption = TelegramNotifier._sanitize_html(caption)
                form_data.add_field("caption", sanitized_caption)
                form_data.add_field("parse_mode", "HTML")
            
            try:
                async with semaphore:
                    async with session.post(
                        url,
                        data=form_data,
                    ) as response:
                            if response.status == 200:
                                logger.info(f"Фото успешно отправлено в Telegram (chat_id: {chat_id})")
                                return True, ""
                            
                            # Получаем детали ошибки от Telegram API
                            try:
                                error_data = await response.json()
                                error_description = error_data.get("description", "Unknown error")
                                error_code = error_data.get("error_code", response.status)
                                last_error_msg = f"Telegram API error {error_code}: {error_description}"
                            except Exception:
                                error_text = await response.text()
                                last_error_msg = f"HTTP {response.status}: {error_text[:200]}"

                            log_extra = {
                                "log_to_db": True,
                                "error_type": "telegram_error",
                                "market": "telegram",
                                "symbol": chat_id,
                            }
                            if attempt < max_retries:
                                logger.warning(
                                    f"Ошибка отправки фото в Telegram (попытка {attempt}/{max_retries}): {last_error_msg}",
                                    extra=log_extra,
                                )
                            else:
                                logger.error(
                                    f"Ошибка отправки фото в Telegram после {attempt} попыток: {last_error_msg}",
                                    extra=log_extra,
                                )
                            return False, last_error_msg
            except asyncio.TimeoutError:
                last_error_msg = "Таймаут при подключении к Telegram API (проверьте интернет-соединение)"
                log_extra = {
                    "log_to_db": attempt == max_retries,
                    "error_type": "telegram_timeout",
                    "market": "telegram",
                    "symbol": chat_id,
                }
                log_func = logger.warning if attempt < max_retries else logger.error
                log_func(
                    f"{last_error_msg} (попытка {attempt}/{max_retries})",
                    extra=log_extra,
                )
            except aiohttp.ClientError as e:
                last_error_msg = f"Ошибка сети при отправке фото в Telegram: {str(e)}"
                log_extra = {
                    "log_to_db": attempt == max_retries,
                    "error_type": "telegram_network_error",
                    "market": "telegram",
                    "symbol": chat_id,
                }
                log_func = logger.warning if attempt < max_retries else logger.error
                log_func(
                    f"{last_error_msg} (попытка {attempt}/{max_retries})",
                    extra=log_extra,
                )
            except Exception as e:
                last_error_msg = f"Неожиданная ошибка при отправке фото в Telegram: {str(e)}"
                log_extra = {
                    "log_to_db": True,
                    "error_type": "telegram_error",
                    "market": "telegram",
                    "symbol": chat_id,
                }
                logger.error(last_error_msg, exc_info=True, extra=log_extra)
                return False, last_error_msg
            
            if attempt < max_retries:
                delay = base_delay * (2 ** (attempt - 1))
                await asyncio.sleep(delay)
        
        return False, last_error_msg
    
    @staticmethod
    async def send_test_message(token: str, chat_id: str) -> Tuple[bool, str]:
        """
        Отправляет тестовое сообщение в Telegram
        
        Args:
            token: Telegram Bot Token
            chat_id: Telegram Chat ID
            
        Returns:
            tuple[bool, str]: (успех, сообщение_об_ошибке)
        """
        message = """
✅ <b>Тестовое сообщение</b>

Уведомления из системы детекта стрел настроены правильно!

Вы будете получать уведомления когда система найдёт свечу, соответствующую вашим фильтрам.
        """.strip()
        
        return await TelegramNotifier.send_message(token, chat_id, message)


# Глобальный экземпляр нотификатора
telegram_notifier = TelegramNotifier()

