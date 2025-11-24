"""
Модуль для детекта стрел (spikes) на основе фильтров пользователей
"""
import json
import time
from collections import defaultdict
from typing import Dict, List, Optional, Tuple
from core.candle_builder import Candle
from BD.database import db
from core.logger import get_logger

logger = get_logger(__name__)


class SpikeDetector:
    """Детектор стрел на основе свечей и фильтров пользователей"""
    
    def __init__(self):
        """Инициализация детектора"""
        self._users_cache: Optional[List[Dict]] = None
        self._cache_timestamp = 0.0
        self._cache_ttl = 5.0  # Кэш пользователей на 5 секунд (было 30) для более быстрого обновления настроек
        
        # Трекер серий стрел: {user_id: {exchange_market_symbol: [{"ts_ms": int, "timestamp": float, "delta": float, "volume_usdt": float, "wick_pct": float, "direction": str, "detected_by_spike_settings": bool, "detected_by_strategy": bool}]}}
        # Хранит временные метки и параметры последних стрел для каждой пары exchange+market+symbol для каждого пользователя
        # Уникальность: {user_id}_{exchange}_{market}_{symbol}_{ts_ms}
        self._series_tracker: Dict[int, Dict[str, List[Dict]]] = defaultdict(lambda: defaultdict(list))
        
        # Настройки для управления памятью
        self._max_spikes_per_symbol = 1000  # Максимальное количество записей на символ
        self._default_ttl_seconds = 900  # TTL по умолчанию: 15 минут (900 секунд)
        self._last_cleanup_time = time.time()  # Время последней очистки
        self._cleanup_interval = 300  # Интервал периодической очистки: 5 минут (для более частой очистки)
    
    def _get_users(self) -> List[Dict]:
        """
        Получает всех пользователей с кэшированием
        
        Returns:
            List[Dict]: Список пользователей с их настройками
        """
        import time
        current_time = time.time()
        
        # Если кэш актуален, возвращаем его
        if self._users_cache is not None and (current_time - self._cache_timestamp) < self._cache_ttl:
            return self._users_cache
        
        # Обновляем кэш
        try:
            import asyncio
            # Проверяем, есть ли уже запущенный event loop
            try:
                loop = asyncio.get_running_loop()
                # Если loop уже запущен, создаём новый loop в отдельном потоке
                # Это безопаснее, чем пытаться использовать существующий loop из синхронного контекста
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, db.get_all_users())
                    users = future.result()
            except RuntimeError:
                # Нет запущенного event loop, можем использовать asyncio.run()
                users = asyncio.run(db.get_all_users())
            self._users_cache = users
            self._cache_timestamp = current_time
            return users
        except Exception as e:
            logger.error(f"Ошибка при получении пользователей: {e}", exc_info=True, extra={
                "log_to_db": True,
                "error_type": "spike_detector_db_error",
                "market": "spike_detector",
            })
            return self._users_cache or []
    
    def _parse_user_options(self, options_json: str) -> Dict:
        """
        Парсит options_json пользователя
        
        Args:
            options_json: JSON строка с настройками
            
        Returns:
            Dict: Распарсенные настройки (без дефолтных порогов)
        """
        try:
            if not options_json:
                return self._get_default_options()
            
            options = json.loads(options_json)
            
            # Дефолтные настройки только для exchanges (включение/выключение бирж)
            default = self._get_default_options()
            exchanges = options.get("exchanges", default["exchanges"])
            
            # Сохраняем thresholds БЕЗ дефолтных значений - только то, что есть у пользователя
            thresholds = options.get("thresholds", {})
            
            # Сохраняем exchangeSettings для использования в проверке порогов
            exchange_settings = options.get("exchangeSettings", {})
            
            # Сохраняем pairSettings для индивидуальных настроек пар
            pair_settings = options.get("pairSettings", {})
            
            # Сохраняем conditionalTemplates (стратегии) для проверки условий
            conditional_templates = options.get("conditionalTemplates", [])
            
            return {
                "thresholds": thresholds,  # Используем только пользовательские настройки, без дефолтов
                "exchanges": {
                    "gate": bool(exchanges.get("gate", default["exchanges"]["gate"])),
                    "binance": bool(exchanges.get("binance", default["exchanges"]["binance"])),
                    "bitget": bool(exchanges.get("bitget", default["exchanges"]["bitget"])),
                    "bybit": bool(exchanges.get("bybit", default["exchanges"]["bybit"])),
                    "hyperliquid": bool(exchanges.get("hyperliquid", default["exchanges"]["hyperliquid"])),
                },
                "exchangeSettings": exchange_settings,
                "pairSettings": pair_settings,
                "conditionalTemplates": conditional_templates
            }
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            logger.warning(f"Ошибка парсинга options_json: {e}, настройки не применятся", extra={
                "log_to_db": True,
                "error_type": "spike_detector_parse_error",
                "market": "spike_detector",
            })
            return self._get_default_options()
    
    def _get_default_options(self) -> Dict:
        """Возвращает дефолтные настройки фильтров (все биржи отключены по умолчанию)"""
        return {
            "thresholds": {},  # Нет дефолтных порогов - используются только пользовательские настройки
            "exchanges": {
                "gate": False,
                "binance": False,
                "bitget": False,
                "bybit": False,
                "hyperliquid": False,
            },
            "exchangeSettings": {},
            "pairSettings": {}
        }
    
    def _extract_quote_currency(self, symbol: str, exchange: str) -> Optional[str]:
        """
        Извлекает котируемую валюту из символа
        
        Args:
            symbol: Символ торговой пары (например, "BTCUSDT", "ETH_TRY", "LTC-TRY")
            exchange: Название биржи (binance, gate, bitget, bybit, hyperliquid)
            
        Returns:
            Optional[str]: Котируемая валюта (USDT, TRY, USDC и т.д.) или None если не удалось определить
        """
        # Список известных котируемых валют (в порядке убывания длины для правильного поиска)
        quote_currencies = [
            "USDT", "USDC", "TRY", "BTC", "ETH", "BNB", "EUR", "GBP", "AUD", "BRL",
            "TUSD", "FDUSD", "BIDR", "TRX", "DOGE", "AEUR"
        ]
        
        exchange_lower = exchange.lower()
        symbol_upper = symbol.upper()
        
        # Gate использует подчёркивание: BTC_USDT -> USDT
        if exchange_lower == "gate" and "_" in symbol_upper:
            parts = symbol_upper.split("_")
            if len(parts) >= 2:
                return parts[-1]  # Последняя часть после подчёркивания
        
        # Дефис используется некоторыми биржами: LTC-TRY -> TRY
        if "-" in symbol_upper:
            parts = symbol_upper.split("-")
            if len(parts) >= 2:
                return parts[-1]  # Последняя часть после дефиса
        
        # Слэш используется некоторыми биржами: BTC/USDT -> USDT
        if "/" in symbol_upper:
            parts = symbol_upper.split("/")
            if len(parts) >= 2:
                return parts[-1]  # Последняя часть после слэша
        
        # Для символов без разделителя ищем котируемую валюту в конце символа
        # Проверяем от самых длинных к коротким (USDT перед USD)
        for quote in sorted(quote_currencies, key=len, reverse=True):
            if symbol_upper.endswith(quote):
                return quote
        
        # Если не нашли - возвращаем None
        return None
    
    def _calculate_delta(self, candle: Candle) -> float:
        """
        Вычисляет максимальное изменение цены в процентах
        (от открытия к максимальному отклонению - хаю или лою)
        
        Args:
            candle: Свеча
            
        Returns:
            float: Дельта в процентах (максимальное отклонение от открытия)
        """
        if candle.open == 0:
            return 0.0
        
        # Вычисляем отклонение к хаю и к лою
        delta_high = ((candle.high - candle.open) / candle.open) * 100
        delta_low = ((candle.low - candle.open) / candle.open) * 100
        
        # Возвращаем максимальное абсолютное отклонение
        return max(abs(delta_high), abs(delta_low))
    
    def _calculate_wick_pct(self, candle: Candle) -> float:
        """
        Вычисляет процент тени свечи (верхняя + нижняя тень относительно тела)
        
        Args:
            candle: Свеча
            
        Returns:
            float: Процент тени (0-100)
        """
        body_size = abs(candle.close - candle.open)
        total_range = candle.high - candle.low
        
        if total_range == 0:
            return 0.0
        
        wick_size = total_range - body_size
        wick_pct = (wick_size / total_range) * 100
        
        return wick_pct
    
    def _calculate_volume_usdt(self, candle: Candle) -> float:
        """
        Вычисляет объём в USDT
        
        Args:
            candle: Свеча
            
        Returns:
            float: Объём в USDT (используем close * volume как приближение)
        """
        # Для USDT пар volume уже в базовой валюте (например, BTC)
        # Для конвертации в USDT умножаем на цену закрытия
        volume_usdt = candle.volume * candle.close
        return volume_usdt
    
    def _check_exchange_filter(self, exchange: str, user_options: Dict) -> bool:
        """
        Проверяет, включена ли биржа для пользователя
        
        Args:
            exchange: Название биржи
            user_options: Настройки пользователя
            
        Returns:
            bool: True если биржа включена
        """
        exchanges = user_options.get("exchanges", {})
        
        # Маппинг названий бирж
        exchange_map = {
            "binance": "binance",
            "gate": "gate",
            "bitget": "bitget",
            "bybit": "bybit",
            "hyperliquid": "hyperliquid",
        }
        
        exchange_key = exchange_map.get(exchange.lower(), exchange.lower())
        # Если биржа не указана в настройках, считаем её отключенной (False)
        # Это гарантирует, что пользователи с нулевыми настройками не будут получать детекты
        return exchanges.get(exchange_key, False)
    
    def _check_strategy_exchange_condition(self, strategy: Dict, candle: Candle) -> Tuple[bool, bool]:
        """
        Проверяет, соответствует ли свеча условию биржи в стратегии
        
        Args:
            strategy: Словарь стратегии с полями:
                - conditions: List[Dict] - список условий
            candle: Свеча для проверки
            
        Returns:
            Tuple[bool, bool]: (соответствует_ли_условию, есть_ли_условие_биржа)
                - Первое значение: True если свеча соответствует условию биржи (или условие не указано)
                - Второе значение: True если в стратегии есть условие биржи (exchange или exchange_market)
        """
        conditions = strategy.get("conditions", [])
        
        # Ищем условия биржи
        exchange_condition = None
        exchange_market_condition = None
        
        for condition in conditions:
            cond_type = condition.get("type")
            if cond_type == "exchange":
                exchange_condition = condition
            elif cond_type == "exchange_market":
                exchange_market_condition = condition
        
        # Если нет условий биржи - возвращаем True (условие не указано, значит работает для всех бирж)
        if not exchange_condition and not exchange_market_condition:
            return True, False
        
        # Проверяем условие exchange_market (приоритет, так как более специфичное)
        if exchange_market_condition:
            condition_exchange_market = exchange_market_condition.get("exchange_market")
            if condition_exchange_market:
                # Формат: "exchange_market" (например, "binance_spot", "bybit_futures")
                parts = condition_exchange_market.lower().split("_", 1)
                if len(parts) == 2:
                    condition_exchange, condition_market = parts
                    
                    # Нормализуем рынок: "futures" и "linear" - одно и то же
                    if condition_market == "linear":
                        condition_market = "futures"
                    
                    # Сравниваем биржу
                    if candle.exchange.lower() != condition_exchange.lower():
                        return False, True
                    
                    # Нормализуем и сравниваем тип рынка
                    market_mapping = {
                        "futures": "linear",
                        "linear": "linear",
                        "spot": "spot"
                    }
                    
                    candle_market = market_mapping.get(candle.market.lower(), candle.market.lower())
                    condition_market_normalized = market_mapping.get(condition_market.lower(), condition_market.lower())
                    
                    return candle_market == condition_market_normalized, True
        
        # Проверяем условие exchange (если не было exchange_market)
        if exchange_condition:
            condition_exchange = exchange_condition.get("exchange") or exchange_condition.get("value")
            if condition_exchange:
                # Проверяем биржу
                return candle.exchange.lower() == condition_exchange.lower(), True
        
        # Если условие указано, но не распознано - возвращаем False
        return False, True
    
    def _check_thresholds(self, candle: Candle, user_options: Dict) -> Tuple[bool, Dict]:
        """
        Проверяет, соответствует ли свеча порогам пользователя
        
        Логика приоритета настроек:
        1. Если для конкретной пары есть индивидуальные настройки в pairSettings - используем их
        2. Если для конкретной пары нет индивидуальных настроек, но есть дополнительные пары для рынка - не применяем детектирование (пара отключена)
        3. Если дополнительных пар нет - используем глобальные настройки exchangeSettings[exchange][market]
        4. Если нет exchangeSettings - используем глобальные thresholds
        
        Args:
            candle: Свеча для проверки
            user_options: Настройки пользователя
            
        Returns:
            Tuple[bool, Dict]: (соответствует ли фильтрам, метрики свечи)
        """
        # Вычисляем метрики
        delta = self._calculate_delta(candle)
        wick_pct = self._calculate_wick_pct(candle)
        volume_usdt = self._calculate_volume_usdt(candle)
        
        exchange_key = candle.exchange.lower()
        market_key = "futures" if candle.market == "linear" else "spot"
        
        # Извлекаем котируемую валюту из символа
        quote_currency = self._extract_quote_currency(candle.symbol, candle.exchange)
        
        # Получаем pairSettings
        pair_settings = user_options.get("pairSettings", {})
        
        # Формируем ключ для поиска индивидуальных настроек пары: {exchange}_{market}_{pair}
        pair_key = None
        if quote_currency:
            pair_key = f"{exchange_key}_{market_key}_{quote_currency}"
        
        # ШАГ 1: Проверяем индивидуальные настройки для конкретной пары
        if pair_key and pair_settings and pair_key in pair_settings:
            pair_config = pair_settings[pair_key]
            
            # Проверяем, включена ли эта пара
            if not pair_config.get("enabled", True):
                logger.debug(f"Пара {pair_key} отключена для пользователя")
                return False, {"delta": delta, "wick_pct": wick_pct, "volume_usdt": volume_usdt}
            
            # Получаем пороги из индивидуальных настроек пары
            try:
                delta_str = pair_config.get("delta")
                volume_str = pair_config.get("volume")
                shadow_str = pair_config.get("shadow")
                
                # Если хотя бы одно значение отсутствует или пустое - не пропускаем детект
                if delta_str is None or volume_str is None or shadow_str is None:
                    logger.debug(f"Неполные настройки для пары {pair_key}: delta={delta_str}, volume={volume_str}, shadow={shadow_str}")
                    return False, {"delta": delta, "wick_pct": wick_pct, "volume_usdt": volume_usdt}
                
                # Проверяем, что значения не пустые строки
                if delta_str == "" or volume_str == "" or shadow_str == "":
                    logger.debug(f"Пустые настройки для пары {pair_key}: delta={delta_str}, volume={volume_str}, shadow={shadow_str}")
                    return False, {"delta": delta, "wick_pct": wick_pct, "volume_usdt": volume_usdt}
                
                delta_min = float(delta_str)
                volume_min = float(volume_str)
                wick_pct_max = float(shadow_str)

                # Значение 0 или меньше означает, что пользователь не задал фильтр
                if delta_min <= 0 or volume_min <= 0 or wick_pct_max <= 0:
                    logger.debug(
                        f"Игнорируем фильтры пары {pair_key}: delta={delta_min}, volume={volume_min}, shadow={wick_pct_max} (не заданы пользователем)"
                    )
                    return False, {"delta": delta, "wick_pct": wick_pct, "volume_usdt": volume_usdt}
                
                logger.debug(f"Проверка индивидуальных фильтров для пары {pair_key}: delta_min={delta_min}, volume_min={volume_min}, wick_pct_max={wick_pct_max}")
                logger.debug(f"Фактические значения: delta={delta:.2f}, volume={volume_usdt:.2f}, wick_pct={wick_pct:.2f}")
                
                # Проверяем пороги
                if delta <= delta_min:
                    logger.debug(f"Дельта {delta:.2f}% <= {delta_min}% - фильтр не пройден (нужно строго больше)")
                    return False, {"delta": delta, "wick_pct": wick_pct, "volume_usdt": volume_usdt}
                
                if volume_usdt <= volume_min:
                    logger.debug(f"Объём {volume_usdt:.2f} <= {volume_min} - фильтр не пройден (нужно строго больше)")
                    return False, {"delta": delta, "wick_pct": wick_pct, "volume_usdt": volume_usdt}
                
                if wick_pct <= wick_pct_max:
                    logger.debug(f"Тень {wick_pct:.2f}% <= {wick_pct_max}% - фильтр не пройден (нужно строго больше)")
                    return False, {"delta": delta, "wick_pct": wick_pct, "volume_usdt": volume_usdt}
                
                # Все проверки пройдены
                logger.debug(f"Все индивидуальные фильтры пройдены для пары {pair_key}: delta={delta:.2f}% > {delta_min}%, volume={volume_usdt:.2f} > {volume_min}, wick_pct={wick_pct:.2f}% > {wick_pct_max}%")
                return True, {"delta": delta, "wick_pct": wick_pct, "volume_usdt": volume_usdt}
                
            except (ValueError, TypeError) as e:
                logger.warning(f"Ошибка парсинга настроек пары {pair_key}: {e}")
                return False, {"delta": delta, "wick_pct": wick_pct, "volume_usdt": volume_usdt}
        
        # ШАГ 2: Проверяем, есть ли дополнительные пары для этого рынка
        # Если есть хотя бы одна дополнительная пара с настройками для этого рынка, но для текущей пары нет индивидуальных настроек,
        # значит пользователь отключил или не включал отслеживание детектов для этой пары - детектирование не применяется
        if pair_settings:
            # Проверяем, есть ли дополнительные пары для этого exchange и market
            has_additional_pairs = False
            for key in pair_settings.keys():
                # Ключ формата: {exchange}_{market}_{pair}
                if key.startswith(f"{exchange_key}_{market_key}_"):
                    has_additional_pairs = True
                    break
            
            # Если есть дополнительные пары для этого рынка, но для текущей пары нет индивидуальных настроек
            # Значит пользователь не включил отслеживание для этой пары - детектирование не применяется
            if has_additional_pairs:
                logger.debug(f"Для рынка {exchange_key} {market_key} есть дополнительные пары, но для текущей пары ({quote_currency or 'unknown'}) нет индивидуальных настроек - детектирование не применяется (пара не включена пользователем)")
                return False, {"delta": delta, "wick_pct": wick_pct, "volume_usdt": volume_usdt}
        
        # ШАГ 3: Используем глобальные настройки exchangeSettings[exchange][market]
        exchange_settings = user_options.get("exchangeSettings", {})
        if exchange_settings and exchange_key in exchange_settings:
            exchange_config = exchange_settings[exchange_key]
            market_config = exchange_config.get(market_key, {})
            
            # Проверяем, включён ли этот рынок
            if not market_config.get("enabled", True):
                logger.debug(f"Рынок {exchange_key} {market_key} отключен для пользователя")
                return False, {"delta": delta, "wick_pct": wick_pct, "volume_usdt": volume_usdt}
            
            # Получаем пороги из настроек биржи (БЕЗ дефолтных значений)
            try:
                delta_str = market_config.get("delta")
                volume_str = market_config.get("volume")
                shadow_str = market_config.get("shadow")
                
                # Если хотя бы одно значение отсутствует или пустое - не пропускаем детект
                if delta_str is None or volume_str is None or shadow_str is None:
                    logger.debug(f"Неполные настройки для {exchange_key} {market_key}: delta={delta_str}, volume={volume_str}, shadow={shadow_str}")
                    return False, {"delta": delta, "wick_pct": wick_pct, "volume_usdt": volume_usdt}
                
                # Проверяем, что значения не пустые строки
                if delta_str == "" or volume_str == "" or shadow_str == "":
                    logger.debug(f"Пустые настройки для {exchange_key} {market_key}: delta={delta_str}, volume={volume_str}, shadow={shadow_str}")
                    return False, {"delta": delta, "wick_pct": wick_pct, "volume_usdt": volume_usdt}
                
                delta_min = float(delta_str)
                volume_min = float(volume_str)
                wick_pct_max = float(shadow_str)

                # Значение 0 или меньше означает, что пользователь не задал фильтр
                if delta_min <= 0 or volume_min <= 0 or wick_pct_max <= 0:
                    logger.debug(
                        f"Игнорируем фильтры {exchange_key} {market_key}: delta={delta_min}, volume={volume_min}, shadow={wick_pct_max} (не заданы пользователем)"
                    )
                    return False, {"delta": delta, "wick_pct": wick_pct, "volume_usdt": volume_usdt}
                
                logger.debug(f"Проверка глобальных фильтров для {exchange_key} {market_key}: delta_min={delta_min}, volume_min={volume_min}, wick_pct_max={wick_pct_max}")
                logger.debug(f"Фактические значения: delta={delta:.2f}, volume={volume_usdt:.2f}, wick_pct={wick_pct:.2f}")
                
                # Проверяем пороги
                if delta <= delta_min:
                    logger.debug(f"Дельта {delta:.2f}% <= {delta_min}% - фильтр не пройден (нужно строго больше)")
                    return False, {"delta": delta, "wick_pct": wick_pct, "volume_usdt": volume_usdt}
                
                if volume_usdt <= volume_min:
                    logger.debug(f"Объём {volume_usdt:.2f} <= {volume_min} - фильтр не пройден (нужно строго больше)")
                    return False, {"delta": delta, "wick_pct": wick_pct, "volume_usdt": volume_usdt}
                
                if wick_pct <= wick_pct_max:
                    logger.debug(f"Тень {wick_pct:.2f}% <= {wick_pct_max}% - фильтр не пройден (нужно строго больше)")
                    return False, {"delta": delta, "wick_pct": wick_pct, "volume_usdt": volume_usdt}
                
                # Все проверки пройдены
                logger.debug(f"Все глобальные фильтры пройдены для {exchange_key} {market_key}: delta={delta:.2f}% > {delta_min}%, volume={volume_usdt:.2f} > {volume_min}, wick_pct={wick_pct:.2f}% > {wick_pct_max}%")
                return True, {"delta": delta, "wick_pct": wick_pct, "volume_usdt": volume_usdt}
                
            except (ValueError, TypeError) as e:
                logger.warning(f"Ошибка парсинга настроек биржи {exchange_key} {market_key}: {e}")
                return False, {"delta": delta, "wick_pct": wick_pct, "volume_usdt": volume_usdt}
        
        # ШАГ 4: Если нет exchangeSettings, проверяем глобальные thresholds
        thresholds = user_options.get("thresholds", {})
        
        # Если нет настроек вообще - не пропускаем детект
        if not thresholds:
            logger.debug(f"Нет настроек фильтров для {exchange_key} {market_key} {candle.symbol}")
            return False, {"delta": delta, "wick_pct": wick_pct, "volume_usdt": volume_usdt}
        
        # Используем глобальные пороги (БЕЗ дефолтных значений)
        delta_min = thresholds.get("delta_pct")
        volume_min = thresholds.get("volume_usdt")
        wick_pct_max = thresholds.get("wick_pct")
        
        # Если хотя бы одно значение отсутствует - не пропускаем детект
        if delta_min is None or volume_min is None or wick_pct_max is None:
            logger.debug(f"Неполные глобальные пороги: delta_pct={delta_min}, volume_usdt={volume_min}, wick_pct={wick_pct_max}")
            return False, {"delta": delta, "wick_pct": wick_pct, "volume_usdt": volume_usdt}

        try:
            delta_min = float(delta_min)
            volume_min = float(volume_min)
            wick_pct_max = float(wick_pct_max)
        except (ValueError, TypeError) as e:
            logger.warning(f"Ошибка парсинга глобальных порогов пользователя: {e}")
            return False, {"delta": delta, "wick_pct": wick_pct, "volume_usdt": volume_usdt}

        if delta_min <= 0 or volume_min <= 0 or wick_pct_max <= 0:
            logger.debug(
                f"Игнорируем глобальные пороги: delta={delta_min}, volume={volume_min}, shadow={wick_pct_max} (не заданы пользователем)"
            )
            return False, {"delta": delta, "wick_pct": wick_pct, "volume_usdt": volume_usdt}
        
        # Проверяем пороги
        if delta <= delta_min:
            logger.debug(f"Дельта {delta:.2f}% <= {delta_min}% - фильтр не пройден (нужно строго больше)")
            return False, {"delta": delta, "wick_pct": wick_pct, "volume_usdt": volume_usdt}
        
        if volume_usdt <= volume_min:
            logger.debug(f"Объём {volume_usdt:.2f} <= {volume_min} - фильтр не пройден (нужно строго больше)")
            return False, {"delta": delta, "wick_pct": wick_pct, "volume_usdt": volume_usdt}
        
        if wick_pct <= wick_pct_max:
            logger.debug(f"Тень {wick_pct:.2f}% <= {wick_pct_max}% - фильтр не пройден (нужно строго больше)")
            return False, {"delta": delta, "wick_pct": wick_pct, "volume_usdt": volume_usdt}
        
        # Все проверки пройдены
        logger.debug(f"Все глобальные пороги пройдены: delta={delta:.2f}% > {delta_min}%, volume={volume_usdt:.2f} > {volume_min}, wick_pct={wick_pct:.2f}% > {wick_pct_max}%")
        return True, {"delta": delta, "wick_pct": wick_pct, "volume_usdt": volume_usdt}
    
    def _get_series_count(self, user_id: int, candle: Candle, time_window_seconds: float, 
                          conditions: Optional[List[Dict]] = None) -> int:
        """
        Получает количество стрел за указанное время для данной пары exchange+market+symbol
        с учетом всех условий стратегии (delta, volume, wick_pct, direction, symbol, exchange, market)
        
        **Важно:** Текущая стрела НЕ учитывается в подсчете серии, так как она еще не добавлена в трекер
        на момент проверки. Это гарантирует правильную логику: при каждой новой стреле мы смотрим назад
        на предыдущие стрелы, и если их достаточно (≥ count) → отправляем сигнал.
        
        Args:
            user_id: ID пользователя
            candle: Текущая свеча (используется для определения временного окна)
            time_window_seconds: Временное окно в секундах (смотрим назад от момента текущей стрелы)
            conditions: Список условий для проверки (опционально). Если указан, 
                       считаются только стрелы, соответствующие **всем** условиям стратегии
                       (delta, volume, wick_pct, direction, symbol, exchange, market)
            
        Returns:
            int: Количество стрел за указанное время (соответствующих условиям, если они указаны)
        """
        # Используем timestamp свечи в миллисекундах для определения временного окна
        # Смотрим назад на timeWindowSeconds от момента текущей стрелы
        current_ts_ms = candle.ts_ms
        window_start_ts_ms = current_ts_ms - int(time_window_seconds * 1000)
        
        key = f"{candle.exchange}_{candle.market}_{candle.symbol}"
        
        # Получаем список стрел для этой пары
        spikes = self._series_tracker[user_id].get(key, [])
        
        # Фильтруем только те, что попадают в временное окно (используем ts_ms для точности)
        # Важно: используем строгое неравенство (<), чтобы исключить текущую стрелу из подсчета
        # Текущая стрела будет добавлена в трекер ПОСЛЕ проверки условий
        filtered_spikes = [
            spike for spike in spikes 
            if spike.get("ts_ms", 0) >= window_start_ts_ms and spike.get("ts_ms", 0) < current_ts_ms
        ]
        
        # Если указаны условия, фильтруем только те стрелы, которые соответствуют **всем** условиям стратегии
        # Это гарантирует, что при проверке серии учитываются только стрелы, которые прошли те же фильтры,
        # что и текущая стрела (delta, volume, wick_pct, direction, symbol, exchange, market)
        if conditions:
            matching_spikes = []
            for spike in filtered_spikes:
                spike_delta = spike.get("delta", 0)
                spike_volume = spike.get("volume_usdt", 0)
                spike_wick_pct = spike.get("wick_pct", 0)
                spike_direction = spike.get("direction", "")
                spike_exchange = spike.get("exchange", "")
                spike_market = spike.get("market", "")
                spike_symbol = spike.get("symbol", "")
                
                # Проверяем все условия стратегии
                matches_all = True
                
                for condition in conditions:
                    cond_type = condition.get("type")
                    
                    if cond_type == "volume":
                        volume_value = condition.get("value")
                        if volume_value is not None and spike_volume < volume_value:
                            matches_all = False
                            break
                    
                    elif cond_type == "delta":
                        value_min = condition.get("valueMin")
                        value_max = condition.get("valueMax")
                        # Поддержка старого формата для обратной совместимости
                        if value_min is None:
                            value_min = condition.get("value")
                        if value_min is not None and spike_delta < value_min:
                            matches_all = False
                            break
                        if value_max is not None and spike_delta > value_max:
                            matches_all = False
                            break
                    
                    elif cond_type == "wick_pct":
                        value_min = condition.get("valueMin")
                        value_max = condition.get("valueMax")
                        if value_min is not None and spike_wick_pct < value_min:
                            matches_all = False
                            break
                        if value_max is not None and spike_wick_pct > value_max:
                            matches_all = False
                            break
                    
                    elif cond_type == "direction":
                        direction_value = condition.get("direction") or condition.get("value")
                        if direction_value and spike_direction != direction_value:
                            matches_all = False
                            break
                    
                    elif cond_type == "symbol":
                        symbol_value = condition.get("symbol") or condition.get("value")
                        if symbol_value and spike_symbol != symbol_value:
                            matches_all = False
                            break
                    
                    elif cond_type == "exchange":
                        exchange_value = condition.get("exchange") or condition.get("value")
                        if exchange_value and spike_exchange.lower() != exchange_value.lower():
                            matches_all = False
                            break
                    
                    elif cond_type == "market":
                        market_value = condition.get("market") or condition.get("value")
                        if market_value:
                            # Нормализация: "linear" -> "futures", "spot" -> "spot"
                            normalized_market = "futures" if market_value == "linear" else market_value
                            normalized_spike_market = "futures" if spike_market == "linear" else spike_market
                            if normalized_spike_market != normalized_market:
                                matches_all = False
                                break
                
                if matches_all:
                    matching_spikes.append(spike)
            
            filtered_spikes = matching_spikes
        
        return len(filtered_spikes)
    
    def _add_spike_to_series(self, user_id: int, candle: Candle, delta: float, volume_usdt: float, 
                             wick_pct: float = 0.0, detected_by_spike_settings: bool = False, 
                             detected_by_strategy: bool = False):
        """
        Добавляет стрелу в трекер серий с параметрами
        
        Уникальность: каждая стрела уникальна по {user_id}_{exchange}_{market}_{symbol}_{ts_ms}
        Одна и та же свеча может быть детектирована для разных пользователей независимо.
        
        Args:
            user_id: ID пользователя
            candle: Свеча со стрелой
            delta: Дельта в процентах
            volume_usdt: Объём в USDT
            wick_pct: Процент тени
            detected_by_spike_settings: Флаг детектирования через обычные настройки прострела
            detected_by_strategy: Флаг детектирования через стратегию
        """
        # Используем timestamp свечи в миллисекундах для уникальности
        ts_ms = candle.ts_ms
        current_time = time.time()
        key = f"{candle.exchange}_{candle.market}_{candle.symbol}"
        
        # Определяем направление стрелы
        direction = "up" if candle.close > candle.open else "down"
        
        # Проверяем уникальность: не добавляем дубликаты
        # Уникальность по {user_id}_{exchange}_{market}_{symbol}_{ts_ms}
        unique_key = f"{user_id}_{candle.exchange}_{candle.market}_{candle.symbol}_{ts_ms}"
        
        # Проверяем, нет ли уже такой стрелы в трекере
        spikes = self._series_tracker[user_id].get(key, [])
        for existing_spike in spikes:
            if (existing_spike.get("ts_ms") == ts_ms and 
                existing_spike.get("exchange") == candle.exchange and
                existing_spike.get("market") == candle.market and
                existing_spike.get("symbol") == candle.symbol):
                # Стрела уже есть в трекере - не добавляем дубликат
                logger.debug(f"Стрела уже существует в трекере: {unique_key}")
                return
        
        # Добавляем стрелу с полными параметрами
        spike_data = {
            "ts_ms": ts_ms,  # Timestamp свечи в миллисекундах (для уникальности)
            "timestamp": current_time,  # Timestamp добавления в трекер (для очистки)
            "delta": delta,
            "volume_usdt": volume_usdt,
            "wick_pct": wick_pct,
            "direction": direction,
            "exchange": candle.exchange,
            "market": candle.market,
            "symbol": candle.symbol,
            "detected_by_spike_settings": detected_by_spike_settings,
            "detected_by_strategy": detected_by_strategy
        }
        
        spikes.append(spike_data)
        
        # Сортируем по ts_ms для быстрого поиска (индексирование по времени)
        spikes.sort(key=lambda x: x.get("ts_ms", 0))
        
        # Получаем максимальный период времени из всех стратегий пользователя
        max_ttl_seconds = self._get_max_time_window_for_user(user_id)
        
        # Очищаем старые записи (TTL) для экономии памяти
        ttl_threshold_ts_ms = ts_ms - int(max_ttl_seconds * 1000)
        spikes = [spike for spike in spikes if spike.get("ts_ms", 0) >= ttl_threshold_ts_ms]
        
        # Ограничиваем максимальный размер (оставляем последние N записей)
        if len(spikes) > self._max_spikes_per_symbol:
            spikes = spikes[-self._max_spikes_per_symbol:]
        
        self._series_tracker[user_id][key] = spikes
    
    def _get_max_time_window_for_user(self, user_id: int) -> float:
        """
        Получает максимальный период времени из всех стратегий пользователя
        
        Если у пользователя есть стратегии с условием "series", возвращает максимальное значение timeWindowSeconds.
        Если стратегий нет или нет условия "series", возвращает значение по умолчанию (15 минут).
        
        Args:
            user_id: ID пользователя
            
        Returns:
            float: Максимальный период времени в секундах (по умолчанию 900 секунд = 15 минут)
        """
        try:
            users = self._get_users()
            user = next((u for u in users if u.get("id") == user_id), None)
            if not user:
                return self._default_ttl_seconds
            
            user_options = self._parse_user_options(user.get("options_json", "{}"))
            conditional_templates = user_options.get("conditionalTemplates", [])
            
            max_time_window = self._default_ttl_seconds  # По умолчанию 15 минут
            
            for strategy in conditional_templates:
                if not strategy.get("enabled", True):
                    continue
                
                conditions = strategy.get("conditions", [])
                for condition in conditions:
                    if condition.get("type") == "series":
                        time_window = condition.get("timeWindowSeconds")
                        if time_window is not None:
                            try:
                                time_window_float = float(time_window)
                                if time_window_float > max_time_window:
                                    max_time_window = time_window_float
                            except (ValueError, TypeError):
                                pass
            
            return max_time_window
        except Exception as e:
            logger.warning(f"Ошибка при получении максимального периода времени для пользователя {user_id}: {e}")
            return self._default_ttl_seconds
    
    def _extract_strategy_filters(self, strategy: Dict, user_options: Dict, candle: Candle) -> Optional[Dict]:
        """
        Извлекает базовые фильтры (delta, volume, wick_pct) из стратегии
        
        Логика:
        - Если useGlobalFilters = true → использует фильтры из exchangeSettings/pairSettings/thresholds
        - Если useGlobalFilters = false → извлекает фильтры из условий стратегии
        
        Args:
            strategy: Словарь стратегии с полями:
                - useGlobalFilters: bool (по умолчанию true)
                - conditions: List[Dict] - список условий
            user_options: Настройки пользователя (для получения глобальных фильтров)
            candle: Свеча (для определения биржи и рынка)
            
        Returns:
            Optional[Dict]: Словарь с фильтрами {"delta_min": float, "volume_min": float, "wick_pct_max": float}
                          или None если фильтры не найдены
        """
        use_global_filters = strategy.get("useGlobalFilters", True)  # По умолчанию true
        
        if use_global_filters:
            # Используем фильтры из глобальных настроек (exchangeSettings/pairSettings/thresholds)
            # Логика аналогична _check_thresholds, но возвращаем только значения фильтров
            exchange_key = candle.exchange.lower()
            market_key = "futures" if candle.market == "linear" else "spot"
            
            # Извлекаем котируемую валюту
            quote_currency = self._extract_quote_currency(candle.symbol, candle.exchange)
            
            # Проверяем pairSettings (приоритет 1)
            pair_settings = user_options.get("pairSettings", {})
            if quote_currency:
                pair_key = f"{exchange_key}_{market_key}_{quote_currency}"
                if pair_key in pair_settings:
                    pair_config = pair_settings[pair_key]
                    if pair_config.get("enabled", True):
                        try:
                            delta_str = pair_config.get("delta")
                            volume_str = pair_config.get("volume")
                            shadow_str = pair_config.get("shadow")
                            
                            if delta_str and volume_str and shadow_str:
                                delta_min = float(delta_str)
                                volume_min = float(volume_str)
                                wick_pct_max = float(shadow_str)
                                
                                if delta_min > 0 and volume_min > 0 and wick_pct_max > 0:
                                    return {
                                        "delta_min": delta_min,
                                        "volume_min": volume_min,
                                        "wick_pct_max": wick_pct_max
                                    }
                        except (ValueError, TypeError):
                            pass
            
            # Проверяем exchangeSettings (приоритет 2)
            exchange_settings = user_options.get("exchangeSettings", {})
            if exchange_key in exchange_settings:
                exchange_config = exchange_settings[exchange_key]
                market_config = exchange_config.get(market_key, {})
                
                if market_config.get("enabled", True):
                    try:
                        delta_str = market_config.get("delta")
                        volume_str = market_config.get("volume")
                        shadow_str = market_config.get("shadow")
                        
                        if delta_str and volume_str and shadow_str:
                            delta_min = float(delta_str)
                            volume_min = float(volume_str)
                            wick_pct_max = float(shadow_str)
                            
                            if delta_min > 0 and volume_min > 0 and wick_pct_max > 0:
                                return {
                                    "delta_min": delta_min,
                                    "volume_min": volume_min,
                                    "wick_pct_max": wick_pct_max
                                }
                    except (ValueError, TypeError):
                        pass
            
            # Проверяем thresholds (приоритет 3)
            thresholds = user_options.get("thresholds", {})
            if thresholds:
                try:
                    delta_min = thresholds.get("delta_pct")
                    volume_min = thresholds.get("volume_usdt")
                    wick_pct_max = thresholds.get("wick_pct")
                    
                    if delta_min is not None and volume_min is not None and wick_pct_max is not None:
                        delta_min = float(delta_min)
                        volume_min = float(volume_min)
                        wick_pct_max = float(wick_pct_max)
                        
                        if delta_min > 0 and volume_min > 0 and wick_pct_max > 0:
                            return {
                                "delta_min": delta_min,
                                "volume_min": volume_min,
                                "wick_pct_max": wick_pct_max
                            }
                except (ValueError, TypeError):
                    pass
            
            return None
        else:
            # Извлекаем фильтры из условий стратегии (используем общий метод)
            return self._extract_strategy_filters_from_conditions(strategy)
    
    def _extract_strategy_filters_from_conditions(self, strategy: Dict) -> Optional[Dict]:
        """
        Извлекает базовые фильтры (delta, volume, wick_pct) напрямую из условий стратегии
        
        Args:
            strategy: Словарь стратегии с полями:
                - conditions: List[Dict] - список условий
                
        Returns:
            Optional[Dict]: Словарь с фильтрами {"delta_min": float, "volume_min": float, "wick_pct_max": float}
                          или None если фильтры не найдены
        """
        conditions = strategy.get("conditions", [])
        
        delta_min = None
        volume_min = None
        wick_pct_max = None
        
        for condition in conditions:
            cond_type = condition.get("type")
            
            if cond_type == "delta":
                # Для дельты используем valueMin (valueMax может быть null для бесконечности)
                value_min = condition.get("valueMin")
                # Поддержка старого формата для обратной совместимости
                if value_min is None:
                    value_min = condition.get("value")
                if value_min is not None:
                    try:
                        delta_min = float(value_min)
                    except (ValueError, TypeError):
                        pass
            
            elif cond_type == "volume":
                # Для объёма используем value
                value = condition.get("value")
                if value is not None:
                    try:
                        volume_min = float(value)
                    except (ValueError, TypeError):
                        pass
            
            elif cond_type == "wick_pct":
                # Для тени используем valueMax (максимальное значение тени)
                # Если valueMax не указан, используем None (бесконечность)
                value_max = condition.get("valueMax")
                if value_max is not None:
                    try:
                        wick_pct_max = float(value_max)
                    except (ValueError, TypeError):
                        pass
                # Если valueMax не указан, wick_pct_max остается None (бесконечность)
        
        # Проверяем, что все базовые фильтры найдены (delta и volume обязательны, wick_pct_max может быть None)
        if delta_min is not None and volume_min is not None:
            return {
                "delta_min": delta_min,
                "volume_min": volume_min,
                "wick_pct_max": wick_pct_max  # Может быть None (бесконечность)
            }
        
        return None
    
    async def _check_strategy_conditions(self, strategy: Dict, candle: Candle, delta: float, 
                                        volume_usdt: float, wick_pct: float, user_id: int) -> bool:
        """
        Проверяет все условия стратегии
        
        Использует единый механизм проверки условий через telegram_notifier._check_condition(),
        чтобы новые условия автоматически поддерживались без изменения логики детектирования.
        
        Args:
            strategy: Словарь стратегии с полями:
                - enabled: bool (по умолчанию true)
                - useGlobalFilters: bool (по умолчанию true)
                - conditions: List[Dict] - список условий
            candle: Свеча для проверки
            delta: Дельта в процентах
            volume_usdt: Объём в USDT
            wick_pct: Процент тени
            user_id: ID пользователя (для проверки серий)
            
        Returns:
            bool: True если все условия стратегии выполнены
        """
        # Проверяем, включена ли стратегия
        enabled = strategy.get("enabled")
        if enabled is False:
            return False
        
        # Получаем условия стратегии
        conditions = strategy.get("conditions", [])
        if not conditions:
            return False
        
        # Проверяем базовые фильтры (delta, volume, wick_pct)
        # Если useGlobalFilters = true, базовые фильтры проверяются через глобальные настройки
        # Если useGlobalFilters = false, базовые фильтры должны быть в условиях стратегии
        use_global_filters = strategy.get("useGlobalFilters", True)
        
        if use_global_filters:
            # Базовые фильтры проверяются через глобальные настройки (не через условия стратегии)
            # Но мы всё равно проверяем все условия стратегии (series, symbol, exchange_market, direction)
            # Базовые фильтры (delta, volume, wick_pct) из условий стратегии игнорируются при useGlobalFilters = true
            pass
        else:
            # Базовые фильтры должны быть в условиях стратегии
            # Проверяем, что они есть
            has_delta = any(c.get("type") == "delta" for c in conditions)
            has_volume = any(c.get("type") == "volume" for c in conditions)
            has_wick_pct = any(c.get("type") == "wick_pct" for c in conditions)
            
            if not (has_delta and has_volume and has_wick_pct):
                # Базовые фильтры отсутствуют - стратегия невалидна
                logger.debug(f"Стратегия невалидна: отсутствуют базовые фильтры (useGlobalFilters=false)")
                return False
        
        # Проверяем все условия стратегии через единый механизм
        from core.telegram_notifier import TelegramNotifier
        
        for condition in conditions:
            # Если useGlobalFilters = true, пропускаем базовые фильтры из условий стратегии
            # (они проверяются через глобальные настройки)
            if use_global_filters:
                cond_type = condition.get("type")
                if cond_type in ("delta", "volume", "wick_pct"):
                    continue  # Пропускаем базовые фильтры, они проверяются через глобальные настройки
            
            # Проверяем условие через единый механизм
            condition_met = await TelegramNotifier._check_condition(
                condition, delta, volume_usdt, wick_pct, candle, user_id, conditions
            )
            
            if not condition_met:
                return False
        
        # Все условия выполнены
        return True
    
    async def _check_user_spike(self, user: Dict, candle: Candle) -> Optional[Dict]:
        """
        Проверяет детектирование стрелы для одного пользователя (обычные настройки + стратегии)
        
        Args:
            user: Словарь с данными пользователя
            candle: Свеча для анализа
            
        Returns:
            Optional[Dict]: Словарь с информацией о детектированной стреле или None
            Формат: {
                "user_id": int,
                "user_name": str,
                "delta": float,
                "wick_pct": float,
                "volume_usdt": float,
                "detected_by_spike_settings": bool,
                "detected_by_strategy": bool,
                "matched_strategies": List[Dict]  # Список стратегий, которые сработали
            }
        """
        try:
            # Парсим настройки пользователя
            user_options = self._parse_user_options(user.get("options_json", "{}"))
            user_name = user.get("user", "Unknown")
            user_id = user["id"]
            
            # Вычисляем метрики свечи один раз
            delta = self._calculate_delta(candle)
            wick_pct = self._calculate_wick_pct(candle)
            volume_usdt = self._calculate_volume_usdt(candle)
            
            # Флаги детектирования
            detected_by_spike_settings = False
            detected_by_strategy = False
            matched_strategies = []
            
            # Проверяем обычные настройки прострела
            # Проверяем, включена ли эта биржа для пользователя
            if self._check_exchange_filter(candle.exchange, user_options):
                # Проверяем, есть ли у пользователя хотя бы какие-то настройки фильтров
                exchange_settings = user_options.get("exchangeSettings", {})
                thresholds = user_options.get("thresholds", {})
                
                if exchange_settings or thresholds:
                    # Проверяем пороги
                    matches, metrics = self._check_thresholds(candle, user_options)
                    
                    if matches:
                        detected_by_spike_settings = True
                        logger.info(f"Стрела обнаружена через обычные настройки для пользователя {user_name}: {candle.exchange} {candle.market} {candle.symbol} - delta={metrics['delta']:.2f}%, volume={metrics['volume_usdt']:.2f}, wick_pct={metrics['wick_pct']:.2f}%")
            
            # Проверяем стратегии независимо от обычных настроек
            conditional_templates = user_options.get("conditionalTemplates", [])
            if conditional_templates:
                for strategy in conditional_templates:
                    try:
                        # Проверяем, включена ли стратегия
                        if strategy.get("enabled", True) is False:
                            continue
                        
                        # Получаем базовые фильтры из стратегии
                        use_global_filters = strategy.get("useGlobalFilters", True)
                        strategy_filters = self._extract_strategy_filters(strategy, user_options, candle)
                        
                        # Логика проверки базовых фильтров:
                        # 1. Если useGlobalFilters = false → используем базовые фильтры из условий стратегии (обязательно)
                        # 2. Если useGlobalFilters = true и есть глобальные настройки → используем их
                        # 3. Если useGlobalFilters = true и нет глобальных настроек → используем базовые фильтры из условий стратегии (если есть)
                        
                        if not use_global_filters:
                            # Если useGlobalFilters = false, проверяем базовые фильтры из условий стратегии
                            if strategy_filters is None:
                                # Пытаемся извлечь фильтры из условий стратегии напрямую
                                strategy_filters = self._extract_strategy_filters_from_conditions(strategy)
                            
                            if strategy_filters is None:
                                logger.debug(f"Стратегия '{strategy.get('name', 'Unknown')}' невалидна: отсутствуют базовые фильтры (useGlobalFilters=false)")
                                continue
                            
                            # Проверяем базовые фильтры из условий стратегии
                            if delta <= strategy_filters.get("delta_min", 0):
                                continue
                            if volume_usdt <= strategy_filters.get("volume_min", 0):
                                continue
                            wick_pct_max = strategy_filters.get("wick_pct_max")
                            if wick_pct_max is not None and wick_pct <= wick_pct_max:
                                continue
                        else:
                            # Если useGlobalFilters = true, сначала пытаемся использовать глобальные настройки
                            if strategy_filters is None:
                                # Если глобальных настроек нет, пытаемся использовать базовые фильтры из условий стратегии
                                strategy_filters = self._extract_strategy_filters_from_conditions(strategy)
                            
                            if strategy_filters is None:
                                # Нет ни глобальных настроек, ни базовых фильтров в условиях стратегии - пропускаем стратегию
                                logger.debug(f"Стратегия '{strategy.get('name', 'Unknown')}' невалидна: отсутствуют базовые фильтры (useGlobalFilters=true, но нет глобальных настроек и нет фильтров в условиях)")
                                continue
                            
                            # Проверяем базовые фильтры (из глобальных настроек или из условий стратегии)
                            if delta <= strategy_filters.get("delta_min", 0):
                                continue
                            if volume_usdt <= strategy_filters.get("volume_min", 0):
                                continue
                            wick_pct_max = strategy_filters.get("wick_pct_max")
                            if wick_pct_max is not None and wick_pct <= wick_pct_max:
                                continue
                        
                        # Проверяем условие exchange в стратегии (для автоматического включения биржи)
                        matches_exchange_condition, has_exchange_condition = self._check_strategy_exchange_condition(strategy, candle)
                        
                        # Если в стратегии указана конкретная биржа, но текущая свеча не соответствует - пропускаем стратегию
                        if has_exchange_condition and not matches_exchange_condition:
                            continue
                        
                        # Если биржа не указана в стратегии - используем только включенные биржи
                        # Если биржа указана в стратегии, но отключена в exchanges - временно игнорируем проверку _check_exchange_filter()
                        # только для этой стратегии (автоматическое включение биржи для стратегии)
                        if not has_exchange_condition:
                            # Если биржа не указана в стратегии, проверяем, включена ли она в exchanges
                            if not self._check_exchange_filter(candle.exchange, user_options):
                                continue
                        # Если биржа указана в стратегии, но отключена в exchanges - пропускаем проверку _check_exchange_filter()
                        # Это позволяет стратегии работать для указанной биржи, даже если она отключена в глобальных настройках
                        # Глобальные фильтры (exchangeSettings/pairSettings/thresholds) остаются отключенными для этой биржи
                        # и проверяются отдельно через _extract_strategy_filters() и _check_strategy_conditions()
                        
                        # Проверяем все условия стратегии (включая дополнительные: series, symbol, exchange, market, direction)
                        strategy_passed = await self._check_strategy_conditions(
                            strategy, candle, delta, volume_usdt, wick_pct, user_id
                        )
                        
                        if strategy_passed:
                            detected_by_strategy = True
                            matched_strategies.append({
                                "name": strategy.get("name", "Unknown"),
                                "template": strategy.get("template", ""),
                                "chatId": strategy.get("chatId")
                            })
                            logger.info(f"Стрела обнаружена через стратегию '{strategy.get('name', 'Unknown')}' для пользователя {user_name}: {candle.exchange} {candle.market} {candle.symbol}")
                    except Exception as e:
                        logger.warning(f"Ошибка при проверке стратегии для пользователя {user_name}: {e}", exc_info=True, extra={
                            "log_to_db": True,
                            "error_type": "strategy_check_error",
                            "exchange": candle.exchange,
                            "market": candle.market,
                            "symbol": candle.symbol,
                        })
                        continue
            
            # Если стрела детектирована хотя бы одним способом
            if detected_by_spike_settings or detected_by_strategy:
                # Добавляем стрелу в трекер серий с параметрами
                # Уникальность гарантируется внутри метода _add_spike_to_series
                self._add_spike_to_series(
                    user_id, candle, delta, volume_usdt, wick_pct,
                    detected_by_spike_settings, detected_by_strategy
                )
                
                return {
                    "user_id": user_id,
                    "user_name": user_name,
                    "delta": delta,
                    "wick_pct": wick_pct,
                    "volume_usdt": volume_usdt,
                    "detected_by_spike_settings": detected_by_spike_settings,
                    "detected_by_strategy": detected_by_strategy,
                    "matched_strategies": matched_strategies
                }
            
            return None
            
        except Exception as e:
            # Обрабатываем ошибки для каждого пользователя отдельно
            try:
                user_name = user.get("user", "Unknown")
            except:
                user_name = "Unknown"
            logger.error(f"Ошибка при обработке пользователя {user_name} для свечи {candle.exchange} {candle.market} {candle.symbol}: {e}", exc_info=True, extra={
                "log_to_db": True,
                "error_type": "spike_detection_user_error",
                "exchange": candle.exchange,
                "market": candle.market,
                "symbol": candle.symbol,
            })
            return None
    
    async def detect_spike(self, candle: Candle) -> List[Dict]:
        """
        Детектирует стрелу для всех пользователей параллельно (обычные настройки + стратегии)
        
        Args:
            candle: Свеча для анализа
            
        Returns:
            List[Dict]: Список детектированных стрел с информацией о пользователях
            Формат: [{
                "user_id": int,
                "user_name": str,
                "delta": float,
                "wick_pct": float,
                "volume_usdt": float,
                "detected_by_spike_settings": bool,
                "detected_by_strategy": bool,
                "matched_strategies": List[Dict]
            }, ...]
        """
        # Периодическая очистка старых данных
        self._cleanup_old_data()
        
        # Получаем всех пользователей
        users = self._get_users()
        
        if not users:
            return []
        
        # Параллельная обработка всех пользователей через asyncio.gather()
        import asyncio
        tasks = [self._check_user_spike(user, candle) for user in users]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Фильтруем результаты: оставляем только успешные детекты (не None и не Exception)
        detected_spikes = []
        for result in results:
            if result is not None and not isinstance(result, Exception):
                detected_spikes.append(result)
            elif isinstance(result, Exception):
                # Логируем исключения, которые не были обработаны в _check_user_spike
                logger.error(f"Необработанное исключение при детектировании стрелы: {result}", exc_info=result, extra={
                    "log_to_db": True,
                    "error_type": "spike_detection_unhandled_error",
                    "exchange": candle.exchange,
                    "market": candle.market,
                    "symbol": candle.symbol,
                })
        
        return detected_spikes
    
    def get_series_count(self, user_id: int, candle: Candle, time_window_seconds: float,
                         conditions: Optional[List[Dict]] = None) -> int:
        """
        Получает количество стрел за указанное время для данной пары (публичный метод)
        с учетом всех условий стратегии (delta, volume, wick_pct, direction, symbol, exchange, market)
        
        Args:
            user_id: ID пользователя
            candle: Свеча (используется для определения временного окна)
            time_window_seconds: Временное окно в секундах (смотрим назад от момента текущей стрелы)
            conditions: Список условий для проверки (опционально). Если указан, 
                       считаются только стрелы, соответствующие **всем** условиям стратегии
            
        Returns:
            int: Количество стрел за указанное время (соответствующих условиям, если они указаны)
        """
        return self._get_series_count(user_id, candle, time_window_seconds, conditions)
    
    def invalidate_cache(self):
        """Сбрасывает кэш пользователей"""
        self._users_cache = None
        self._cache_timestamp = 0.0
    
    def _cleanup_old_data(self):
        """
        Периодическая очистка старых данных:
        - Удаляет записи старше максимального периода времени из всех стратегий пользователя
        - Удаляет данные для несуществующих пользователей
        - Использует динамический TTL для каждого пользователя на основе его стратегий
        """
        current_time = time.time()
        
        # Периодическая очистка: раз в 5 минут (более частая очистка для экономии памяти)
        if current_time - self._last_cleanup_time < self._cleanup_interval:
            return
        
        self._last_cleanup_time = current_time
        
        # Получаем список существующих пользователей
        try:
            users = self._get_users()
            existing_user_ids = {user["id"] for user in users}
        except Exception as e:
            logger.warning(f"Ошибка при получении пользователей для очистки трекера: {e}")
            existing_user_ids = set()
        
        # Очищаем данные для несуществующих пользователей
        user_ids_to_remove = []
        for user_id in self._series_tracker.keys():
            if user_id not in existing_user_ids:
                user_ids_to_remove.append(user_id)
        
        for user_id in user_ids_to_remove:
            del self._series_tracker[user_id]
            logger.debug(f"Удалены данные трекера для несуществующего пользователя ID={user_id}")
        
        # Очищаем старые записи (TTL) и ограничиваем размер для существующих пользователей
        # Используем динамический TTL для каждого пользователя
        current_ts_ms = int(current_time * 1000)
        
        for user_id in list(self._series_tracker.keys()):
            # Получаем максимальный период времени для этого пользователя
            max_ttl_seconds = self._get_max_time_window_for_user(user_id)
            ttl_threshold_ts_ms = current_ts_ms - int(max_ttl_seconds * 1000)
            
            for key in list(self._series_tracker[user_id].keys()):
                spikes = self._series_tracker[user_id][key]
                # Фильтруем по TTL (используем ts_ms для точности)
                spikes = [spike for spike in spikes if spike.get("ts_ms", 0) >= ttl_threshold_ts_ms]
                # Ограничиваем размер
                if len(spikes) > self._max_spikes_per_symbol:
                    spikes = spikes[-self._max_spikes_per_symbol:]
                
                # Сортируем по ts_ms для быстрого поиска
                spikes.sort(key=lambda x: x.get("ts_ms", 0))
                
                if spikes:
                    self._series_tracker[user_id][key] = spikes
                else:
                    # Удаляем пустые ключи
                    del self._series_tracker[user_id][key]
            
            # Удаляем пустые записи пользователей
            if not self._series_tracker[user_id]:
                del self._series_tracker[user_id]
    
    def cleanup_user_data(self, user_id: int):
        """
        Очищает данные трекера для указанного пользователя.
        Вызывается при удалении пользователя.
        
        Args:
            user_id: ID пользователя для очистки
        """
        if user_id in self._series_tracker:
            del self._series_tracker[user_id]
            logger.debug(f"Очищены данные трекера для пользователя ID={user_id}")


# Глобальный экземпляр детектора
spike_detector = SpikeDetector()

