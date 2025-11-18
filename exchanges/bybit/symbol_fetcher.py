"""
Получение списка торговых символов с Bybit API
"""
import ssl
import certifi
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
        # Используем сертификаты из certifi для безопасных SSL подключений
        ssl_context = ssl.create_default_context(cafile=certifi.where())
        connector = aiohttp.TCPConnector(ssl=ssl_context)
        async with aiohttp.ClientSession(connector=connector) as session:
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
                    status = item.get("status", "").lower()
                    if "trading" in status or status == "1":
                        symbol = item.get("symbol", "")
                        
                        # Для spot рынка: фильтруем по USDT, USDC, BTC, ETH, EUR
                        # Для linear (futures) рынка: фильтруем только по USDT
                        if market == "spot":
                            # Поддерживаем дополнительные пары для spot
                            # Проверяем от самых длинных к коротким (USDT перед USD, USDC перед USDT)
                            quote_currencies = ["USDT", "USDC", "BTC", "ETH", "EUR"]
                            for quote in sorted(quote_currencies, key=len, reverse=True):
                                if symbol.endswith(quote):
                                    symbols.append(symbol)
                                    break
                        elif market == "linear":
                            # Для futures только USDT
                            if symbol.endswith("USDT"):
                                symbols.append(symbol)
                
                return symbols
                
    except Exception:
        return []

