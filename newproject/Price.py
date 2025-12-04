# -*- coding: utf-8 -*-
# Python 3.13
# Бот: @a1price_bot

import asyncio
import contextlib
import re
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import Dict, Optional, List

from telegram import Update, MessageEntity
from telegram.constants import ChatType, ParseMode
from telegram.ext import Application, MessageHandler, ContextTypes, filters
from telegram.request import HTTPXRequest

import aiohttp
import ccxt.async_support as ccxt  # async CCXT

# ====================== КОНФИГ ======================
BOT_TOKEN = "8375316639:AAH21M_hBd34bRdpISm6-DMiFCwUYdf52II"
BOT_USERNAME = "a1price_bot"  # без @

# Тайминги
UPDATE_DEBOUNCE_SEC = 1.0      # минимум между редактированиями
FIRST_SEND_DELAY    = 2.0      # задержка перед первым ответом
SECOND_ROUND_DELAY  = 30.0     # задержка перед вторым раундом обновления цен
NO_PRICE_TIMEOUT    = 20.0     # если за это время нет цен - монета не найдена
NOT_FOUND_GRACE_SEC = 15.0     # сколько НЕ показывать «не найдена»

# Таймауты (мс/сек)
TIMEOUT_ALL_MS     = 25000      # 25 секунд для всех бирж
TIMEOUT_OKX_HTTP   = 25         # сек, HTTP-фолбэк OKX
TIMEOUT_PAN_HTTP   = 25         # сек, API PancakeSwap / DexScreener

# Кэш маркетов
MARKETS_TTL = timedelta(minutes=10)

# PancakeSwap / DexScreener
PAN_TOKENLIST_TTL      = timedelta(minutes=10)
PAN_TOKENLIST_URL      = "https://tokens.pancakeswap.finance/pancakeswap-extended.json"
PAN_TOKEN_DATA_URL     = "https://api.pancakeswap.info/api/v2/tokens/{addr}"
DEXSCREENER_TOKEN_URL  = "https://api.dexscreener.com/latest/dex/tokens/{addr}"
BSC_USDT = "0x55d398326f99059fF775485246999027B3197955"  # USDT (BSC)

_pan_tokens_cache: Optional[dict] = None
_pan_tokens_loaded_at: Optional[datetime] = None

# ======= ЧЁРНЫЙ СПИСОК ТИКЕРОВ =======
BLACKLIST_COINS = {
    "AIX","VOLT","NEIRO","BLZ","VT","TRUMP","WELL","APP","BEAM","DORA","CAD","EARNM",
    "SLN","CAW","WXT","MRLN","ZK","POP","TST","RIF","GTC","MLN","QI","BIFI","ARC",
    "ZERO","PBUX","XCAD","TRC","X","ORT","TOMI","SHRAP","HOLD","OLAS","WOLF","MAX",
    "GME","PMX","RICE","REAL","ROCK","SNS","BLOCK","GAIN","LAI","VON","SUKU","CULT",
    "BAC","PBX","RAI","GST","AIBOT","PALM","WX","CLV","TAP","TROLL",
}

# ====================== ЛОГИ ======================
logger = logging.getLogger("a1price")
handler = logging.StreamHandler()
formatter = logging.Formatter("[%(asctime)s] %(levelname)s %(message)s", "%H:%M:%S")
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.INFO)
def log(msg: str): logger.info(msg)

# ====================== ФОРМАТ ЧИСЕЛ ======================

def fmt_price(x: float | str) -> str:
    if x is None:
        return ""
    if isinstance(x, str):
        return x
    try:
        d = Decimal(str(x))
    except InvalidOperation:
        d = Decimal(x)

    if d == d.to_integral_value():
        return format(d.quantize(Decimal("1")), "f")

    if abs(d) < Decimal("1"):
        s = format(abs(d), "f")
        decimals = s.split(".")[1]
        m = re.search(r"[1-9]", decimals)
        if not m:
            return ("-" if d < 0 else "") + "0"
        j = m.start()
        k = min(len(decimals), j + 3)
        new_dec = decimals[:k]
        return ("-" if d < 0 else "") + "0." + new_dec

    absd = abs(d)
    if absd >= Decimal("1000"):
        q = Decimal("1")
    elif absd >= Decimal("100"):
        q = Decimal("0.1")
    else:
        q = Decimal("0.001")
    d = d.quantize(q, rounding=ROUND_HALF_UP)
    s = format(d, "f")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s

def decimals_count(s: str) -> int:
    return len(s.split(".")[1]) if s and "." in s else 0

def pad_to_decimals(s: str, target: int) -> str:
    if not s: return s
    if target <= 0: return s
    if "." not in s: return s + "." + ("0" * target)
    cur = len(s.split(".")[1])
    if cur >= target: return s
    return s + ("0" * (target - cur))

@dataclass
class MarketPick:
    symbol: str

@dataclass
class MsgState:
    sent: Optional[object] = None
    last_text: Optional[str] = None
    last_edit_at: float = 0.0

# ====================== URL конструкторы (ссылки на пары) ======================

def build_pair_url(ex_name: str, market_type: str, base: str) -> Optional[str]:
    b = base.upper()
    try:
        if ex_name == "Binance":
            return f"https://www.binance.com/en/{'trade' if market_type=='spot' else 'futures'}/{b}{'_USDT' if market_type=='spot' else 'USDT'}"
        if ex_name == "Bybit":
            return f"https://www.bybit.com/trade/{'spot' if market_type=='spot' else 'usdt'}/{b}{'' if market_type=='spot' else 'USDT'}{'' if market_type!='spot' else '/USDT'}"
        if ex_name == "Bitget":
            return f"https://www.bitget.com/{'spot' if market_type=='spot' else 'futures/usdt'}/{b}USDT"
        if ex_name == "Gate":
            return f"https://www.gate.io/{'trade' if market_type=='spot' else 'futures_trade/USDT'}/{b}{'_USDT' if market_type=='spot' else '_USDT'}"
        if ex_name == "MEXC":
            return f"https://www.mexc.com/exchange/{b}_USDT" if market_type=='spot' else f"https://futures.mexc.com/exchange?symbol={b}_USDT"
        if ex_name == "HTX":
            return f"https://www.htx.com/en-us/trade/{b}_usdt" if market_type=='spot' else f"https://www.htx.com/en-us/futures/linear/{b}USDT"
        if ex_name == "KuCoin":
            return f"https://www.kucoin.com/trade/{b}-USDT" if market_type=='spot' else f"https://www.kucoin.com/futures/{b}USDT"
        if ex_name == "BingX":
            return f"https://bingx.com/spot/{b}USDT/" if market_type=='spot' else f"https://bingx.com/standardContract/{b}USDT/"
        if ex_name == "OKX":
            return f"https://www.okx.com/trade-spot/{b}-usdt" if market_type=='spot' else f"https://www.okx.com/trade-swap/{b}-usdt-swap"
    except Exception:
        return None
    return None

# ====================== Exchange Manager ======================

class ExchangeManager:
    def __init__(self) -> None:
        self.inited = False
        self.last_load: Dict[str, datetime] = {}
        self.market_locks: Dict[str, asyncio.Lock] = {}
        self.exchanges_spot: Dict[str, Optional[ccxt.Exchange]] = {}
        self.exchanges_fut: Dict[str, Optional[ccxt.Exchange]] = {}

    async def init(self):
        if self.inited:
            return

        def timeout_for(name: str) -> int:
            return TIMEOUT_ALL_MS  # 25 секунд для всех бирж

        # Spot
        self.exchanges_spot = {
            "Binance": ccxt.binance({"timeout": timeout_for("Binance")}),
            "Bybit":   ccxt.bybit({"timeout": timeout_for("Bybit"), "options": {"defaultType": "spot"}}),
            "Bitget":  ccxt.bitget({"timeout": timeout_for("Bitget"), "options": {"defaultType": "spot"}}),
            "Gate":    ccxt.gate({"timeout": timeout_for("Gate"), "options": {"defaultType": "spot"}}),
            "MEXC":    ccxt.mexc({"timeout": timeout_for("MEXC"), "enableRateLimit": True, "options": {"defaultType": "spot"}}),
            "HTX":     ccxt.htx({"timeout": timeout_for("HTX"), "enableRateLimit": True, "options": {"defaultType": "spot"}}),
            "OKX":     ccxt.okx({"timeout": timeout_for("OKX"), "enableRateLimit": True, "options": {"defaultType": "spot"}}),
            "BingX":   ccxt.bingx({"timeout": timeout_for("BingX"), "options": {"defaultType": "spot"}}),
            "KuCoin":  ccxt.kucoin({"timeout": timeout_for("KuCoin")}),
            "PanSwap": None,
        }
        # Futures (USDT-M perp)
        self.exchanges_fut = {
            "Binance": ccxt.binanceusdm({"timeout": timeout_for("Binance")}),
            "Bybit":   ccxt.bybit({"timeout": timeout_for("Bybit"),
                                   "options": {"defaultType": "swap", "defaultSettle": "USDT"}}),
            "Bitget":  ccxt.bitget({"timeout": timeout_for("Bitget"),
                                    "options": {"defaultType": "swap"}}),
            "Gate":    ccxt.gate({"timeout": timeout_for("Gate"),
                                  "options": {"defaultType": "swap"}}),
            "MEXC":    ccxt.mexc({"timeout": timeout_for("MEXC"),
                                  "options": {"defaultType": "swap"}}),
            "HTX":     ccxt.htx({"timeout": timeout_for("HTX"), "enableRateLimit": True,
                                 "options": {"defaultType": "swap", "defaultSettle": "USDT"}}),
            "OKX":     ccxt.okx({"timeout": timeout_for("OKX"), "enableRateLimit": True,
                                 "options": {"defaultType": "swap", "defaultSettle": "USDT"}}),
            "BingX":   ccxt.bingx({"timeout": timeout_for("BingX"),
                                   "options": {"defaultType": "swap"}}),
            "KuCoin":  ccxt.kucoinfutures({"timeout": timeout_for("KuCoin")}),
            "PanSwap": None,
        }

        with contextlib.suppress(Exception):
            self.exchanges_spot["OKX"].set_sandbox_mode(False)
        with contextlib.suppress(Exception):
            self.exchanges_fut["OKX"].set_sandbox_mode(False)

        self.inited = True
        log("ExchangeManager initialized")

    async def ensure_markets(self, ex: ccxt.Exchange, key: str):
        now = datetime.now(timezone.utc)
        ts = self.last_load.get(key)
        if ts and (now - ts <= MARKETS_TTL) and getattr(ex, "markets", None):
            return
        lock = self.market_locks.setdefault(key, asyncio.Lock())
        async with lock:
            now = datetime.now(timezone.utc)
            ts = self.last_load.get(key)
            if ts and (now - ts <= MARKETS_TTL) and getattr(ex, "markets", None):
                return
            try:
                log(f"[markets] loading {key} ...")
                await ex.load_markets(reload=True)
            except Exception as e:
                log(f"[markets] reload failed for {key}: {e!r}, trying cached")
                with contextlib.suppress(Exception):
                    await ex.load_markets()
            self.last_load[key] = datetime.now(timezone.utc)
            log(f"[markets] ready {key}: {len(getattr(ex, 'markets', {}) or {})} markets")

    async def close_all(self):
        tasks = []
        for ex in self.exchanges_spot.values():
            if ex:
                tasks.append(ex.close())
        for ex in self.exchanges_fut.values():
            if ex:
                tasks.append(ex.close())
        await asyncio.gather(*tasks, return_exceptions=True)
        await asyncio.sleep(0.05)
        log("All exchanges closed")

MANAGER = ExchangeManager()

# ====================== PancakeSwap / DexScreener ======================

async def pan_load_token_list() -> dict:
    global _pan_tokens_cache, _pan_tokens_loaded_at
    now = datetime.now(timezone.utc)
    if _pan_tokens_cache and _pan_tokens_loaded_at and now - _pan_tokens_loaded_at < PAN_TOKENLIST_TTL:
        return _pan_tokens_cache
    try:
        log("[PanSwap] loading token list ...")
        async with aiohttp.ClientSession() as sess:
            async with sess.get(PAN_TOKENLIST_URL, timeout=TIMEOUT_PAN_HTTP) as r:
                data = await r.json()
                _pan_tokens_cache = data or {}
                _pan_tokens_loaded_at = now
                log(f"[PanSwap] token list loaded: {len((_pan_tokens_cache or {}).get('tokens', []))} items")
                return _pan_tokens_cache
    except Exception as e:
        log(f"[PanSwap] token list error: {e!r}")
        return _pan_tokens_cache or {}

async def pan_find_address_by_symbol(symbol: str) -> Optional[str]:
    data = await pan_load_token_list()
    tokens = data.get("tokens") or []
    sym = symbol.upper()
    for t in tokens:
        try:
            if t.get("symbol", "").upper() == sym and int(t.get("chainId", 0)) == 56:
                return t.get("address")
        except Exception:
            continue
    return None

def _safe_float(x) -> Optional[float]:
    try:
        f = float(x)
        return f if f > 0 else None
    except Exception:
        return None

async def panswap_spot_price(symbol: str) -> Optional[float]:
    addr = await pan_find_address_by_symbol(symbol)
    if not addr:
        log(f"[PanSwap] {symbol}: address not found")
        return None
    try:
        async with aiohttp.ClientSession() as sess:
            async with sess.get(PAN_TOKEN_DATA_URL.format(addr=addr), timeout=TIMEOUT_PAN_HTTP) as r:
                if r.status == 200:
                    js = await r.json()
                    data = js.get("data") or {}
                    price = _safe_float(data.get("price"))
                    if price is not None:
                        log(f"[PanSwap] {symbol}: price from Pancake info, addr={addr}, price={price}")
                        return price
                else:
                    log(f"[PanSwap] {symbol}: Pancake info HTTP {r.status}")
    except Exception as e:
        log(f"[PanSwap] {symbol}: Pancake info error {e!r}")
    try:
        async with aiohttp.ClientSession() as sess:
            async with sess.get(DEXSCREENER_TOKEN_URL.format(addr=addr), timeout=TIMEOUT_PAN_HTTP) as r:
                if r.status != 200:
                    log(f"[PanSwap] {symbol}: DexScreener HTTP {r.status}")
                    return None
                js = await r.json()
                pairs = js.get("pairs") or []
                best = None
                best_liq = -1.0
                for p in pairs:
                    try:
                        if (p.get("chainId") or "").lower() != "bsc":
                            continue
                        pu = _safe_float(p.get("priceUsd"))
                        if pu is None:
                            continue
                        liq = _safe_float(((p.get("liquidity") or {}).get("usd")))
                        liq = liq if liq is not None else 0.0
                        if liq > best_liq:
                            best_liq = liq
                            best = pu
                    except Exception:
                        continue
                if best is not None:
                    log(f"[PanSwap] {symbol}: price from DexScreener, liq={best_liq}, price={best}")
                else:
                    log(f"[PanSwap] {symbol}: no usable pairs")
                return best
    except Exception as e:
        log(f"[PanSwap] {symbol}: DexScreener error {e!r}")
        return None

# ====================== Маркеты и цены (CEX) ======================

def pick_market_symbol(ex: ccxt.Exchange, coin: str, want_type: str) -> Optional[str]:
    try:
        markets = ex.markets
        if not markets:
            return None
        for m in markets.values():
            if m.get("base") == coin and m.get("quote") == "USDT":
                if m.get("active") is False:
                    continue
                if want_type == "spot":
                    # Для spot проверяем несколько вариантов
                    if m.get("spot") or m.get("type") == "spot" or (m.get("type") is None and m.get("swap") is None and m.get("future") is None):
                        return m.get("symbol")
                if want_type == "swap" and m.get("type") == "swap" and m.get("linear") and m.get("settle") == "USDT":
                    return m.get("symbol")
        return None
    except Exception:
        return None

async def build_pick(ex: ccxt.Exchange, name: str, coin: str, want_type: str) -> Optional[MarketPick]:
    await MANAGER.ensure_markets(ex, key=f"{name}-{want_type}")
    if not getattr(ex, "markets", None):
        with contextlib.suppress(Exception):
            await ex.load_markets()
    symbol = pick_market_symbol(ex, coin, want_type)
    if not symbol:
        log(f"[{name}/{want_type}] {coin}: market not found")
        return None
    log(f"[{name}/{want_type}] {coin}: market picked {symbol}")
    return MarketPick(symbol=symbol)

async def okx_http_ticker(inst_id: str) -> Optional[dict]:
    url = "https://www.okx.com/api/v5/market/ticker"
    try:
        async with aiohttp.ClientSession() as sess:
            async with sess.get(url, params={"instId": inst_id}, timeout=TIMEOUT_OKX_HTTP) as r:
                if r.status != 200:
                    return None
                data = await r.json()
                arr = data.get("data") or []
                return arr[0] if arr else None
    except Exception:
        return None

async def okx_http_spot_mid(coin: str) -> Optional[float]:
    t = await okx_http_ticker(f"{coin}-USDT")
    if not t:
        return None
    try:
        bid = float(t.get("bidPx", 0) or 0)
        ask = float(t.get("askPx", 0) or 0)
        if bid > 0 and ask > 0:
            return (bid + ask) / 2.0
    except Exception:
        return None
    return None

async def okx_http_swap_last(coin: str) -> Optional[float]:
    t = await okx_http_ticker(f"{coin}-USDT-SWAP")
    if not t:
        return None
    try:
        last = float(t.get("last", 0) or 0)
        return last if last > 0 else None
    except Exception:
        return None

async def fetch_spot_mid_standard(ex: ccxt.Exchange, market_symbol: str, name: str, coin: str) -> Optional[float]:
    try:
        t = await ex.fetch_ticker(market_symbol)
        bid = t.get("bid"); ask = t.get("ask")
        if isinstance(bid, (int, float)) and isinstance(ask, (int, float)) and bid > 0 and ask > 0:
            price = (bid + ask) / 2.0
            log(f"[{name}/spot] {coin}: ticker mid={price}")
            return price
        else:
            log(f"[{name}/spot] {coin}: ticker has no bid/ask")
    except Exception as e:
        log(f"[{name}/spot] {coin}: fetch_ticker error {e!r}")

    try:
        ob = await ex.fetch_order_book(market_symbol, limit=20)
        bids = ob.get("bids") or []
        asks = ob.get("asks") or []
        if bids and asks and bids[0] and asks[0]:
            price = (bids[0][0] + asks[0][0]) / 2.0
            log(f"[{name}/spot] {coin}: orderbook mid={price}")
            return price
        else:
            log(f"[{name}/spot] {coin}: orderbook empty")
    except Exception as e:
        log(f"[{name}/spot] {coin}: fetch_order_book error {e!r}")
    return None

async def fetch_spot_mid_mexcfast(ex: ccxt.Exchange, market_symbol: str, coin: str) -> Optional[float]:
    async def from_ticker():
        try:
            t = await ex.fetch_ticker(market_symbol)
            bid = t.get("bid"); ask = t.get("ask")
            if isinstance(bid, (int, float)) and isinstance(ask, (int, float)) and bid > 0 and ask > 0:
                return (bid + ask) / 2.0
        except Exception:
            return None
        return None

    async def from_orderbook():
        try:
            ob = await ex.fetch_order_book(market_symbol, limit=20)
            bids = ob.get("bids") or []
            asks = ob.get("asks") or []
            if bids and asks and bids[0] and asks[0]:
                return (bids[0][0] + asks[0][0]) / 2.0
        except Exception:
            return None
        return None

    t1 = asyncio.create_task(from_ticker())
    t2 = asyncio.create_task(from_orderbook())
    done, pending = await asyncio.wait({t1, t2}, return_when=asyncio.FIRST_COMPLETED)

    result = None
    for d in done:
        with contextlib.suppress(Exception):
            res = d.result()
            if isinstance(res, (int, float)):
                result = res
                which = "ticker" if d is t1 else "orderbook"
                log(f"[MEXC/spot] {coin}: {which} mid={res}")
                break

    if result is None:
        rest = await asyncio.gather(*pending, return_exceptions=True)
        for res in rest:
            if isinstance(res, (int, float)):
                result = res
                log(f"[MEXC/spot] {coin}: (late) mid={res}")
                break

    for p in pending:
        with contextlib.suppress(Exception):
            p.cancel()

    if result is None:
        log(f"[MEXC/spot] {coin}: no price from ticker/orderbook")
    return result

async def fetch_fut_last(ex: ccxt.Exchange, market_symbol: str, name: str, coin: str) -> Optional[float]:
    try:
        t = await ex.fetch_ticker(market_symbol)
        last = t.get("last")
        if isinstance(last, (int, float)) and last > 0:
            log(f"[{name}/swap] {coin}: last={last}")
            return float(last)
        else:
            log(f"[{name}/swap] {coin}: ticker has no last")
    except Exception as e:
        log(f"[{name}/swap] {coin}: fetch_ticker error {e!r}")
    return None

# ====================== Рендер (моноширинный) ======================

def render_table_text(
    coin: str,
    rows: Dict[str, Dict[str, Optional[float]]],
    suppress_not_found: bool = False,
) -> str:
    """
    PanSwap выводится только если есть цена. Δ считается БЕЗ PanSwap.
    Если suppress_not_found=True и пока нет ни одной цены, рисуем скелет таблицы.
    """
    names = ["Binance", "Bybit", "Bitget", "Gate", "HTX", "MEXC",
             "KuCoin", "BingX", "OKX", "PanSwap"]

    present = []
    for n in names:
        sp = rows.get(n, {}).get("spot")
        ft = rows.get(n, {}).get("fut")
        if n == "PanSwap":
            if isinstance(sp, (int, float)):
                present.append((n, sp, ft))
        else:
            if isinstance(sp, (int, float)) or isinstance(ft, (int, float)):
                present.append((n, sp, ft))

    # если нет цен и включён грейс — рисуем скелет (все CEX, без PanSwap)
    if not present and suppress_not_found:
        display_names = ["Binance","Bybit","Bitget","Gate","HTX","MEXC","KuCoin","BingX","OKX"]
        label_w = max(len(n) for n in display_names + [("#"+coin)])
        spot_w  = len("Spot")
        fut_w   = len("Futures")
        def center(text: str, w: int) -> str:
            if not text: return " " * w
            if w <= len(text): return text
            padl = (w - len(text)) // 2
            padr = w - len(text) - padl
            return " " * padl + text + " " * padr
        lines = []
        lines.append(f"{('#'+coin).ljust(label_w)} |{center('Spot', spot_w)}| |{center('Futures', fut_w)}|")
        for n in display_names:
            lines.append(f"{n.ljust(label_w)} |{' '*spot_w}| |{' '*fut_w}|")
        return "<pre>" + "\n".join(lines) + "</pre>"

    if not present:
        return f"❌ Монета {coin} в парах с USDT на указанных биржах не найдена."

    formatted = []
    for n, sp, ft in present:
        s_sp = fmt_price(sp) if isinstance(sp, (int, float)) else ""
        s_ft = fmt_price(ft) if isinstance(ft, (int, float)) else ""
        formatted.append((n, sp, s_sp, ft, s_ft))

    spot_decimals = [decimals_count(fmt_price(sp)) for _, sp, *_ in formatted if isinstance(sp, (int, float)) and sp >= 1]
    fut_decimals  = [decimals_count(fmt_price(ft)) for *_, ft, _ in formatted if isinstance(ft, (int, float)) and ft >= 1]
    spot_target = min(max(spot_decimals) if spot_decimals else 0, 3)
    fut_target  = min(max(fut_decimals)  if fut_decimals  else 0, 3)

    display = []
    for n, sp, s_sp, ft, s_ft in formatted:
        if isinstance(sp, (int, float)) and sp >= 1:
            s_sp = pad_to_decimals(s_sp, spot_target)
        if isinstance(ft, (int, float)) and ft >= 1:
            s_ft  = pad_to_decimals(s_ft,  fut_target)
        display.append((n, s_sp, s_ft))

    label_w = max(len(n) for n, *_ in display + [("#" + coin, "", "")])
    spot_w  = max(len("Spot"),    max((len(s) for _, s, _ in display), default=0))
    fut_w   = max(len("Futures"), max((len(s) for *_, s in display),   default=0))

    def center(text: str, w: int) -> str:
        if not text: return " " * w
        if w <= len(text): return text
        padl = (w - len(text)) // 2
        padr = w - len(text) - padl
        return " " * padl + text + " " * padr

    lines = []
    lines.append(f"{('#'+coin).ljust(label_w)} |{center('Spot', spot_w)}| |{center('Futures', fut_w)}|")

    for n, s_sp, s_ft in display:
        scell = center(s_sp, spot_w)
        fcell = center(s_ft, fut_w)
        lines.append(f"{n.ljust(label_w)} |{scell}| |{fcell}|")

    # Δ без PanSwap
    all_prices: List[float] = []
    for n, sp, ft in present:
        if n == "PanSwap": continue
        if isinstance(sp, (int, float)): all_prices.append(sp)
        if isinstance(ft, (int, float)): all_prices.append(ft)
    delta_pct = (max(all_prices) - min(all_prices)) / min(all_prices) * 100.0 if all_prices and min(all_prices)>0 else 0.0

    delta_line = f"d-{delta_pct:.1f}%"
    if coin.upper() in BLACKLIST_COINS:
        delta_line += "  ⚠️Blacklist, разница цен на биржах или есть монеты с таким же названием"

    lines.append(delta_line)
    return "<pre>" + "\n".join(lines) + "</pre>"

# ====================== Рендер (режим ссылок) ======================

def _plain_len(html_text: str) -> int:
    return len(re.sub(r"<.*?>", "", html_text or ""))

def _center_html(cell_html: str, width: int) -> str:
    pad = width - _plain_len(cell_html)
    if pad <= 0:
        return cell_html
    left = pad // 2
    right = pad - left
    return f"{'&nbsp;'*left}{cell_html}{'&nbsp;'*right}"

def render_table_text_links(
    coin: str,
    rows: Dict[str, Dict[str, Optional[float]]],
    urls: Dict[str, Dict[str, Optional[str]]],
    suppress_not_found: bool = False,
) -> str:
    """
    Ссылочные цены. Показываем скелет сразу (все CEX), PanSwap — только если есть цена.
    Δ считается без PanSwap.
    """
    names_all = ["Binance","Bybit","Bitget","Gate","HTX","MEXC","KuCoin","BingX","OKX","PanSwap"]

    formatted = []
    for n in names_all:
        sp = rows.get(n, {}).get("spot")
        ft = rows.get(n, {}).get("fut")
        if n == "PanSwap" and not isinstance(sp, (int, float)):
            continue

        s_sp = fmt_price(sp) if isinstance(sp, (int, float)) else ""
        s_ft = fmt_price(ft) if isinstance(ft, (int, float)) else ""
        u_sp = (urls.get(n) or {}).get("spot")
        u_ft = (urls.get(n) or {}).get("fut")
        if s_sp and u_sp: s_sp = f'<a href="{u_sp}">{s_sp}</a>'
        if s_ft and u_ft: s_ft = f'<a href="{u_ft}">{s_ft}</a>'

        formatted.append((n, sp, s_sp, ft, s_ft))

    # если пусто и включён грейс — рисуем скелет (без PanSwap)
    if not formatted and suppress_not_found:
        for n in names_all[:-1]:
            formatted.append((n, None, "", None, ""))

    if not formatted:
        return f"❌ Монета {coin} в парах с USDT на указанных биржах не найдена."

    label_w = max(len(n) for n, *_ in formatted + [("#"+coin, "", "", "", "")])
    spot_w  = max(len("Spot"),    max((_plain_len(s_sp) for _, _, s_sp, _, _ in formatted), default=0))
    fut_w   = max(len("Futures"), max((_plain_len(s_ft) for _, _, _, _, s_ft in formatted), default=0))

    lines = []
    head = f"{('#'+coin).ljust(label_w).replace(' ', '&nbsp;')}&nbsp;|{_center_html('Spot', spot_w)}|&nbsp;|{_center_html('Futures', fut_w)}|"
    lines.append(head)

    for n, sp, s_sp, ft, s_ft in formatted:
        scell = _center_html(s_sp, spot_w) if s_sp else "&nbsp;"*spot_w
        fcell = _center_html(s_ft, fut_w) if s_ft else "&nbsp;"*fut_w
        row = f"{n.ljust(label_w).replace(' ', '&nbsp;')}&nbsp;|{scell}|&nbsp;|{fcell}|"
        lines.append(row)

    # Δ без PanSwap
    all_prices: List[float] = []
    for n, sp, ft in formatted:
        if n == "PanSwap": continue
        if isinstance(sp, (int, float)): all_prices.append(sp)
        if isinstance(ft, (int, float)): all_prices.append(ft)
    delta_pct = (max(all_prices) - min(all_prices)) / min(all_prices) * 100.0 if all_prices and min(all_prices)>0 else 0.0

    tail = f"d-{delta_pct:.1f}%"
    if coin.upper() in BLACKLIST_COINS:
        tail += "  ⚠️Blacklist, разница цен на биржах или есть монеты с таким же названием"

    return "<b>" + "<br>".join(lines) + f"</b><br>{tail}"

# ====================== Извлечение тикера ======================

TICKER_RE = re.compile(r"[A-Za-z0-9]{1,15}")
def extract_symbol(text: str, entities: List[MessageEntity]) -> Optional[str]:
    if not text:
        return None
    mention_spans = []
    for ent in entities or []:
        if ent.type == "mention":
            mention_spans.append((ent.offset, ent.length))
    if not mention_spans:
        return None
    start = mention_spans[0][0] + mention_spans[0][1]
    tail = text[start:].strip()
    m = TICKER_RE.search(tail)
    if not m:
        return None
    token = m.group(0).upper()
    if token.endswith("USDT"):
        token = token[:-4]
    return token or None

# ====================== Handler ======================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    msg  = update.effective_message
    log(f"[handle start] chat={chat.id} update_id={update.update_id} text={getattr(msg, 'text','')!r}")

    try:
        if chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
            return

        text = msg.text or ""
        mentioned = any(
            ent.type == "mention" and (text[ent.offset: ent.offset + ent.length].lstrip("@").lower() == BOT_USERNAME.lower())
            for ent in (msg.entities or [])
        )
        if not mentioned:
            return

        coin = extract_symbol(text, msg.entities or [])
        if not coin:
            await msg.reply_text("❌ Не удалось распознать тикер. Пример: @a1price_bot BTC или @a1price_bot BTCUSDT")
            return

        with_links = "ссылки" in (text or "").lower()  # режим ссылок

        log(f"==== Request for {coin} (links={with_links}) from chat {chat.id} ====")

        rows: Dict[str, Dict[str, Optional[float]]] = {}
        urls: Dict[str, Dict[str, Optional[str]]] = {}
        changed = asyncio.Event()
        state = MsgState()

        loop = asyncio.get_event_loop()
        grace_until = loop.time() + NOT_FOUND_GRACE_SEC

        def mark_changed():
            if not changed.is_set():
                changed.set()

        async def run_one(name: str, want_type: str, ex: Optional[ccxt.Exchange]):
            if name not in rows:
                rows[name] = {"spot": None, "fut": None}

            # PanSwap — только спот
            if name == "PanSwap":
                if want_type == "spot":
                    try:
                        price = await panswap_spot_price(coin)
                        if price is not None:
                            if rows[name]["spot"] != price:
                                rows[name]["spot"] = price
                                mark_changed()
                        else:
                            log(f"[{name}/{want_type}] {coin}: не удалось получить цену")
                    except Exception as e:
                        log(f"[{name}/{want_type}] {coin}: ошибка получения цены: {e!r}")
                return

            try:
                pick = await build_pick(ex, name, coin, want_type) if ex is not None else None
                if pick is None and name not in ("OKX", "MEXC"):
                    log(f"[{name}/{want_type}] {coin}: маркет не найден")
                    return

                urls.setdefault(name, {"spot": None, "fut": None})
                urls[name]["spot" if want_type=="spot" else "fut"] = build_pair_url(name, "spot" if want_type=="spot" else "swap", coin)

                if want_type == "spot":
                    price = None
                    if pick:
                        try:
                            if name == "MEXC":
                                price = await fetch_spot_mid_mexcfast(ex, pick.symbol, coin)
                                if price is None:
                                    await asyncio.sleep(0.2)
                                    price = await fetch_spot_mid_mexcfast(ex, pick.symbol, coin)
                            else:
                                price = await fetch_spot_mid_standard(ex, pick.symbol, name, coin)
                        except Exception as e:
                            log(f"[{name}/{want_type}] {coin}: ошибка получения цены spot: {e!r}")
                    
                    # Для MEXC spot пробуем получить цену даже если pick не найден
                    if name == "MEXC" and price is None and pick is None:
                        # Пробуем стандартный символ
                        try_symbols = [f"{coin}/USDT", f"{coin}USDT"]
                        for try_sym in try_symbols:
                            try:
                                price = await fetch_spot_mid_mexcfast(ex, try_sym, coin)
                                if price is not None:
                                    log(f"[MEXC/spot] {coin}: got price using fallback symbol {try_sym}, price={price}")
                                    break
                            except Exception as e:
                                log(f"[MEXC/spot] {coin}: fallback symbol {try_sym} failed: {e!r}")
                                continue

                    if name == "OKX" and price is None:
                        try:
                            http_mid = await okx_http_spot_mid(coin)
                            if isinstance(http_mid, (int, float)):
                                price = http_mid
                                log(f"[OKX/spot] {coin}: HTTP fallback mid={price}")
                        except Exception as e:
                            log(f"[OKX/spot] {coin}: ошибка HTTP fallback: {e!r}")

                    if price is None:
                        log(f"[{name}/{want_type}] {coin}: не удалось получить цену")
                    elif rows[name]["spot"] != price:
                        rows[name]["spot"] = price
                        mark_changed()

                else:
                    price = None
                    if pick:
                        try:
                            price = await fetch_fut_last(ex, pick.symbol, name, coin)
                        except Exception as e:
                            log(f"[{name}/{want_type}] {coin}: ошибка получения цены futures: {e!r}")

                    if name == "OKX" and price is None:
                        try:
                            http_last = await okx_http_swap_last(coin)
                            if isinstance(http_last, (int, float)):
                                price = http_last
                                log(f"[OKX/swap] {coin}: HTTP fallback last={price}")
                        except Exception as e:
                            log(f"[OKX/swap] {coin}: ошибка HTTP fallback: {e!r}")

                    if price is None:
                        log(f"[{name}/{want_type}] {coin}: не удалось получить цену")
                    elif rows[name]["fut"] != price:
                        rows[name]["fut"] = price
                        mark_changed()

            except asyncio.CancelledError:
                return
            except Exception as e:
                log(f"[{name}/{want_type}] {coin}: неожиданная ошибка: {e!r}")

        names = ["Binance","Bybit","Bitget","Gate","HTX","MEXC","KuCoin","BingX","OKX","PanSwap"]

        async def maybe_edit():
            suppress = loop.time() < grace_until
            core = (
                render_table_text_links(coin, rows, urls, suppress_not_found=suppress)
                if with_links
                else render_table_text(coin, rows, suppress_not_found=suppress)
            )
            text_html = core
            if text_html != state.last_text:
                now = loop.time()
                wait = max(0.0, (state.last_edit_at + UPDATE_DEBOUNCE_SEC) - now)
                if wait:
                    await asyncio.sleep(wait)
                if state.sent is None:
                    try:
                        state.sent = await msg.reply_text(text_html, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
                        state.last_text = text_html
                        state.last_edit_at = loop.time()
                        log(f"[edit] sent initial table for {coin}")
                    except Exception as e:
                        log(f"[edit] send error: {e!r}")
                else:
                    with contextlib.suppress(Exception):
                        await state.sent.edit_text(text_html, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
                        state.last_text = text_html
                        state.last_edit_at = loop.time()
                        log(f"[edit] updated table for {coin}")

        async def run_round(round_num: int):
            """Запускает один раунд запросов ко всем биржам"""
            log(f"---- Round {round_num} start for {coin} ----")
            changed.clear()
            
            tasks: List[asyncio.Task] = []
            for n in names:
                tasks.append(context.application.create_task(run_one(n, "spot", MANAGER.exchanges_spot.get(n))))
                tasks.append(context.application.create_task(run_one(n, "swap", MANAGER.exchanges_fut.get(n))))
            
            # Обновляем сообщение по мере поступления цен
            # Ждем завершения всех задач, обновляя сообщение при изменениях
            update_task = None
            
            async def update_loop():
                """Цикл обновления сообщения при изменениях"""
                while True:
                    try:
                        await asyncio.wait_for(changed.wait(), timeout=0.5)
                        changed.clear()
                        await maybe_edit()
                    except asyncio.TimeoutError:
                        # Проверяем, все ли задачи завершены
                        if all(t.done() for t in tasks):
                            break
                        continue
            
            update_task = context.application.create_task(update_loop())
            
            # Ждем завершения всех задач
            await asyncio.gather(*tasks, return_exceptions=True)
            
            # Отменяем цикл обновления и ждем его завершения
            if update_task and not update_task.done():
                update_task.cancel()
                try:
                    await asyncio.wait_for(update_task, timeout=1.0)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass
            
            # Финальное обновление после завершения всех задач
            await maybe_edit()
            log(f"---- Round {round_num} end for {coin} ----")

        # Первый раунд - сразу
        round1_start_time = loop.time()
        check_task = None
        should_skip_round2 = False
        
        async def check_no_price():
            """Проверяет через 20 секунд, есть ли цены"""
            nonlocal should_skip_round2
            try:
                await asyncio.sleep(NO_PRICE_TIMEOUT)
                # Проверяем еще раз, возможно цены появились
                has_any_price = any(
                    (row.get("spot") is not None or row.get("fut") is not None)
                    for row in rows.values()
                )
                if not has_any_price:
                    log(f"---- No prices found for {coin} after {NO_PRICE_TIMEOUT}s, will skip Round 2 ----")
                    should_skip_round2 = True
                    if state.sent:
                        try:
                            await state.sent.edit_text(
                                f"❌ Монета <b>{coin}</b> не найдена на биржах",
                                parse_mode=ParseMode.HTML
                            )
                            log(f"[edit] sent 'not found' message for {coin}")
                        except Exception as e:
                            log(f"[edit] error sending 'not found' message: {e!r}")
            except asyncio.CancelledError:
                pass
        
        try:
            # Запускаем проверку параллельно с первым раундом
            check_task = context.application.create_task(check_no_price())
            
            await run_round(1)
            log(f"---- Round 1 completed for {coin} ----")
            
            # Отменяем проверку, если первый раунд завершился раньше
            if check_task and not check_task.done():
                check_task.cancel()
                with contextlib.suppress(Exception):
                    await check_task
                
                # Проверяем наличие цен после завершения первого раунда
                has_any_price = any(
                    (row.get("spot") is not None or row.get("fut") is not None)
                    for row in rows.values()
                )
                if not has_any_price:
                    log(f"---- No prices found for {coin} after Round 1, will skip Round 2 ----")
                    should_skip_round2 = True
                    if state.sent:
                        try:
                            await state.sent.edit_text(
                                f"❌ Монета <b>{coin}</b> не найдена на биржах",
                                parse_mode=ParseMode.HTML
                            )
                            log(f"[edit] sent 'not found' message for {coin}")
                        except Exception as e:
                            log(f"[edit] error sending 'not found' message: {e!r}")
        except Exception as e:
            log(f"---- Round 1 error for {coin}: {e!r} ----")
            # Отменяем проверку при ошибке
            if check_task and not check_task.done():
                check_task.cancel()
                with contextlib.suppress(Exception):
                    await check_task
            raise
        
        # Если нужно пропустить второй раунд - завершаем
        if should_skip_round2:
            log(f"---- Skipping Round 2 for {coin} (no prices found) ----")
            return
        
        # Если есть цены - продолжаем со вторым раундом
        log(f"---- Prices found for {coin}, waiting {SECOND_ROUND_DELAY}s before Round 2 ----")
        
        # Второй раунд - через 30 секунд
        try:
            await asyncio.sleep(SECOND_ROUND_DELAY)
            log(f"---- Starting Round 2 for {coin} ----")
            await run_round(2)
            log(f"---- Round 2 completed for {coin} ----")
        except Exception as e:
            log(f"---- Round 2 error for {coin}: {e!r} ----")
            raise

    finally:
        log(f"[handle end]   chat={chat.id} update_id={update.update_id}")

# ====================== Запуск ======================

async def post_init(app: Application) -> None:
    """Инициализация ExchangeManager после создания event loop"""
    await MANAGER.init()

def build_application():
    request = HTTPXRequest(
        connect_timeout=10.0,
        read_timeout=90.0,   # > long-poll timeout
        write_timeout=90.0,
        pool_timeout=10.0,
    )

    application = (
        Application
        .builder()
        .token(BOT_TOKEN)
        .request(request)
        .concurrent_updates(True)   # параллельные апдейты
        .post_init(post_init)
        .build()
    )

    application.add_handler(MessageHandler(filters.TEXT & filters.Entity("mention"), handle_message))
    return application

if __name__ == "__main__":
    app = build_application()
    # Синхронный polling — внутри сам управляет своим loop
    app.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
        poll_interval=0.5,
        timeout=30,    # long-poll timeout (сек)
    )
