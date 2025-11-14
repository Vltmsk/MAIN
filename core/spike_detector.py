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
            users = db.get_all_users()
            self._users_cache = users
            self._cache_timestamp = current_time
            return users
        except Exception as e:
            logger.error(f"Ошибка при получении пользователей: {e}", exc_info=True)
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
            
            return {
                "thresholds": thresholds,  # Используем только пользовательские настройки, без дефолтов
                "exchanges": {
                    "gate": bool(exchanges.get("gate", default["exchanges"]["gate"])),
                    "binance": bool(exchanges.get("binance", default["exchanges"]["binance"])),
                    "bitget": bool(exchanges.get("bitget", default["exchanges"]["bitget"])),
                    "bybit": bool(exchanges.get("bybit", default["exchanges"]["bybit"])),
                },
                "exchangeSettings": exchange_settings
            }
        except Exception as e:
            logger.warning(f"Ошибка парсинга options_json: {e}, настройки не применятся")
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
            "exchangeSettings": {}
        }
    
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
        
        # Пытаемся получить настройки из exchangeSettings для конкретной биржи и рынка
        exchange_settings = user_options.get("exchangeSettings", {})
        exchange_key = candle.exchange.lower()
        market_key = "futures" if candle.market == "linear" else "spot"
        
        # Используем настройки из exchangeSettings, если они есть
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
                
                logger.debug(f"Проверка фильтров для {exchange_key} {market_key}: delta_min={delta_min}, volume_min={volume_min}, wick_pct_max={wick_pct_max}")
                logger.debug(f"Фактические значения: delta={delta:.2f}, volume={volume_usdt:.2f}, wick_pct={wick_pct:.2f}")
            except (ValueError, TypeError) as e:
                logger.warning(f"Ошибка парсинга настроек биржи {exchange_key} {market_key}: {e}")
                return False, {"delta": delta, "wick_pct": wick_pct, "volume_usdt": volume_usdt}
        else:
            # Если нет настроек в exchangeSettings, проверяем глобальные thresholds
            thresholds = user_options.get("thresholds", {})
            
            # Если нет настроек вообще - не пропускаем детект
            if not thresholds:
                return False, {"delta": delta, "wick_pct": wick_pct, "volume_usdt": volume_usdt}
            
            # Используем глобальные пороги (БЕЗ дефолтных значений)
            delta_min = thresholds.get("delta_pct")
            volume_min = thresholds.get("volume_usdt")
            wick_pct_max = thresholds.get("wick_pct")
            
            # Если хотя бы одно значение отсутствует - не пропускаем детект
            if delta_min is None or volume_min is None or wick_pct_max is None:
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
        
        # Дельта должна быть СТРОГО больше установленной пользователем
        if delta <= delta_min:
            logger.debug(f"Дельта {delta:.2f}% <= {delta_min}% - фильтр не пройден (нужно строго больше)")
            return False, {"delta": delta, "wick_pct": wick_pct, "volume_usdt": volume_usdt}
        
        # Объём должен быть СТРОГО больше установленного пользователем
        if volume_usdt <= volume_min:
            logger.debug(f"Объём {volume_usdt:.2f} <= {volume_min} - фильтр не пройден (нужно строго больше)")
            return False, {"delta": delta, "wick_pct": wick_pct, "volume_usdt": volume_usdt}
        
        # Тень должна быть СТРОГО больше установленной пользователем
        if wick_pct <= wick_pct_max:
            logger.debug(f"Тень {wick_pct:.2f}% <= {wick_pct_max}% - фильтр не пройден (нужно строго больше)")
            return False, {"delta": delta, "wick_pct": wick_pct, "volume_usdt": volume_usdt}
        
        # Все проверки пройдены
        logger.debug(f"Все фильтры пройдены для {exchange_key} {market_key}: delta={delta:.2f}% > {delta_min}%, volume={volume_usdt:.2f} > {volume_min}, wick_pct={wick_pct:.2f}% > {wick_pct_max}%")
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
        
        # Очищаем старые записи (старше 1 часа) для экономии памяти
        hour_ago = current_time - 3600
        self._series_tracker[user_id][key] = [
            spike for spike in self._series_tracker[user_id][key] 
            if spike.get("timestamp", 0) >= hour_ago
        ]
    
    def detect_spike(self, candle: Candle) -> List[Dict]:
        """
        Детектирует стрелу для всех пользователей, чьи фильтры соответствуют свече
        
        Args:
            candle: Свеча для анализа
            
        Returns:
            List[Dict]: Список детектированных стрел с информацией о пользователях
            Формат: [{"user_id": int, "user_name": str, "delta": float, "wick_pct": float, "volume_usdt": float}, ...]
        """
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


# Глобальный экземпляр детектора
spike_detector = SpikeDetector()

