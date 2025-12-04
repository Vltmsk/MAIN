"""
Получение списка торговых символов с Bitget API
"""
import ssl
import certifi
import aiohttp
from typing import List

BITGET_REST_BASE = "https://api.bitget.com"

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
        Список символов (например, ["BTCUSDT", "ETHUSDT"])
    """
    if market == "spot":
        # Используем SPOT API
        url = f"{BITGET_REST_BASE}/api/v2/spot/public/symbols"
        
        try:
            # Используем переиспользуемую сессию для экономии памяти
            session = await _get_session()
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status != 200:
                    return []
                
                data = await resp.json()
                symbols = []
                for it in data.get("data", []):
                    try:
                        if it.get("status") == "online" and it.get("quoteCoin") == "USDT":
                            sym = it.get("symbol") or it.get("instId")
                            if sym and sym.endswith("USDT"):
                                symbols.append(sym)
                    except Exception:
                        continue
                return sorted(symbols)
        except Exception:
            return []
    
    elif market == "linear":
        # Используем FUTURES API
        endpoints = [
            f"{BITGET_REST_BASE}/api/v2/mix/market/tickers?productType=USDT-FUTURES",
            f"{BITGET_REST_BASE}/api/v2/mix/market/contracts?productType=USDT-FUTURES",
            f"{BITGET_REST_BASE}/api/mix/v1/market/contracts?productType=USDT-FUTURES",
            f"{BITGET_REST_BASE}/api/v2/mix/market/contracts?productType=UMCBL",
            f"{BITGET_REST_BASE}/api/mix/v1/market/contracts?productType=UMCBL",
        ]
        
        for url in endpoints:
            try:
                # Используем переиспользуемую сессию для экономии памяти
                session = await _get_session()
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    if resp.status != 200:
                        continue
                    
                    data = await resp.json()
                    rows = data.get("data") if isinstance(data, dict) else None
                    if not rows:
                        continue
                    
                    symbols = []
                    for it in rows:
                        try:
                            sym = it.get("symbol") or it.get("instId")
                            status = (it.get("status") or it.get("state") or "").lower()
                            if sym and sym.endswith("USDT"):
                                if (not status) or status in ("online", "normal", "trading"):
                                    symbols.append(sym)
                        except Exception:
                            continue
                    
                    if symbols:
                        return sorted(set(symbols))
            except Exception:
                continue
        
        return []
    else:
        return []

