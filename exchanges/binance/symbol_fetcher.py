"""
Получение списка торговых символов с Binance API
"""
import ssl
import certifi
import aiohttp
import asyncio
from typing import List
from core.logger import get_logger

logger = get_logger(__name__)

# Котируемые активы для Spot
SPOT_QUOTE_ASSETS = {
    "BTC", "ETH", "USDT", "BNB", "USD", "TUSD", "BRL",
    "USDC", "TRX", "EUR", "DOGE", "FDUSD", "IDR",
}
# Котируемые активы для Futures USDⓈ-M5
FAPI_QUOTE_ASSETS = {"USDT", "USDC", "BTC"}

SPOT_EXCHANGE_INFO = "https://api.binance.com/api/v3/exchangeInfo"
FAPI_EXCHANGE_INFO = "https://fapi.binance.com/fapi/v1/exchangeInfo"

# Глобальный пул соединений для переиспользования (экономия памяти)
_connector_pool = None
_session_pool = None
_session_lock: asyncio.Lock | None = None


async def _get_session():
    """Получает или создает переиспользуемую сессию для экономии памяти"""
    global _session_pool, _connector_pool, _session_lock
    
    # Инициализируем lock при первом вызове
    if _session_lock is None:
        _session_lock = asyncio.Lock()
    
    # Используем double-check pattern для защиты создания сессии
    if _session_pool is None or _session_pool.closed:
        async with _session_lock:
            # Проверяем еще раз внутри lock (double-check)
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
        Список символов (например, ["BTCUSDT", "ETHUSDT"])
    """
    if market == "spot":
        # Используем SPOT API
        url = SPOT_EXCHANGE_INFO
        quote_assets = SPOT_QUOTE_ASSETS
    elif market == "linear":
        # Используем FUTURES API
        url = FAPI_EXCHANGE_INFO
        quote_assets = FAPI_QUOTE_ASSETS
    else:
        return []
    
    try:
        # Используем переиспользуемую сессию для экономии памяти
        session = await _get_session()
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status != 200:
                return []
            
            data = await resp.json()
            symbols = []
            
            for s in data.get("symbols", []):
                if s.get("status") != "TRADING":
                    continue
                
                if market == "spot":
                    # Для spot фильтруем по quoteAsset
                    quote = s.get("quoteAsset", "").upper()
                    if quote not in quote_assets:
                        continue
                    symbols.append(s.get("symbol"))
                
                elif market == "linear":
                    # Для futures проверяем PERPETUAL и quoteAsset
                    if s.get("contractType") != "PERPETUAL":
                        continue
                    quote = s.get("quoteAsset", "")
                    if quote not in quote_assets:
                        continue
                    # Формируем pair в верхнем регистре
                    pair = f"{s.get('baseAsset')}{s.get('quoteAsset')}"
                    symbols.append(pair.upper())
            
            return symbols
                
    except Exception as e:
        logger.error(f"Ошибка получения символов Binance {market}: {e}", exc_info=True)
        return []

