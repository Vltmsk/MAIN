# -*- coding: utf-8 -*-
"""
USDT cross-venue "price skew" detector (Spot & USDT-Perp) -> Telegram alerts

Биржи:
  Spot:   Binance, Bybit, Bitget, Gate, MEXC, HTX
  Futures: Binance(USDT-M), Bybit(Linear), Bitget(USDT-FUTURES), Gate(USDT-Perp)

Особенности:
  - Реестры листинга по каждой бирже/рынку (только реально торгуемые пары)
  - Bitget Spot: включаем пары только если open > 0
  - Bitget Perps: включаем контракты со status="normal"; цены берём только при суточном объёме > 0
  - Сбор цен с фильтром p>0
  - Порог детекта: DIFF >= 50%  (Diff% = (max-min)/max*100)
  - Подтверждение детекта: параллельный запрос цен по монете на все рынки
  - Кулдаун: 8 часов на монету
  - Блеклист: глобальный + пер-биржевой (например, только для Gate-S)
  - Логи: статусы, ошибки, счётчики
  - Ровная таблица в Telegram (<pre>), стрелки: ⬆️ максимум, ⬇️ минимум
"""

import time
import requests
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# ====== КОНФИГ ======
BOT_TOKEN = "8271206439:AAGx7y4_wEWP7HhMojYXpvjI6yTqBjTw-tI"
CHAT_ID = -1001556517228

PRICE_DIFF_THRESHOLD = 50.0        # %, считаем от maxPrice
COOLDOWN_SECONDS = 8 * 60 * 60     # 8 часов
POLL_INTERVAL = 2.0                # сек между циклами
MARKETS_REFRESH_MIN = 30           # обновление реестров раз в 30 мин
HTTP_TIMEOUT = 6                   # сек для запросов

# ====== БЛЕКЛИСТЫ ======
# Глобальный блеклист (для всех бирж/рынков)
BLACKLIST_COINS = {
    "AIX","VOLT","NEIRO","BLZ","VT","TRUMP","WELL","APP","BEAM","DORA","CAD","EARNM","SLN",
    "CAW","WXT","MRLN","ZK","POP","TST","RIF","GTC","MLN","QI","BIFI","ARC","ZERO","PBUX",
    "XCAD","TRC","X","ORT","TOMI","SHRAP","HOLD","OLAS","WOLF","MAX","GME","PMX","RICE",
    "REAL","ROCK","SNS","BLOCK","GAIN","LAI","VON","SUKU","CULT","BAC","PBX","RAI","GST",
    "AIBOT","PALM","WX","CLV","TAP","DGB","ZEROLEND","LRDS","TROLL","JAM","TOWN","UXLINK",
    "SPON","MON","REX","PEPPER","BABYBNB","MMT","BFI","GAME","TXT","CELB","KDA","BULLA",
    "BEBE","VIC","PEP","ACN","MA","SLF","WIFI","BSX"
}

# Пер-биржевой блеклист: монеты игнорируются ТОЛЬКО на указанных рынках
# Пример: TRAC для Gate Spot
VENUE_BLACKLIST = {
    "Gate-S": {"TRAC"},
    # Можно добавлять и другие, например:
    # "Binance-F": {"ABC", "XYZ"},
}

def is_blacklisted_global(coin: str) -> bool:
    return coin.upper() in BLACKLIST_COINS

def is_blacklisted_venue(coin: str, exch_tag: str) -> bool:
    return coin.upper() in VENUE_BLACKLIST.get(exch_tag, set())

# ====== СОСТОЯНИЕ ======
last_alert_time = {}     # { "BTC": ts_last_sent }
last_markets_refresh = 0

# Реестр поддерживаемых символов по бирже/рынку (нормализация: BASEUSDT)
supported = {
    "Binance-S": set(),
    "Binance-F": set(),
    "Bybit-S": set(),
    "Bybit-F": set(),
    "Bitget-S": set(),
    "Bitget-F": set(),
    "Gate-S": set(),
    "Gate-F": set(),
    "MEXC-S": set(),
    "HTX-S": set(),
}

# ====== УТИЛИТЫ ======
def log(msg: str):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)

def send_pre_message(text: str):
    """Отправка моноширинного блока <pre>...<pre> (parse_mode=HTML)."""
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={
                "chat_id": CHAT_ID,
                "text": f"<pre>{text}</pre>",
                "parse_mode": "HTML",
                "disable_web_page_preview": True
            },
            timeout=HTTP_TIMEOUT
        )
        if r.status_code != 200:
            log(f"Ошибка Telegram: {r.status_code} {r.text}")
    except Exception as e:
        log(f"Исключение при отправке в Telegram: {e}")

def fmt_price(p: float) -> str:
    try:
        p = float(p)
    except:
        return ""
    if p <= 0:
        return ""
    if p >= 1000:
        s = f"{p:.2f}"
    elif p >= 100:
        s = f"{p:.3f}"
    elif p >= 1:
        s = f"{p:.4f}"
    else:
        s = f"{p:.6f}"
    return s.rstrip("0").rstrip(".")

def safe_float(x, default=0.0):
    try:
        return float(x)
    except:
        return default

# ====== ОБНОВЛЕНИЕ РЕЕСТРОВ (листинг) ======
def refresh_markets():
    global last_markets_refresh
    t0 = time.time()
    log("Обновление реестров символов...")

    # 1) Binance Spot
    try:
        r = requests.get("https://api.binance.com/api/v3/exchangeInfo", timeout=HTTP_TIMEOUT)
        j = r.json()
        s = {it["symbol"] for it in j.get("symbols", []) if it.get("status")=="TRADING" and it.get("quoteAsset")=="USDT"}
        supported["Binance-S"] = s
        log(f"Binance-S: {len(s)} USDT-пар")
    except Exception as e:
        log(f"Binance-S exchangeInfo ошибка: {e}")

    # 2) Binance Futures (USDT-M)
    try:
        r = requests.get("https://fapi.binance.com/fapi/v1/exchangeInfo", timeout=HTTP_TIMEOUT)
        j = r.json()
        s = {it["symbol"] for it in j.get("symbols", []) if it.get("quoteAsset")=="USDT" and it.get("status")=="TRADING"}
        supported["Binance-F"] = s
        log(f"Binance-F: {len(s)} USDT-перп контрактов")
    except Exception as e:
        log(f"Binance-F exchangeInfo ошибка: {e}")

    # 3) Bybit Spot
    try:
        r = requests.get("https://api.bybit.com/v5/market/tickers?category=spot", timeout=HTTP_TIMEOUT)
        j = r.json(); s=set()
        if j.get("retCode")==0:
            for it in j.get("result",{}).get("list",[]):
                sym=it.get("symbol",""); 
                if sym.endswith("USDT"): s.add(sym)
        supported["Bybit-S"]=s
        log(f"Bybit-S: {len(s)} USDT-пар")
    except Exception as e:
        log(f"Bybit-S ошибка: {e}")

    # 4) Bybit Futures (linear USDT)
    try:
        r = requests.get("https://api.bybit.com/v5/market/tickers?category=linear", timeout=HTTP_TIMEOUT)
        j = r.json(); s=set()
        if j.get("retCode")==0:
            for it in j.get("result",{}).get("list",[]):
                sym=it.get("symbol",""); 
                if sym.endswith("USDT"): s.add(sym)
        supported["Bybit-F"]=s
        log(f"Bybit-F: {len(s)} USDT-линейных контрактов")
    except Exception as e:
        log(f"Bybit-F ошибка: {e}")

    # 5) Bitget Spot  (ТОЛЬКО активные пары: open > 0)
    try:
        r = requests.get("https://api.bitget.com/api/v2/spot/market/tickers", timeout=HTTP_TIMEOUT)
        j = r.json(); s=set()
        if j.get("code")=="00000":
            for it in j.get("data",[]):
                sym=it.get("symbol","")
                if sym.endswith("USDT") and safe_float(it.get("open"))>0: s.add(sym)
        supported["Bitget-S"]=s
        log(f"Bitget-S (active open>0): {len(s)} USDT-пар")
    except Exception as e:
        log(f"Bitget-S ошибка: {e}")

    # 6) Bitget Futures: по каталогу контрактов + status="normal"
    try:
        r = requests.get("https://api.bitget.com/api/v2/mix/market/contracts?productType=USDT-FUTURES", timeout=HTTP_TIMEOUT)
        j = r.json(); s=set()
        if j.get("code")=="00000":
            for it in j.get("data",[]):
                sym=it.get("symbol",""); status=(it.get("symbolStatus") or "").lower()
                if sym.endswith("USDT") and status=="normal": s.add(sym)
        supported["Bitget-F"]=s
        log(f"Bitget-F (status=normal): {len(s)} USDT-контрактов")
    except Exception as e:
        log(f"Bitget-F contracts ошибка: {e}")

    # 7) Gate Spot
    try:
        r = requests.get("https://api.gateio.ws/api/v4/spot/currency_pairs", timeout=HTTP_TIMEOUT)
        arr = r.json(); s=set()
        if isinstance(arr,list):
            for it in arr:
                cp = it.get("id") or it.get("name") or it.get("currency_pair")
                if cp and cp.endswith("_USDT"): s.add(cp.replace("_",""))
        supported["Gate-S"]=s
        log(f"Gate-S: {len(s)} USDT-пар")
    except Exception as e:
        log(f"Gate-S currency_pairs ошибка: {e}")
        try:
            r = requests.get("https://api.gateio.ws/api/v4/spot/tickers", timeout=HTTP_TIMEOUT)
            arr = r.json(); s=set()
            if isinstance(arr,list):
                for it in arr:
                    cp=it.get("currency_pair","")
                    if cp.endswith("_USDT"): s.add(cp.replace("_",""))
            supported["Gate-S"]=s
            log(f"Gate-S (tickers): {len(s)} USDT-пар")
        except Exception as e2:
            log(f"Gate-S тикеры ошибка: {e2}")

    # 8) Gate Futures (USDT-perp)
    try:
        r = requests.get("https://api.gateio.ws/api/v4/futures/usdt/contracts", timeout=HTTP_TIMEOUT)
        arr = r.json(); s=set()
        if isinstance(arr,list):
            for it in arr:
                name = it.get("name") or it.get("symbol") or it.get("contract")
                if name:
                    base = name.replace("_","")
                    if base.endswith("USDT"): s.add(base)
        supported["Gate-F"]=s
        log(f"Gate-F: {len(s)} USDT-перп контрактов")
    except Exception as e:
        log(f"Gate-F ошибка: {e}")

    # 9) MEXC Spot
    try:
        r = requests.get("https://api.mexc.com/api/v3/ticker/price", timeout=HTTP_TIMEOUT)
        arr = r.json(); s=set()
        if isinstance(arr,list):
            for it in arr:
                sym=it.get("symbol","")
                if sym.endswith("USDT"): s.add(sym)
        supported["MEXC-S"]=s
        log(f"MEXC-S: {len(s)} USDT-пар")
    except Exception as e:
        log(f"MEXC-S ошибка: {e}")

    # 10) HTX (Huobi) Spot
    try:
        r = requests.get("https://api.huobi.pro/market/tickers", timeout=HTTP_TIMEOUT)
        j = r.json(); s=set()
        if j.get("status")=="ok":
            for it in j.get("data",[]):
                sym=it.get("symbol","")
                if sym.endswith("usdt"): s.add(sym.upper())
        supported["HTX-S"]=s
        log(f"HTX-S: {len(s)} USDT-пар")
    except Exception as e:
        log(f"HTX-S ошибка: {e}")

    last_markets_refresh = time.time()
    log(f"Реестры обновлены за {last_markets_refresh - t0:.2f}s")

# ====== СБОР ЦЕН (с фильтром по листингу и p>0) ======
def fetch_prices_once():
    prices = {}

    def put(sym_full: str, exch_tag: str, price_val):
        """Добавляем цену если >0, символ в листинге, монета не в блеклистах."""
        p = safe_float(price_val, default=-1.0)
        if p <= 0 or not sym_full.endswith("USDT"):
            return
        coin = sym_full[:-4].upper()
        # глобальный и пер-биржевой блеклист
        if is_blacklisted_global(coin) or is_blacklisted_venue(coin, exch_tag):
            return
        prices.setdefault(coin, {})[exch_tag] = p

    # Binance Spot
    try:
        r = requests.get("https://api.binance.com/api/v3/ticker/price", timeout=HTTP_TIMEOUT)
        arr = r.json(); cnt=0; sset=supported["Binance-S"]
        for it in arr:
            sym=it.get("symbol","")
            if sym in sset:
                put(sym,"Binance-S",it.get("price")); cnt+=1
        log(f"Binance-S цены: {cnt}")
    except Exception as e:
        log(f"Binance-S цены ошибка: {e}")

    # Binance Futures
    try:
        r = requests.get("https://fapi.binance.com/fapi/v2/ticker/price", timeout=HTTP_TIMEOUT)
        arr = r.json(); cnt=0; sset=supported["Binance-F"]
        for it in arr:
            sym=it.get("symbol","")
            if sym in sset:
                put(sym,"Binance-F",it.get("price")); cnt+=1
        log(f"Binance-F цены: {cnt}")
    except Exception as e:
        log(f"Binance-F цены ошибка: {e}")

    # Bybit Spot
    try:
        r = requests.get("https://api.bybit.com/v5/market/tickers?category=spot", timeout=HTTP_TIMEOUT)
        j = r.json(); cnt=0; sset=supported["Bybit-S"]
        if j.get("retCode")==0:
            for it in j.get("result",{}).get("list",[]):
                sym=it.get("symbol","")
                if sym in sset:
                    put(sym,"Bybit-S",it.get("lastPrice")); cnt+=1
        log(f"Bybit-S цены: {cnt}")
    except Exception as e:
        log(f"Bybit-S цены ошибка: {e}")

    # Bybit Futures
    try:
        r = requests.get("https://api.bybit.com/v5/market/tickers?category=linear", timeout=HTTP_TIMEOUT)
        j = r.json(); cnt=0; sset=supported["Bybit-F"]
        if j.get("retCode")==0:
            for it in j.get("result",{}).get("list",[]):
                sym=it.get("symbol","")
                if sym in sset:
                    put(sym,"Bybit-F",it.get("lastPrice")); cnt+=1
        log(f"Bybit-F цены: {cnt}")
    except Exception as e:
        log(f"Bybit-F цены ошибка: {e}")

    # Bitget Spot
    try:
        r = requests.get("https://api.bitget.com/api/v2/spot/market/tickers", timeout=HTTP_TIMEOUT)
        j = r.json(); cnt=0; sset=supported["Bitget-S"]
        if j.get("code")=="00000":
            for it in j.get("data",[]):
                sym=it.get("symbol","")
                if sym in sset and safe_float(it.get("open"))>0:
                    put(sym,"Bitget-S",it.get("lastPr")); cnt+=1
        log(f"Bitget-S цены (active): {cnt}")
    except Exception as e:
        log(f"Bitget-S цены ошибка: {e}")

    # Bitget Futures
    try:
        r = requests.get("https://api.bitget.com/api/v2/mix/market/tickers?productType=USDT-FUTURES", timeout=HTTP_TIMEOUT)
        j = r.json(); cnt=0; sset=supported["Bitget-F"]
        if j.get("code")=="00000":
            for it in j.get("data",[]):
                sym_full=it.get("symbol","")
                base = sym_full.split("_")[0] if "_" in sym_full else sym_full
                if base not in sset:
                    continue
                if (safe_float(it.get("usdtVolume"))<=0 and
                    safe_float(it.get("baseVolume"))<=0 and
                    safe_float(it.get("quoteVolume"))<=0):
                    continue
                put(base,"Bitget-F",it.get("lastPr")); cnt+=1
        log(f"Bitget-F цены (status ok & vol>0): {cnt}")
    except Exception as e:
        log(f"Bitget-F цены ошибка: {e}")

    # Gate Spot
    try:
        r = requests.get("https://api.gateio.ws/api/v4/spot/tickers", timeout=HTTP_TIMEOUT)
        arr = r.json(); cnt=0; sset=supported["Gate-S"]
        if isinstance(arr,list):
            for it in arr:
                cp=it.get("currency_pair","")
                sym=cp.replace("_","")
                if sym in sset:
                    put(sym,"Gate-S",it.get("last")); cnt+=1
        log(f"Gate-S цены: {cnt}")
    except Exception as e:
        log(f"Gate-S цены ошибка: {e}")

    # Gate Futures
    try:
        r = requests.get("https://api.gateio.ws/api/v4/futures/usdt/tickers", timeout=HTTP_TIMEOUT)
        arr = r.json(); cnt=0; sset=supported["Gate-F"]
        if isinstance(arr,list):
            for it in arr:
                name=(it.get("contract") or it.get("name") or "").replace("_","")
                if name in sset:
                    put(name,"Gate-F",it.get("last")); cnt+=1
        log(f"Gate-F цены: {cnt}")
    except Exception as e:
        log(f"Gate-F цены ошибка: {e}")

    # MEXC Spot
    try:
        r = requests.get("https://api.mexc.com/api/v3/ticker/price", timeout=HTTP_TIMEOUT)
        arr = r.json(); cnt=0; sset=supported["MEXC-S"]
        if isinstance(arr,list):
            for it in arr:
                sym=it.get("symbol","")
                if sym in sset:
                    put(sym,"MEXC-S",it.get("price")); cnt+=1
        log(f"MEXC-S цены: {cnt}")
    except Exception as e:
        log(f"MEXC-S цены ошибка: {e}")

    # HTX Spot
    try:
        r = requests.get("https://api.huobi.pro/market/tickers", timeout=HTTP_TIMEOUT)
        j = r.json(); cnt=0; sset=supported["HTX-S"]
        if j.get("status")=="ok":
            for it in j.get("data",[]):
                sym=it.get("symbol","").upper()
                if sym in sset:
                    put(sym,"HTX-S",it.get("close")); cnt+=1
        log(f"HTX-S цены: {cnt}")
    except Exception as e:
        log(f"HTX-S цены ошибка: {e}")

    return prices

# ====== ПАРАЛЛЕЛЬНОЕ ПОДТВЕРЖДЕНИЕ ПО МОНЕТЕ ======
def confirm_prices_for_coin(coin: str):
    """Одновременные запросы coinUSDT по каждому рынку (с учётом блеклистов)."""
    sym = f"{coin}USDT"
    tasks = []
    out = {}

    def allowed(ex_tag: str) -> bool:
        # монета может быть не в глобальном БЛ, но забанена для конкретного рынка
        return (not is_blacklisted_global(coin)) and (not is_blacklisted_venue(coin, ex_tag))

    with ThreadPoolExecutor(max_workers=10) as ex:
        # Binance-S
        if sym in supported["Binance-S"] and allowed("Binance-S"):
            tasks.append(ex.submit(lambda: ("Binance-S", safe_float(
                requests.get(f"https://api.binance.com/api/v3/ticker/price?symbol={sym}", timeout=HTTP_TIMEOUT).json().get("price")
            ))))
        # Binance-F
        if sym in supported["Binance-F"] and allowed("Binance-F"):
            tasks.append(ex.submit(lambda: ("Binance-F", safe_float(
                requests.get(f"https://fapi.binance.com/fapi/v2/ticker/price?symbol={sym}", timeout=HTTP_TIMEOUT).json().get("price")
            ))))
        # Bybit-S
        if sym in supported["Bybit-S"] and allowed("Bybit-S"):
            tasks.append(ex.submit(lambda: ("Bybit-S", safe_float(
                (lambda j: (j.get("result", {}).get("list", [{}])[0]).get("lastPrice"))(
                    requests.get(f"https://api.bybit.com/v5/market/tickers?category=spot&symbol={sym}", timeout=HTTP_TIMEOUT).json()
                )
            ))))
        # Bybit-F
        if sym in supported["Bybit-F"] and allowed("Bybit-F"):
            tasks.append(ex.submit(lambda: ("Bybit-F", safe_float(
                (lambda j: (j.get("result", {}).get("list", [{}])[0]).get("lastPrice"))(
                    requests.get(f"https://api.bybit.com/v5/market/tickers?category=linear&symbol={sym}", timeout=HTTP_TIMEOUT).json()
                )
            ))))
        # Bitget-S
        if sym in supported["Bitget-S"] and allowed("Bitget-S"):
            tasks.append(ex.submit(lambda: ("Bitget-S", (lambda jj: (
                safe_float(next((it.get("lastPr") for it in jj.get("data", []) if it.get("symbol")==sym and safe_float(it.get("open"))>0), 0.0))
            ))(requests.get(f"https://api.bitget.com/api/v2/spot/market/tickers?symbol={sym}", timeout=HTTP_TIMEOUT).json()))))
        # Bitget-F
        if sym in supported["Bitget-F"] and allowed("Bitget-F"):
            def get_bitget_f():
                j = requests.get("https://api.bitget.com/api/v2/mix/market/tickers?productType=USDT-FUTURES", timeout=HTTP_TIMEOUT).json()
                best = 0.0
                for it in j.get("data", []):
                    sfull = it.get("symbol","")
                    base = sfull.split("_")[0] if "_" in sfull else sfull
                    if base != sym:
                        continue
                    if (safe_float(it.get("usdtVolume"))<=0 and
                        safe_float(it.get("baseVolume"))<=0 and
                        safe_float(it.get("quoteVolume"))<=0):
                        continue
                    best = safe_float(it.get("lastPr")); break
                return ("Bitget-F", best)
            tasks.append(ex.submit(get_bitget_f))
        # Gate-S
        if sym in supported["Gate-S"] and allowed("Gate-S"):
            cp = f"{coin}_USDT"
            tasks.append(ex.submit(lambda: ("Gate-S", safe_float(
                (lambda arr: next((safe_float(x.get("last")) for x in arr if x.get("currency_pair")==cp), 0.0))(
                    requests.get(f"https://api.gateio.ws/api/v4/spot/tickers?currency_pair={cp}", timeout=HTTP_TIMEOUT).json()
                )
            ))))
        # Gate-F
        if sym in supported["Gate-F"] and allowed("Gate-F"):
            cp = f"{coin}_USDT"
            tasks.append(ex.submit(lambda: ("Gate-F", safe_float(
                (lambda arr: next((safe_float(x.get("last")) for x in arr if (x.get("contract")==cp or x.get("name")==cp)), 0.0))(
                    requests.get(f"https://api.gateio.ws/api/v4/futures/usdt/tickers?contract={cp}", timeout=HTTP_TIMEOUT).json()
                )
            ))))
        # MEXC-S
        if sym in supported["MEXC-S"] and allowed("MEXC-S"):
            tasks.append(ex.submit(lambda: ("MEXC-S", safe_float(
                requests.get(f"https://api.mexc.com/api/v3/ticker/price?symbol={sym}", timeout=HTTP_TIMEOUT).json().get("price")
            ))))
        # HTX-S
        if sym in supported["HTX-S"] and allowed("HTX-S"):
            def get_htx_spot():
                js = requests.get(f"https://api.huobi.pro/market/detail/merged?symbol={sym.lower()}", timeout=HTTP_TIMEOUT).json()
                tick = js.get("tick") or {}
                return ("HTX-S", safe_float(tick.get("close") or tick.get("lastPrice") or tick.get("last")))
            tasks.append(ex.submit(get_htx_spot))

        for fut in as_completed(tasks):
            try:
                tag, val = fut.result()
                if val and val > 0:
                    out[tag] = val
            except Exception:
                pass
    return out

# ====== ВЫВОД ТАБЛИЦЫ (со стрелками) ======
def build_aligned_table(coin: str, price_map: dict, diff_percent: float) -> str:
    """
    Разница цен между биржами⚠️
    #COIN  |  Spot  | Futures
    Binance| 12.34  | 12.35
    ...
    d-XX.X%
    """
    exchanges = ["Binance", "Bybit", "Bitget", "Gate", "MEXC", "HTX"]

    all_prices = list(price_map.values())
    mn = min(all_prices) if all_prices else None
    mx = max(all_prices) if all_prices else None
    show_marks = not (mn is None or mx is None or abs(mx - mn) < 1e-12)

    rows = []
    for ex in exchanges:
        s_tag = f"{ex}-S"; f_tag = f"{ex}-F"
        s_val = price_map.get(s_tag)
        f_val = price_map.get(f_tag)
        if s_val is None and f_val is None:
            continue

        s_txt = fmt_price(s_val) if s_val is not None else ""
        f_txt = fmt_price(f_val) if f_val is not None else ""

        if show_marks:
            if s_val is not None:
                if abs(s_val - mx) < 1e-12: s_txt = (s_txt + " ⬆️").strip()
                elif abs(s_val - mn) < 1e-12: s_txt = (s_txt + " ⬇️").strip()
            if f_val is not None:
                if abs(f_val - mx) < 1e-12: f_txt = (f_txt + " ⬆️").strip()
                elif abs(f_val - mn) < 1e-12: f_txt = (f_txt + " ⬇️").strip()

        rows.append((ex, s_txt, f_txt))

    exch_w = max(7, max((len(r[0]) for r in rows), default=7))
    spot_w = max(4, max((len(r[1]) for r in rows), default=4))
    fut_w  = max(7, max((len(r[2]) for r in rows), default=7))

    lines = []
    lines.append("Разница цен между биржами⚠️")
    head = f"#{coin}".ljust(exch_w) + " | " + "Spot".center(spot_w) + " | " + "Futures".center(fut_w)
    lines.append(head)

    for ex, s_txt, f_txt in rows:
        line = ex.ljust(exch_w) + " | " + s_txt.ljust(spot_w) + " | " + f_txt.ljust(fut_w)
        lines.append(line)

    lines.append(f"d-{round(diff_percent, 1)}%")
    return "\n".join(lines)

# ====== ОСНОВНОЙ ЦИКЛ ======
def main_loop():
    global last_markets_refresh
    log("Запуск детектора перекоса цен...")
    refresh_markets()

    while True:
        now = time.time()
        if now - last_markets_refresh > MARKETS_REFRESH_MIN * 60:
            refresh_markets()

        log("Старт снятия ценового среза...")
        prices = fetch_prices_once()
        total_pairs = sum(len(v) for v in prices.values())
        log(f"Срез готов: монет={len(prices)}, заполненных строк={total_pairs}")

        for coin, exch_map in prices.items():
            # глобальный БЛ — выключаем монету целиком
            if is_blacklisted_global(coin):
                continue

            if len(exch_map) < 2:
                continue

            vals = list(exch_map.values())
            mn = min(vals); mx = max(vals)
            if mx <= 0:
                continue
            diff = (mx - mn) / mx * 100.0
            if diff < PRICE_DIFF_THRESHOLD:
                continue

            ts = last_alert_time.get(coin)
            if ts and (now - ts) < COOLDOWN_SECONDS:
                continue

            log(f"Первичный перекос {diff:.2f}% по {coin} — подтверждаю...")
            confirm_map = confirm_prices_for_coin(coin)
            confirm_map = {k: v for k, v in confirm_map.items() if v and v > 0}
            if len(confirm_map) < 2:
                log(f"Подтверждение {coin}: недостаточно данных, пропуск.")
                continue

            cvals = list(confirm_map.values())
            cmn = min(cvals); cmx = max(cvals)
            if cmx <= 0:
                continue
            cdiff = (cmx - cmn) / cmx * 100.0
            if cdiff < PRICE_DIFF_THRESHOLD:
                log(f"Подтверждение {coin}: расхождение исчезло ({cdiff:.2f}%), пропуск.")
                continue

            table_text = build_aligned_table(coin, confirm_map, cdiff)
            send_pre_message(table_text)
            last_alert_time[coin] = time.time()
            log(f"АЛЕРТ отправлен по {coin}: {cdiff:.2f}%")

        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    try:
        main_loop()
    except KeyboardInterrupt:
        log("Остановлено пользователем.")
    except Exception as e:
        log(f"Критическая ошибка: {e}")
