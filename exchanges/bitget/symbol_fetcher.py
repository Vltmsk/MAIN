"""
Получение списка торговых символов с Bitget API
"""
import aiohttp
from typing import List

BITGET_REST_BASE = "https://api.bitget.com"


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
            async with aiohttp.ClientSession() as session:
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
                async with aiohttp.ClientSession() as session:
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

