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
        
        # Трекер серий стрел: {user_id: {exchange_market_symbol: [{"timestamp": float, "delta": float, "volume_usdt": float}]}}
        # Хранит временные метки и параметры последних стрел для каждой пары exchange+market+symbol для каждого пользователя
        self._series_tracker: Dict[int, Dict[str, List[Dict]]] = defaultdict(lambda: defaultdict(list))
        
        # Настройки для управления памятью
        self._max_spikes_per_symbol = 1000  # Максимальное количество записей на символ
        self._ttl_seconds = 3600  # TTL: 1 час
        self._last_cleanup_time = time.time()  # Время последней очистки
        self._cleanup_interval = 3600  # Интервал периодической очистки: 1 час
    
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
            
            return {
                "thresholds": thresholds,  # Используем только пользовательские настройки, без дефолтов
                "exchanges": {
                    "gate": bool(exchanges.get("gate", default["exchanges"]["gate"])),
                    "binance": bool(exchanges.get("binance", default["exchanges"]["binance"])),
                    "bitget": bool(exchanges.get("bitget", default["exchanges"]["bitget"])),
                    "bybit": bool(exchanges.get("bybit", default["exchanges"]["bybit"])),
                },
                "exchangeSettings": exchange_settings,
                "pairSettings": pair_settings
            }
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            logger.warning(f"Ошибка парсинга options_json: {e}, настройки не применятся", extra={
                "log_to_db": True,
                "error_type": "spike_detector_parse_error",
                "market": "spike_detector",
            })
            return self._get_default_options()
    
    def _get_default_options(self) -> Dict:
        """Возвращает дефолтные настройки фильтров (только для включения/выключения бирж)"""
        return {
            "thresholds": {},  # Нет дефолтных порогов - используются только пользовательские настройки
            "exchanges": {
                "gate": True,
                "binance": True,
                "bitget": True,
                "bybit": True,
            },
            "exchangeSettings": {},
            "pairSettings": {}
        }
    
    def _extract_quote_currency(self, symbol: str, exchange: str) -> Optional[str]:
        """
        Извлекает котируемую валюту из символа
        
        Args:
            symbol: Символ торговой пары (например, "BTCUSDT", "ETH_TRY", "LTC-TRY")
            exchange: Название биржи (binance, gate, bitget, bybit)
            
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
        Вычисляет изменение цены в процентах
        
        Args:
            candle: Свеча
            
        Returns:
            float: Дельта в процентах
        """
        if candle.open == 0:
            return 0.0
        
        delta = ((candle.close - candle.open) / candle.open) * 100
        return abs(delta)  # Берём абсолютное значение
    
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
        }
        
        exchange_key = exchange_map.get(exchange.lower(), exchange.lower())
        return exchanges.get(exchange_key, True)  # По умолчанию включено
    
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
        # Если есть хотя бы одна дополнительная пара с настройками - глобальные настройки не применяются
        if pair_settings:
            # Проверяем, есть ли дополнительные пары для этого exchange и market
            has_additional_pairs = False
            for key in pair_settings.keys():
                # Ключ формата: {exchange}_{market}_{pair}
                if key.startswith(f"{exchange_key}_{market_key}_"):
                    has_additional_pairs = True
                    break
            
            # Если есть дополнительные пары, но для текущей пары нет настроек - не применяем детектирование
            if has_additional_pairs:
                logger.debug(f"Для рынка {exchange_key} {market_key} есть дополнительные пары, но для текущей пары ({quote_currency or 'unknown'}) нет индивидуальных настроек - детектирование не применяется")
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

        if delta_min <= 0 or volume_min <= 0:
            logger.debug(
                f"Игнорируем глобальные пороги: delta={delta_min}, volume={volume_min} (не заданы пользователем)"
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
        с учетом условий volume и delta (если указаны)
        
        Args:
            user_id: ID пользователя
            candle: Текущая свеча
            time_window_seconds: Временное окно в секундах
            conditions: Список условий для проверки (опционально). Если указан, 
                       считаются только стрелы, соответствующие всем условиям volume и delta
            
        Returns:
            int: Количество стрел за указанное время (соответствующих условиям, если они указаны)
        """
        current_time = time.time()
        key = f"{candle.exchange}_{candle.market}_{candle.symbol}"
        
        # Получаем список стрел для этой пары
        spikes = self._series_tracker[user_id][key]
        
        # Фильтруем только те, что попадают в временное окно
        window_start = current_time - time_window_seconds
        filtered_spikes = [spike for spike in spikes if spike.get("timestamp", 0) >= window_start]
        
        # Если указаны условия, фильтруем только те стрелы, которые им соответствуют
        if conditions:
            # Извлекаем условия volume и delta из списка условий
            volume_condition = None
            delta_condition = None
            
            for condition in conditions:
                cond_type = condition.get("type")
                if cond_type == "volume":
                    volume_condition = condition
                elif cond_type == "delta":
                    delta_condition = condition
            
            # Фильтруем стрелы по условиям
            matching_spikes = []
            for spike in filtered_spikes:
                spike_delta = spike.get("delta", 0)
                spike_volume = spike.get("volume_usdt", 0)
                
                # Проверяем условие volume (если указано)
                if volume_condition:
                    volume_value = volume_condition.get("value")
                    if volume_value is not None and spike_volume < volume_value:
                        continue  # Стрела не соответствует условию volume
                
                # Проверяем условие delta (если указано)
                if delta_condition:
                    delta_value = delta_condition.get("value")
                    if delta_value is not None and spike_delta < delta_value:
                        continue  # Стрела не соответствует условию delta
                
                # Стрела соответствует всем условиям
                matching_spikes.append(spike)
            
            filtered_spikes = matching_spikes
        
        # Обновляем трекер (оставляем только стрелы в окне)
        self._series_tracker[user_id][key] = filtered_spikes
        
        return len(filtered_spikes)
    
    def _add_spike_to_series(self, user_id: int, candle: Candle, delta: float, volume_usdt: float):
        """
        Добавляет стрелу в трекер серий с параметрами
        
        Args:
            user_id: ID пользователя
            candle: Свеча со стрелой
            delta: Дельта в процентах
            volume_usdt: Объём в USDT
        """
        current_time = time.time()
        key = f"{candle.exchange}_{candle.market}_{candle.symbol}"
        
        # Добавляем стрелу с параметрами
        spike_data = {
            "timestamp": current_time,
            "delta": delta,
            "volume_usdt": volume_usdt
        }
        self._series_tracker[user_id][key].append(spike_data)
        
        # Очищаем старые записи (TTL) для экономии памяти
        ttl_threshold = current_time - self._ttl_seconds
        spikes = self._series_tracker[user_id][key]
        spikes = [spike for spike in spikes if spike.get("timestamp", 0) >= ttl_threshold]
        
        # Ограничиваем максимальный размер (оставляем последние N записей)
        if len(spikes) > self._max_spikes_per_symbol:
            spikes = spikes[-self._max_spikes_per_symbol:]
        
        self._series_tracker[user_id][key] = spikes
    
    def detect_spike(self, candle: Candle) -> List[Dict]:
        """
        Детектирует стрелу для всех пользователей, чьи фильтры соответствуют свече
        
        Args:
            candle: Свеча для анализа
            
        Returns:
            List[Dict]: Список детектированных стрел с информацией о пользователях
            Формат: [{"user_id": int, "user_name": str, "delta": float, "wick_pct": float, "volume_usdt": float}, ...]
        """
        # Периодическая очистка старых данных
        self._cleanup_old_data()
        
        detected_spikes = []
        
        # Получаем всех пользователей
        users = self._get_users()
        
        for user in users:
            # Пропускаем пользователей без настроек Telegram (опционально, можно убрать)
            # if not user.get("tg_token") or not user.get("chat_id"):
            #     continue
            
            # Парсим настройки пользователя
            user_options = self._parse_user_options(user.get("options_json", "{}"))
            user_name = user.get("user", "Unknown")
            user_id = user["id"]
            
            # Проверяем, включена ли эта биржа для пользователя
            if not self._check_exchange_filter(candle.exchange, user_options):
                logger.debug(f"Биржа {candle.exchange} отключена для пользователя {user_name}")
                continue
            
            # Проверяем, есть ли у пользователя хотя бы какие-то настройки фильтров
            # Если нет ни exchangeSettings, ни thresholds - пропускаем пользователя
            exchange_settings = user_options.get("exchangeSettings", {})
            thresholds = user_options.get("thresholds", {})
            
            if not exchange_settings and not thresholds:
                logger.debug(f"У пользователя {user_name} нет настроек фильтров - пропускаем")
                continue
            
            # Проверяем пороги
            matches, metrics = self._check_thresholds(candle, user_options)
            
            if matches:
                logger.info(f"Стрела обнаружена для пользователя {user_name}: {candle.exchange} {candle.market} {candle.symbol} - delta={metrics['delta']:.2f}%, volume={metrics['volume_usdt']:.2f}, wick_pct={metrics['wick_pct']:.2f}%")
                
                # Добавляем стрелу в трекер серий с параметрами
                self._add_spike_to_series(user_id, candle, metrics["delta"], metrics["volume_usdt"])
                
                detected_spikes.append({
                    "user_id": user_id,
                    "user_name": user["user"],
                    "delta": metrics["delta"],
                    "wick_pct": metrics["wick_pct"],
                    "volume_usdt": metrics["volume_usdt"],
                })
            else:
                logger.debug(f"Стрела НЕ прошла фильтры для пользователя {user_name}: {candle.exchange} {candle.market} {candle.symbol} - delta={metrics['delta']:.2f}%, volume={metrics['volume_usdt']:.2f}, wick_pct={metrics['wick_pct']:.2f}%")
        
        return detected_spikes
    
    def get_series_count(self, user_id: int, candle: Candle, time_window_seconds: float,
                         conditions: Optional[List[Dict]] = None) -> int:
        """
        Получает количество стрел за указанное время для данной пары (публичный метод)
        с учетом условий volume и delta (если указаны)
        
        Args:
            user_id: ID пользователя
            candle: Свеча
            time_window_seconds: Временное окно в секундах
            conditions: Список условий для проверки (опционально). Если указан, 
                       считаются только стрелы, соответствующие всем условиям volume и delta
            
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
        - Удаляет записи старше TTL
        - Удаляет данные для несуществующих пользователей
        """
        current_time = time.time()
        
        # Периодическая очистка: раз в час
        if current_time - self._last_cleanup_time < self._cleanup_interval:
            return
        
        self._last_cleanup_time = current_time
        ttl_threshold = current_time - self._ttl_seconds
        
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
        for user_id in list(self._series_tracker.keys()):
            for key in list(self._series_tracker[user_id].keys()):
                spikes = self._series_tracker[user_id][key]
                # Фильтруем по TTL
                spikes = [spike for spike in spikes if spike.get("timestamp", 0) >= ttl_threshold]
                # Ограничиваем размер
                if len(spikes) > self._max_spikes_per_symbol:
                    spikes = spikes[-self._max_spikes_per_symbol:]
                
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

