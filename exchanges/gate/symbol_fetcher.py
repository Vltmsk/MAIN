"""
Получение списка торговых символов с Gate.io API
"""
import ssl
import certifi
import aiohttp
from typing import List
from core.logger import get_logger

logger = get_logger(__name__)

SPOT_API_URL = "https://api.gateio.ws/api/v4/spot/currency_pairs"
LINEAR_API_URL = "https://api.gateio.ws/api/v4/futures/usdt/contracts"

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
        market: "spot" или "linear" (futures)
        
    Returns:
        Список символов
    """
    if market == "spot":
        url = SPOT_API_URL
    elif market == "linear":
        url = LINEAR_API_URL
    else:
        return []
    
    try:
        # Используем переиспользуемую сессию для экономии памяти
        session = await _get_session()
        async with session.get(url) as response:
            if response.status != 200:
                logger.warning(f"Gate.io API вернул статус {response.status} для {market}")
                return []
            
            data = await response.json()
            symbols = []
            
            for item in data:
                if market == "spot":
                    # Для spot проверяем trade_status
                    if item.get("trade_status") == "tradable":
                        symbol_id = item.get("id")
                        if symbol_id:
                            symbols.append(symbol_id)
                elif market == "linear":
                    # Для linear проверяем status
                    if item.get("status") == "trading":
                        symbol_name = item.get("name")
                        if symbol_name:
                            symbols.append(symbol_name)
            
            # Логируем только на уровне DEBUG, чтобы не засорять логи при частых проверках
            logger.debug(f"Gate.io: получено {len(symbols)} символов для {market}")
            return symbols
                
    except Exception as e:
        logger.error(f"Ошибка при получении символов Gate.io для {market}: {e}")
        return []

