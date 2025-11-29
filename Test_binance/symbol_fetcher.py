"""
Получение списка торговых символов с Binance API
"""
import aiohttp
from typing import List

# Котируемые активы для Spot
SPOT_QUOTE_ASSETS = {
    "BTC", "ETH", "USDT", "BNB", "AUD", "TUSD", "BRL", "GBP",
    "USDC", "TRX", "EUR", "BIDR", "DOGE", "TRY", "FDUSD", "AEUR",
}
# Котируемые активы для Futures USDⓈ-M
FAPI_QUOTE_ASSETS = {"USDT", "USDC", "BTC"}

SPOT_EXCHANGE_INFO = "https://api.binance.com/api/v3/exchangeInfo"
FAPI_EXCHANGE_INFO = "https://fapi.binance.com/fapi/v1/exchangeInfo"


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
        async with aiohttp.ClientSession() as session:
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
                
    except Exception:
        return []

