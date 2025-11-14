"""
Получение списка торговых символов с Bybit API
"""
import aiohttp
from typing import List


# Bybit REST API
REST_BASE = "https://api.bybit.com/v5/market/instruments-info"


async def fetch_symbols(market: str) -> List[str]:
    """
    Получает список активных торговых символов для указанного рынка.
    
    Args:
        market: "spot" или "linear" (futures)
        
    Returns:
        Список символов (например, ["BTCUSDT", "ETHUSDT"])
    """
    # Маппинг market на category для Bybit API
    category_map = {
        "spot": "spot",
        "linear": "linear",
    }
    
    category = category_map.get(market)
    if not category:
        return []
    
    url = REST_BASE
    params = {
        "category": category,
        "limit": 1000  # Max 1000 per request
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status != 200:
                    return []
                
                data = await resp.json()
                ret_code = data.get("retCode")
                if ret_code != 0:
                    return []
                
                result = data.get("result", {})
                list_data = result.get("list", [])
                
                symbols = []
                for item in list_data:
                    # Filter: active status, USDT quote (для spot: USDT, ETH, BTC, USDC, EUR; для linear: только USDT)
                    status = item.get("status", "").lower()
                    if "trading" in status or status == "1":
                        symbol = item.get("symbol", "")
                        if symbol.endswith("USDT"):
                            symbols.append(symbol)
                
                return symbols
                
    except Exception:
        return []

