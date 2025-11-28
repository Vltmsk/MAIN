"""
Получение списка торговых символов с Hyperliquid API
"""
import ssl
import certifi
import aiohttp
import json
from typing import List
from core.logger import get_logger

logger = get_logger(__name__)

# Hyperliquid REST API endpoints
HYPERLIQUID_REST_API = "https://api.hyperliquid.xyz/info"

# Котируемые активы для фильтрации
SPOT_QUOTE_ASSETS = {"USDC"}  # Spot на Hyperliquid обычно использует USDC
PERPETUAL_QUOTE_ASSETS = {"USDC"}  # Perpetuals также используют USDC

# Глобальный пул соединений для переиспользования (экономия памяти)
_connector_pool = None
_session_pool = None


async def _get_session():
    """Получает или создает переиспользуемую сессию для экономии памяти"""
    global _session_pool, _connector_pool
    
    if _session_pool is None or _session_pool.closed:
        ssl_context = ssl.create_default_context(cafile=certifi.where())
        _connector_pool = aiohttp.TCPConnector(ssl=ssl_context, limit=10)
        _session_pool = aiohttp.ClientSession(connector=_connector_pool)
    
    return _session_pool


async def fetch_symbols(market: str) -> List[str]:
    """
    Получает список активных торговых символов для указанного рынка.
    
    Args:
        market: "spot" или "linear" (perpetuals)
        
    Returns:
        Список символов (например, ["BTC", "ETH"] или ["BTC/USDC:USDC"])
    """
    try:
        # Используем переиспользуемую сессию для экономии памяти
        session = await _get_session()
        # Hyperliquid использует POST запросы для получения информации
        # Для спота используем spotMeta, для перпов - meta
        if market == "spot":
            payload = {"type": "spotMeta"}
        else:  # linear (perpetuals)
            payload = {"type": "meta"}
        
        async with session.post(
            HYPERLIQUID_REST_API,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=30)
        ) as resp:
            if resp.status != 200:
                logger.warning(f"Hyperliquid API вернул статус {resp.status} для {market}")
                return []
            
            data = await resp.json()
            symbols = []
            
            if market == "spot":
                # Для спота: данные в spotMeta.universe[]
                # Формат: universe[] с полями name (может быть "PURR/USDC" или "@index") и tokens[]
                universe = []
                if isinstance(data, dict):
                    universe = data.get("universe", [])
                
                for item in universe:
                    if isinstance(item, dict):
                        # name может быть "PURR/USDC" или "@index"
                        name = item.get("name", "")
                        if name:
                            # Если это "@index", используем как есть
                            # Если это "PURR/USDC", используем как есть
                            symbols.append(name)
            
            else:  # linear (perpetuals)
                # Для перпов: данные в meta.universe[]
                # Формат: universe[] с полем name (символ, например "BTC", "ETH")
                universe = []
                if isinstance(data, dict):
                    universe = data.get("universe", [])
                
                for item in universe:
                    if isinstance(item, dict):
                        # Проверяем флаг isDelisted - фильтруем только активные
                        is_delisted = item.get("isDelisted", False)
                        if is_delisted:
                            continue
                        
                        # Получаем название символа
                        symbol = item.get("name", "")
                        if symbol:
                            symbols.append(symbol)
            
            # Удаляем дубликаты и сортируем
            symbols = sorted(list(set(symbols)))
            
            # Логируем только на уровне DEBUG, чтобы не засорять логи при частых проверках
            logger.debug(f"Hyperliquid: получено {len(symbols)} символов для {market}")
            return symbols
            
    except Exception as e:
        logger.error(f"Ошибка при получении символов Hyperliquid для {market}: {e}", exc_info=True)
        return []

