"""
Модуль для нормализации символов торговых пар
Извлекает базовую монету из символа для всех бирж
"""
import re
from typing import Optional, List, Set
from core.logger import get_logger
from BD.symbol_normalization_db import symbol_normalization_db

logger = get_logger(__name__)

# Список котируемых валют для всех бирж
# Расширяемый список, который можно обновлять при добавлении новых бирж
QUOTE_CURRENCIES: Set[str] = {
    # Стандартные
    "USDT", "USDC", "BTC", "ETH", "BNB",
    # Фиатные
    "TRY", "EUR", "GBP", "AUD", "BRL", "BIDR", "AEUR",
    # Другие криптовалюты
    "TRX", "DOGE", "TUSD", "FDUSD",
    # Добавляем другие по мере необходимости
}

# Форматы разделителей для разных бирж
SEPARATORS = ["_", "-", "/"]


def _extract_base_currency_algorithmic(symbol: str, exchange: str, market: str) -> Optional[str]:
    """
    Алгоритмическая нормализация символа (извлечение базовой монеты)
    
    Args:
        symbol: Оригинальный символ (например, BTCUSDT, ETH_USDT, BTC/USDC)
        exchange: Название биржи
        market: Тип рынка (spot/linear)
        
    Returns:
        Нормализованный символ (базовая монета) или None если не удалось определить
    
    Примечание:
        Для Hyperliquid выполняется специальная обработка:
        - Для linear рынка символы уже нормализованы (BTC, ETH, ADA и т.д.)
        - Для spot рынка может быть два формата:
          1. С разделителем "/": PURR/USDC, BTC/USDC
          2. Слитный формат: TNSRUSDC, XPLUSDC, STRKUSDC
    """
    if not symbol:
        return None
    
    # Если символ уже короткий (например, BTC, ETH для Hyperliquid linear), возвращаем как есть
    if len(symbol) <= 6 and not any(sep in symbol for sep in SEPARATORS):
        # Проверяем, не является ли это котируемой валютой
        if symbol.upper() not in QUOTE_CURRENCIES:
            return symbol.upper()
    
    symbol_upper = symbol.upper()
    
    # Специальная обработка для Hyperliquid
    if exchange.lower() == "hyperliquid":
        if market == "linear":
            # Для linear на Hyperliquid символы уже нормализованы (BTC, ETH, ADA и т.д.)
            # Проверяем, что это не котируемая валюта
            if symbol_upper not in QUOTE_CURRENCIES:
                return symbol_upper
        elif market == "spot":
            # Для spot на Hyperliquid может быть два формата:
            # 1. С разделителем: PURR/USDC, BTC/USDC
            # 2. Слитный формат: TNSRUSDC, XPLUSDC, STRKUSDC
            if "/" in symbol_upper:
                parts = symbol_upper.split("/")
                if len(parts) == 2:
                    base = parts[0]
                    quote = parts[1]
                    # Проверяем, что quote - это котируемая валюта
                    if quote in QUOTE_CURRENCIES:
                        return base
            # Для слитного формата (TNSRUSDC, XPLUSDC) ищем котируемую валюту в конце
            # Ищем самую длинную котируемую валюту, которая совпадает с концом символа
            matched_quote = None
            max_length = 0
            
            for quote in QUOTE_CURRENCIES:
                if symbol_upper.endswith(quote) and len(quote) > max_length:
                    matched_quote = quote
                    max_length = len(quote)
            
            if matched_quote:
                base = symbol_upper[:-len(matched_quote)]
                if base and len(base) >= 2:
                    return base
            
            # Если не удалось определить, пробуем стандартную обработку
            return _extract_base_standard(symbol_upper)
    
    # Стандартная обработка для всех остальных бирж
    return _extract_base_standard(symbol_upper)


def _extract_base_standard(symbol: str) -> Optional[str]:
    """
    Стандартная обработка символа (для Binance, Gate, Bitget, Bybit)
    
    Args:
        symbol: Символ в верхнем регистре
        
    Returns:
        Базовая монета или None
    """
    # Сначала пробуем найти разделители
    for sep in SEPARATORS:
        if sep in symbol:
            parts = symbol.split(sep)
            if len(parts) >= 2:
                # Берем первую часть как базовую монету
                base = parts[0]
                quote = parts[1] if len(parts) > 1 else ""
                # Проверяем, что quote - это котируемая валюта
                if quote in QUOTE_CURRENCIES:
                    return base
                # Если quote не распознан, но base выглядит как валидная монета, возвращаем base
                if base and len(base) >= 2:
                    return base
    
    # Если разделителей нет, пробуем найти котируемую валюту в конце
    # Ищем самую длинную котируемую валюту, которая совпадает с концом символа
    matched_quote = None
    max_length = 0
    
    for quote in QUOTE_CURRENCIES:
        if symbol.endswith(quote) and len(quote) > max_length:
            matched_quote = quote
            max_length = len(quote)
    
    if matched_quote:
        base = symbol[:-len(matched_quote)]
        if base and len(base) >= 2:
            return base
    
    # Если не удалось определить, возвращаем исходный символ (может быть уже нормализован)
    # Но только если он не слишком длинный
    if len(symbol) <= 10:
        return symbol
    
    # В крайнем случае возвращаем None
    logger.warning(f"Не удалось нормализовать символ: {symbol}")
    return None


def _extract_quote_currency(symbol: str) -> Optional[str]:
    """
    Извлекает котируемую валюту из символа
    
    Args:
        symbol: Символ в верхнем регистре
        
    Returns:
        Котируемая валюта или None
    """
    symbol_upper = symbol.upper()
    
    # Сначала пробуем найти разделители
    for sep in SEPARATORS:
        if sep in symbol_upper:
            parts = symbol_upper.split(sep)
            if len(parts) >= 2:
                quote = parts[1] if len(parts) > 1 else ""
                # Проверяем, что quote - это котируемая валюта
                if quote in QUOTE_CURRENCIES:
                    return quote
    
    # Если разделителей нет, пробуем найти котируемую валюту в конце
    # Ищем самую длинную котируемую валюту, которая совпадает с концом символа
    matched_quote = None
    max_length = 0
    
    for quote in QUOTE_CURRENCIES:
        if symbol_upper.endswith(quote) and len(quote) > max_length:
            matched_quote = quote
            max_length = len(quote)
    
    if matched_quote:
        return matched_quote
    
    return None


async def get_quote_currency(symbol: str, exchange: str, market: str) -> Optional[str]:
    """
    Извлекает котируемую валюту из символа торговой пары
    
    Args:
        symbol: Символ торговой пары (например, BTCUSDT, ETH_USDT, BTC/USDC)
        exchange: Название биржи
        market: Тип рынка (spot/linear)
        
    Returns:
        Котируемая валюта (USDT, USDC, TRY и т.д.) или None если не удалось определить
    """
    if not symbol:
        return None
    
    symbol_upper = symbol.upper()
    
    # Специальная обработка для Hyperliquid
    if exchange.lower() == "hyperliquid":
        if market == "linear":
            # Для linear на Hyperliquid символы уже нормализованы (BTC, ETH), котируемая валюта - USDC
            return "USDC"
        elif market == "spot":
            # Для spot на Hyperliquid может быть два формата:
            # 1. С разделителем: PURR/USDC, BTC/USDC
            # 2. Слитный формат: TNSRUSDC, XPLUSDC, STRKUSDC
            if "/" in symbol_upper:
                parts = symbol_upper.split("/")
                if len(parts) == 2:
                    quote = parts[1]
                    if quote in QUOTE_CURRENCIES:
                        return quote
            # Для слитного формата ищем котируемую валюту в конце
            matched_quote = None
            max_length = 0
            
            for quote in QUOTE_CURRENCIES:
                if symbol_upper.endswith(quote) and len(quote) > max_length:
                    matched_quote = quote
                    max_length = len(quote)
            
            if matched_quote:
                return matched_quote
    
    # Стандартная обработка для всех остальных бирж
    # Ищем самую длинную котируемую валюту, которая совпадает с концом символа
    matched_quote = None
    max_length = 0
    
    for quote in QUOTE_CURRENCIES:
        if symbol_upper.endswith(quote) and len(quote) > max_length:
            matched_quote = quote
            max_length = len(quote)
    
    # Также проверяем разделители
    for sep in SEPARATORS:
        if sep in symbol_upper:
            parts = symbol_upper.split(sep)
            if len(parts) == 2:
                quote = parts[1]
                if quote in QUOTE_CURRENCIES:
                    return quote
    
    return matched_quote


async def get_symbol_with_pair(symbol: str, exchange: str, market: str) -> str:
    """
    Получает символ в формате "BASE-QUOTE" (например, "BTC-USDT")
    
    Args:
        symbol: Оригинальный символ (например, "BTCUSDT")
        exchange: Название биржи
        market: Тип рынка (spot/linear)
        
    Returns:
        Символ в формате "BASE-QUOTE" или просто базовую монету, если не удалось определить пару
    """
    if not symbol:
        return symbol
    
    symbol_upper = symbol.upper()
    
    # Специальная обработка для Hyperliquid
    if exchange.lower() == "hyperliquid":
        if market == "linear":
            # Для linear на Hyperliquid символы уже нормализованы (BTC, ETH, ADA и т.д.)
            # Проверяем, что это не котируемая валюта
            if symbol_upper not in QUOTE_CURRENCIES:
                # Для Hyperliquid linear обычно используется USDC как котируемая валюта
                return f"{symbol_upper}-USDC"
        elif market == "spot":
            # Для spot на Hyperliquid может быть два формата:
            # 1. С разделителем: PURR/USDC, BTC/USDC
            # 2. Слитный формат: TNSRUSDC, XPLUSDC, STRKUSDC
            if "/" in symbol_upper:
                parts = symbol_upper.split("/")
                if len(parts) == 2:
                    base = parts[0]
                    quote = parts[1]
                    # Проверяем, что quote - это котируемая валюта
                    if quote in QUOTE_CURRENCIES:
                        return f"{base}-{quote}"
            # Для слитного формата (TNSRUSDC, XPLUSDC) ищем котируемую валюту в конце
            matched_quote = None
            max_length = 0
            
            for quote in QUOTE_CURRENCIES:
                if symbol_upper.endswith(quote) and len(quote) > max_length:
                    matched_quote = quote
                    max_length = len(quote)
            
            if matched_quote:
                base = symbol_upper[:-len(matched_quote)]
                if base and len(base) >= 2:
                    return f"{base}-{matched_quote}"
    
    # Стандартная обработка для всех остальных бирж
    base = _extract_base_standard(symbol_upper)
    quote = _extract_quote_currency(symbol_upper)
    
    if base and quote:
        return f"{base}-{quote}"
    elif base:
        # Если не удалось определить котируемую валюту, возвращаем только базовую
        return base
    else:
        # Если не удалось определить, возвращаем исходный символ
        return symbol_upper


async def normalize_symbol(symbol: str, exchange: str, market: str) -> str:
    """
    Нормализует символ (извлекает базовую монету)
    
    Сначала проверяет БД нормализации, если не найдено - использует алгоритмическую нормализацию
    и сохраняет результат в БД для будущего использования
    
    Args:
        symbol: Оригинальный символ
        exchange: Название биржи
        market: Тип рынка (spot/linear)
        
    Returns:
        Нормализованный символ (базовая монета)
    """
    if not symbol:
        return symbol
    
    # Нормализуем входные параметры
    exchange_lower = exchange.lower()
    market_lower = market.lower()
    symbol_upper = symbol.upper()
    
    # Сначала проверяем БД
    normalized = await symbol_normalization_db.get_normalized_symbol(
        exchange_lower, market_lower, symbol_upper
    )
    
    if normalized:
        return normalized
    
    # Если не найдено в БД, используем алгоритмическую нормализацию
    normalized = _extract_base_currency_algorithmic(symbol_upper, exchange_lower, market_lower)
    
    # Если алгоритмическая нормализация не дала результата, используем исходный символ
    if not normalized:
        normalized = symbol_upper
    
    # Сохраняем в БД асинхронно (не блокируем выполнение)
    # Используем asyncio.create_task для фонового сохранения
    try:
        # Сохраняем синхронно, но это быстрая операция
        await symbol_normalization_db.save_normalized_symbol(
            exchange_lower, market_lower, symbol_upper, normalized
        )
    except Exception as e:
        # Не критично, если не удалось сохранить - просто логируем
        logger.debug(f"Не удалось сохранить нормализованный символ в БД: {e}")
    
    return normalized


async def denormalize_symbol(normalized: str, exchange: Optional[str] = None, 
                           market: Optional[str] = None) -> List[str]:
    """
    Получает все варианты символов для нормализованного символа (денормализация)
    
    Args:
        normalized: Нормализованный символ (базовая монета)
        exchange: Фильтр по бирже (опционально)
        market: Фильтр по рынку (опционально)
        
    Returns:
        Список оригинальных символов
    """
    if not normalized:
        return []
    
    normalized_upper = normalized.upper()
    
    # Получаем из БД
    symbols = await symbol_normalization_db.get_denormalized_symbols(
        normalized_upper, exchange, market
    )
    
    return symbols


def is_normalized(symbol: str) -> bool:
    """
    Проверяет, является ли символ нормализованным (базовой монетой)
    
    Args:
        symbol: Символ для проверки
        
    Returns:
        True если символ выглядит как нормализованный (короткий, без разделителей)
    """
    if not symbol:
        return False
    
    symbol_upper = symbol.upper()
    
    # Если содержит разделители - не нормализован
    if any(sep in symbol_upper for sep in SEPARATORS):
        return False
    
    # Если слишком длинный - вероятно не нормализован
    if len(symbol_upper) > 10:
        return False
    
    # Если заканчивается на известную котируемую валюту - не нормализован
    for quote in QUOTE_CURRENCIES:
        if symbol_upper.endswith(quote) and len(symbol_upper) > len(quote):
            return False
    
    return True


def symbols_match(symbol1: str, symbol2: str) -> bool:
    """
    Проверяет, соответствуют ли два символа одной монете (с учётом нормализации)
    
    Args:
        symbol1: Первый символ
        symbol2: Второй символ
        
    Returns:
        True если символы соответствуют одной монете
    """
    if not symbol1 or not symbol2:
        return False
    
    # Нормализуем оба символа (синхронно, без БД)
    # Для быстрой проверки используем только алгоритмическую нормализацию
    norm1 = _extract_base_currency_algorithmic(symbol1.upper(), "", "")
    norm2 = _extract_base_currency_algorithmic(symbol2.upper(), "", "")
    
    if not norm1 or not norm2:
        # Если не удалось нормализовать, сравниваем как есть
        return symbol1.upper() == symbol2.upper()
    
    return norm1 == norm2


async def populate_normalization_db():
    """
    Заполняет БД нормализации всеми символами со всех бирж
    Вызывается при первом запуске или для синхронизации
    """
    logger.info("Начинаем заполнение БД нормализации символов...")
    
    exchanges = {
        "binance": ["spot", "linear"],
        "gate": ["spot", "linear"],
        "bitget": ["spot", "linear"],
        "bybit": ["spot", "linear"],
        "hyperliquid": ["spot", "linear"],
    }
    
    total_added = 0
    
    for exchange, markets in exchanges.items():
        for market in markets:
            try:
                # Импортируем symbol_fetcher для каждой биржи
                if exchange == "binance":
                    from exchanges.binance.symbol_fetcher import fetch_symbols
                elif exchange == "gate":
                    from exchanges.gate.symbol_fetcher import fetch_symbols
                elif exchange == "bitget":
                    from exchanges.bitget.symbol_fetcher import fetch_symbols
                elif exchange == "bybit":
                    from exchanges.bybit.symbol_fetcher import fetch_symbols
                elif exchange == "hyperliquid":
                    from exchanges.hyperliquid.symbol_fetcher import fetch_symbols
                else:
                    continue
                
                # Получаем символы с биржи
                symbols = await fetch_symbols(market)
                logger.info(f"Получено {len(symbols)} символов для {exchange} {market}")
                
                # Нормализуем и сохраняем каждый символ
                for symbol in symbols:
                    try:
                        normalized = await normalize_symbol(symbol, exchange, market)
                        total_added += 1
                    except Exception as e:
                        logger.warning(f"Ошибка при нормализации символа {symbol} для {exchange} {market}: {e}")
                        continue
                
            except Exception as e:
                logger.error(f"Ошибка при получении символов для {exchange} {market}: {e}", exc_info=True)
                continue
    
    logger.info(f"Заполнение БД нормализации завершено. Добавлено символов: {total_added}")
    return total_added


async def sync_normalization_db():
    """
    Синхронизирует БД нормализации с актуальными символами бирж
    Добавляет только новые символы, которые отсутствуют в БД
    """
    logger.info("Начинаем синхронизацию БД нормализации символов...")
    
    exchanges = {
        "binance": ["spot", "linear"],
        "gate": ["spot", "linear"],
        "bitget": ["spot", "linear"],
        "bybit": ["spot", "linear"],
        "hyperliquid": ["spot", "linear"],
    }
    
    total_added = 0
    
    for exchange, markets in exchanges.items():
        for market in markets:
            try:
                # Импортируем symbol_fetcher для каждой биржи
                if exchange == "binance":
                    from exchanges.binance.symbol_fetcher import fetch_symbols
                elif exchange == "gate":
                    from exchanges.gate.symbol_fetcher import fetch_symbols
                elif exchange == "bitget":
                    from exchanges.bitget.symbol_fetcher import fetch_symbols
                elif exchange == "bybit":
                    from exchanges.bybit.symbol_fetcher import fetch_symbols
                elif exchange == "hyperliquid":
                    from exchanges.hyperliquid.symbol_fetcher import fetch_symbols
                else:
                    continue
                
                # Получаем символы с биржи
                symbols = await fetch_symbols(market)
                
                # Проверяем каждый символ - есть ли он в БД
                for symbol in symbols:
                    try:
                        # Проверяем, есть ли уже в БД
                        existing = await symbol_normalization_db.get_normalized_symbol(
                            exchange, market, symbol.upper()
                        )
                        
                        if not existing:
                            # Нормализуем и сохраняем
                            normalized = await normalize_symbol(symbol, exchange, market)
                            total_added += 1
                    except Exception as e:
                        logger.warning(f"Ошибка при синхронизации символа {symbol} для {exchange} {market}: {e}")
                        continue
                
            except Exception as e:
                logger.error(f"Ошибка при синхронизации символов для {exchange} {market}: {e}", exc_info=True)
                continue
    
    logger.info(f"Синхронизация БД нормализации завершена. Добавлено новых символов: {total_added}")
    return total_added

