# Как строить тиковый график по Binance (SPOT и USDT-M Futures)
# --------------------------------------------------------------
# Задача: максимально быстро получить последние сделки по инструменту
# (без привязки к строго 60 минутам) и рисовать по ним тиковый график.
#
# БАЗОВАЯ ИДЕЯ:
#   1) Один REST-запрос aggTrades c limit=1000 -> получаем последние до 1000 сделок.
#   2) Конвертируем каждую запись aggTrade в "тик" (time, price, qty, side).
#   3) Рисуем тиковый график:
#        - либо X = индекс тика (tick index chart),
#        - либо X = timestamp (time-based tick chart).
#   4) Для онлайна: WebSocket <symbol>@aggTrade, добавляем новые тики в хвост.


# 1. REST-эндпоинты Binance под тиковый график
# -------------------------------------------
# SPOT:
#   GET https://api.binance.com/api/v3/aggTrades?symbol=BTCUSDT&limit=1000
#
# Futures USDT-M:
#   GET https://fapi.binance.com/fapi/v1/aggTrades?symbol=BTCUSDT&limit=1000
#
# Параметры:
#   symbol : строка, например "BTCUSDT", "FETUSDT"
#   limit  : максимум 1000 -> нам и нужно 1000 (последний доступный кусок рынка)
#
# НИЧЕГО больше НЕ указываем:
#   - НЕ задаём startTime / endTime
#   - НЕ задаём fromId
#
# Тогда Binance возвращает последние aggTrades по этому символу.
# Массив отсортирован по времени: самый старый первый, самый новый последний.


# 2. Структура одного aggTrade (примерный формат)
# -----------------------------------------------
# Одна запись aggTrade выглядит так:
#
# {
#   "a": 26129,          # aggTradeId (ID агрегированной сделки)
#   "p": "0.01633102",   # цена (price)
#   "q": "4.70443515",   # объём в базовой валюте (quantity)
#   "f": 27781,          # firstTradeId
#   "l": 27781,          # lastTradeId
#   "T": 1498793709153,  # время сделки в миллисекундах
#   "m": true,           # was buyer the maker (флаг maker для покупателя)
#   "M": true            # best price match (обычно не важен для графика)
# }
#
# Для тикового графика нам нужны:
#   - T  -> время
#   - p  -> цена
#   - q  -> объём
#   - m  -> side (из него выводим направление сделки)


# 3. Конвертация aggTrades в универсальную структуру "тик"
# --------------------------------------------------------
# Логика по "m":
#   m == True  -> buyer is maker  -> агрессор продавец -> считаем тик как SELL
#   m == False -> buyer is taker  -> агрессор покупатель -> считаем тик как BUY
#
# Пример структуры тика:
#
# tick = {
#     "id":   agg["a"],            # ID тика (aggTradeId)
#     "ts":   agg["T"],            # timestamp в ms
#     "price": float(agg["p"]),    # цена
#     "qty":   float(agg["q"]),    # объём
#     "side": "sell" if agg["m"] else "buy"
# }


import time
import requests
from typing import List, Literal, TypedDict


class Tick(TypedDict):
    id: int
    ts: int          # timestamp в миллисекундах
    price: float
    qty: float
    side: Literal["buy", "sell"]


def fetch_latest_aggtrades_binance_spot(symbol: str, limit: int = 1000) -> List[dict]:
    """
    Получить сырые aggTrades со спота Binance (последние limit сделок).
    Никаких startTime/fromId - только последние aggTrades.
    """
    url = "https://api.binance.com/api/v3/aggTrades"
    params = {"symbol": symbol.upper(), "limit": limit}
    r = requests.get(url, params=params, timeout=5)
    r.raise_for_status()
    return r.json()  # список dict-ов с полями a, p, q, T, m и т.д.


def fetch_latest_aggtrades_binance_futures(symbol: str, limit: int = 1000) -> List[dict]:
    """
    То же самое, но для Binance Futures USDT-M.
    """
    url = "https://fapi.binance.com/fapi/v1/aggTrades"
    params = {"symbol": symbol.upper(), "limit": limit}
    r = requests.get(url, params=params, timeout=5)
    r.raise_for_status()
    return r.json()


def aggtrades_to_ticks(aggtrades: List[dict]) -> List[Tick]:
    """
    Конвертация списка aggTrades в список тиков (Tick).
    Предполагаем, что aggtrades уже отсортированы Binance по времени (oldest -> newest).
    """
    ticks: List[Tick] = []
    for a in aggtrades:
        tick: Tick = {
            "id": int(a["a"]),
            "ts": int(a["T"]),
            "price": float(a["p"]),
            "qty": float(a["q"]),
            "side": "sell" if a["m"] else "buy",
        }
        ticks.append(tick)

    # На всякий случай можно отсортировать по ts,
    # но Binance уже возвращает в правильном порядке:
    ticks.sort(key=lambda t: t["ts"])
    return ticks


# 4. Построение тикового графика из списка ticks
# ----------------------------------------------
# Вариант A: X = индекс тика (tick index chart)
#   - X: 0, 1, 2, 3, ...
#   - Y: price
#   - цвет точки: side (buy/sell)
#
# Вариант B: X = время (time-based chart)
#   - X: ts (или ts/1000 в секундах)
#   - Y: price
#   - цвет точки: side
#
# Пример: подготовка данных для графика (без конкретной библиотеки отрисовки)


def prepare_tick_chart_data_index_x(ticks: List[Tick]):
    """
    X = индекс тика, Y = цена.
    Возвращает кортеж (x_list, y_list, colors) - уже готовый для любой plotting-библиотеки.
    """
    x = list(range(len(ticks)))
    y = [t["price"] for t in ticks]
    colors = ["green" if t["side"] == "buy" else "red" for t in ticks]
    sizes = [max(1.0, t["qty"] ** 0.5) for t in ticks]  # пример: размер точки ~ sqrt(volume)
    return x, y, colors, sizes


def prepare_tick_chart_data_time_x(ticks: List[Tick]):
    """
    X = время (в секундах), Y = цена.
    """
    x = [t["ts"] / 1000.0 for t in ticks]  # переводим ms -> секунды
    y = [t["price"] for t in ticks]
    colors = ["green" if t["side"] == "buy" else "red" for t in ticks]
    sizes = [max(1.0, t["qty"] ** 0.5) for t in ticks]
    return x, y, colors, sizes


# 5. Полный базовый цикл: "получить и нарисовать"
# -----------------------------------------------
# Ниже пример функций, которые можно использовать в проекте:
#   - fetch_spot_ticks_for_symbol  -> получить последние тики с SPOT
#   - fetch_futures_ticks_for_symbol -> получить последние тики с FUTURES
#   - дальше - получить x, y, colors, sizes -> отрисовать.


def fetch_spot_ticks_for_symbol(symbol: str, limit: int = 1000) -> List[Tick]:
    """
    Универсальный шаг:
      1) REST запрос aggTrades SPOT
      2) конвертация в тики
    """
    raw = fetch_latest_aggtrades_binance_spot(symbol, limit=limit)
    ticks = aggtrades_to_ticks(raw)
    return ticks


def fetch_futures_ticks_for_symbol(symbol: str, limit: int = 1000) -> List[Tick]:
    """
    То же самое для фьючей USDT-M.
    """
    raw = fetch_latest_aggtrades_binance_futures(symbol, limit=limit)
    ticks = aggtrades_to_ticks(raw)
    return ticks


# 6. Пример использования (псевдо-main)
# -------------------------------------
# Представим, что у тебя есть код отрисовки (PyQt, веб, matplotlib, plotly — не важно).
# Тебе нужно просто получить ticks и превратить их в x/y + цвета.


def example_usage():
    symbol = "FETUSDT"

    # 1. Получаем последние 1000 тиков со спота
    spot_ticks = fetch_spot_ticks_for_symbol(symbol, limit=1000)

    # 2. Готовим данные для тикового графика (ось X = индекс тика)
    x_idx, y_idx, colors_idx, sizes_idx = prepare_tick_chart_data_index_x(spot_ticks)

    # 3. Готовим данные для тикового графика (ось X = время)
    x_time, y_time, colors_time, sizes_time = prepare_tick_chart_data_time_x(spot_ticks)

    # Далее:
    #   - x_idx, y_idx, colors_idx, sizes_idx -> отдаёшь в компонент отрисовки "по индексу"
    #   - x_time, y_time, colors_time, sizes_time -> отдаёшь в компонент отрисовки "по времени"
    #
    # В реальном проекте ты сюда вместо print подставишь вызов своей функции:
    # draw_tick_chart(x_idx, y_idx, colors_idx, sizes_idx)
    # или draw_tick_chart(x_time, y_time, colors_time, sizes_time)
    print(
        f"Got {len(spot_ticks)} ticks for {symbol}. "
        f"Time range: {time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(spot_ticks[0]['ts']/1000))} "
        f"-> {time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(spot_ticks[-1]['ts']/1000))}"
    )


# 7. Реалтайм-обновление через WebSocket (идея)
# --------------------------------------------
# Для живого графика добавляется WS:
#
#   SPOT:   wss://stream.binance.com:9443/ws/<symbol>@aggTrade
#   FUTURES:wss://fstream.binance.com/ws/<symbol>@aggTrade
#
# При старте:
#   - делаешь один REST-бэкрап (как выше) -> ticks
#   - запускаешь WS и на каждое новое сообщение @aggTrade:
#       * конвертируешь сообщение в Tick
#       * добавляешь в конец списка ticks
#       * если len(ticks) > MAX_TICKS (например, 2000) -> удаляешь старые с головы
#       * триггеришь перерисовку графика
#
# Так ты:
#   - одним REST-запросом получаешь историю (последние 1000 тиков)
#   - через WS добавляешь живые тики
#   - всегда рисуешь актуальный тиковый график без лишних запросов.


if __name__ == "__main__":
    # Пример запуска (для проверки в консоли / IDE)
    # В реальном проекте ты будешь вызывать только нужные функции.
    try:
        example_usage()
    except Exception as e:
        print("Error:", e)
