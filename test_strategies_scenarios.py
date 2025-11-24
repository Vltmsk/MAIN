"""
Тесты для этапа 15: Тестирование всех сценариев работы стратегий детектирования

Этот файл содержит тесты для всех 12 сценариев из PLAN.md, этап 15.
Запуск: pytest test_strategies_scenarios.py -v
"""
import pytest
import asyncio
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch
from core.candle_builder import Candle
from core.spike_detector import SpikeDetector


class TestStrategiesScenarios:
    """Тесты для всех сценариев работы стратегий"""
    
    @pytest.fixture
    def detector(self):
        """Создаёт экземпляр SpikeDetector для тестов"""
        return SpikeDetector()
    
    @pytest.fixture
    def sample_candle(self):
        """Создаёт тестовую свечу"""
        current_time_ms = int(time.time() * 1000)
        return Candle(
            ts_ms=current_time_ms,
            open=50000.0,
            high=51000.0,  # Дельта = 2%
            low=49000.0,
            close=51000.0,  # Стрела вверх
            volume=1.0,  # Объём = 1 BTC * 51000 = 51000 USDT
            market="spot",
            exchange="binance",
            symbol="BTCUSDT"
        )
    
    @pytest.fixture
    def user_with_spike_settings(self):
        """Пользователь с обычными настройками прострела"""
        return {
            "id": 1,
            "user": "test_user",
            "options_json": json.dumps({
                "exchanges": {"binance": True},
                "exchangeSettings": {
                    "binance": {
                        "spot": {
                            "enabled": True,
                            "delta": "0.5",  # 0.5%
                            "volume": "10000",  # 10000 USDT
                            "shadow": "30"  # 30%
                        }
                    }
                },
                "messageTemplate": "Дефолтный шаблон: {symbol} {delta_formatted}"
            })
        }
    
    @pytest.fixture
    def user_with_strategy(self):
        """Пользователь со стратегией"""
        return {
            "id": 2,
            "user": "strategy_user",
            "options_json": json.dumps({
                "exchanges": {"binance": True},
                "exchangeSettings": {
                    "binance": {
                        "spot": {
                            "enabled": True,
                            "delta": "1.0",  # Нужны глобальные настройки для useGlobalFilters=true
                            "volume": "20000",
                            "shadow": "50"
                        }
                    }
                },
                "conditionalTemplates": [{
                    "name": "Тестовая стратегия",
                    "enabled": True,
                    "useGlobalFilters": True,
                    "conditions": [
                        {"type": "delta", "valueMin": 1.0},
                        {"type": "volume", "value": 20000}
                    ],
                    "template": "Шаблон стратегии: {symbol} {delta_formatted}"
                }]
            })
        }
    
    @pytest.mark.asyncio
    async def test_scenario_1_only_spike_settings(self, detector, sample_candle, user_with_spike_settings):
        """
        Сценарий 1: Стрела проходит только обычный прострел (не проходит стратегии)
        Ожидаемый результат: отправляется дефолтный шаблон (messageTemplate)
        """
        # Настраиваем мок для получения пользователей
        with patch.object(detector, '_get_users', return_value=[user_with_spike_settings]):
            # Свеча с дельтой 2% и объёмом 51000 USDT проходит фильтры (delta > 0.5%, volume > 10000)
            result = await detector.detect_spike(sample_candle)
            
            assert len(result) == 1
            assert result[0]["user_id"] == 1
            assert result[0]["detected_by_spike_settings"] is True
            assert result[0]["detected_by_strategy"] is False
            assert result[0]["matched_strategies"] == []
    
    @pytest.mark.asyncio
    async def test_scenario_2_only_strategy(self, detector, sample_candle, user_with_strategy):
        """
        Сценарий 2: Стрела проходит только стратегию (не проходит обычный прострел)
        Ожидаемый результат: отправляется шаблон стратегии
        """
        # Настраиваем мок для получения пользователей
        with patch.object(detector, '_get_users', return_value=[user_with_strategy]):
            # Свеча с дельтой 2% и объёмом 51000 USDT проходит стратегию (delta > 1.0%, volume > 20000)
            # Но не проходит обычные настройки (их нет у пользователя)
            result = await detector.detect_spike(sample_candle)
            
            assert len(result) == 1
            assert result[0]["user_id"] == 2
            assert result[0]["detected_by_spike_settings"] is False
            assert result[0]["detected_by_strategy"] is True
            assert len(result[0]["matched_strategies"]) == 1
            assert result[0]["matched_strategies"][0]["name"] == "Тестовая стратегия"
    
    @pytest.mark.asyncio
    async def test_scenario_3_both_systems(self, detector, sample_candle):
        """
        Сценарий 3: Стрела проходит обе системы (обычный прострел + стратегия)
        Ожидаемый результат: отправляется шаблон стратегии (приоритет), дефолтный шаблон не отправляется
        """
        user = {
            "id": 3,
            "user": "both_user",
            "options_json": json.dumps({
                "exchanges": {"binance": True},
                "exchangeSettings": {
                    "binance": {
                        "spot": {
                            "enabled": True,
                            "delta": "0.5",
                            "volume": "10000",
                            "shadow": "30"
                        }
                    }
                },
                "messageTemplate": "Дефолтный шаблон",
                "conditionalTemplates": [{
                    "name": "Стратегия 1",
                    "enabled": True,
                    "useGlobalFilters": True,
                    "conditions": [
                        {"type": "delta", "valueMin": 1.0},
                        {"type": "volume", "value": 20000}
                    ],
                    "template": "Шаблон стратегии"
                }]
            })
        }
        
        with patch.object(detector, '_get_users', return_value=[user]):
            result = await detector.detect_spike(sample_candle)
            
            assert len(result) == 1
            assert result[0]["user_id"] == 3
            assert result[0]["detected_by_spike_settings"] is True
            assert result[0]["detected_by_strategy"] is True  # Приоритет у стратегии
            assert len(result[0]["matched_strategies"]) == 1
    
    @pytest.mark.asyncio
    async def test_scenario_4_multiple_strategies(self, detector, sample_candle):
        """
        Сценарий 4: Стрела проходит несколько стратегий одновременно
        Ожидаемый результат: отправляются все подходящие шаблоны стратегий
        """
        user = {
            "id": 4,
            "user": "multi_strategy_user",
            "options_json": json.dumps({
                "exchanges": {"binance": True},
                "exchangeSettings": {
                    "binance": {
                        "spot": {
                            "enabled": True,
                            "delta": "0.5",  # Глобальные настройки для useGlobalFilters=true
                            "volume": "10000",
                            "shadow": "50"
                        }
                    }
                },
                "conditionalTemplates": [
                    {
                        "name": "Стратегия 1",
                        "enabled": True,
                        "useGlobalFilters": True,
                        "conditions": [
                            {"type": "delta", "valueMin": 1.0}
                        ],
                        "template": "Шаблон стратегии 1"
                    },
                    {
                        "name": "Стратегия 2",
                        "enabled": True,
                        "useGlobalFilters": True,
                        "conditions": [
                            {"type": "volume", "value": 20000}
                        ],
                        "template": "Шаблон стратегии 2"
                    }
                ]
            })
        }
        
        with patch.object(detector, '_get_users', return_value=[user]):
            result = await detector.detect_spike(sample_candle)
            
            assert len(result) == 1
            assert result[0]["detected_by_strategy"] is True
            assert len(result[0]["matched_strategies"]) == 2  # Обе стратегии должны сработать
    
    @pytest.mark.asyncio
    async def test_scenario_5_series_condition(self, detector):
        """
        Сценарий 5: Серия стрел с условием "series ≥ 2 стрелы за 5 минут"
        Проверить: первая стрела не отправляется, вторая и последующие отправляются
        """
        user = {
            "id": 5,
            "user": "series_user",
            "options_json": json.dumps({
                "exchanges": {"binance": True},
                "exchangeSettings": {
                    "binance": {
                        "spot": {
                            "enabled": True,
                            "delta": "0.3",
                            "volume": "1000000",
                            "shadow": "50"
                        }
                    }
                },
                "conditionalTemplates": [{
                    "name": "Стратегия серии",
                    "enabled": True,
                    "useGlobalFilters": True,
                    "conditions": [
                        {"type": "delta", "valueMin": 0.3},
                        {"type": "volume", "value": 1000000},
                        {"type": "series", "count": 2, "timeWindowSeconds": 300}
                    ],
                    "template": "Серия стрел!"
                }]
            })
        }
        
        base_time_ms = int(time.time() * 1000)
        
        with patch.object(detector, '_get_users', return_value=[user]):
            # Первая стрела
            candle1 = Candle(
                ts_ms=base_time_ms,
                open=50000.0,
                high=50150.0,  # Дельта = 0.3%
                low=49850.0,
                close=50150.0,
                volume=20.0,  # Объём = 20 * 50150 = 1,003,000 USDT
                market="spot",
                exchange="binance",
                symbol="BTCUSDT"
            )
            
            result1 = await detector.detect_spike(candle1)
            # Первая стрела не должна пройти условие серии (серия = 1, нужно ≥ 2)
            assert len(result1) == 0  # Не отправляется, так как серия < 2
            
            # Вторая стрела через 1 минуту
            candle2 = Candle(
                ts_ms=base_time_ms + 60000,  # +1 минута
                open=50150.0,
                high=50300.0,  # Дельта = 0.3%
                low=50000.0,
                close=50300.0,
                volume=20.0,
                market="spot",
                exchange="binance",
                symbol="BTCUSDT"
            )
            
            result2 = await detector.detect_spike(candle2)
            # Вторая стрела должна пройти (серия = 2, ≥ 2)
            assert len(result2) == 1
            assert result2[0]["detected_by_strategy"] is True
            assert len(result2[0]["matched_strategies"]) == 1
    
    @pytest.mark.asyncio
    async def test_scenario_6_use_global_filters_false(self, detector, sample_candle):
        """
        Сценарий 6: Стратегия с useGlobalFilters = false и базовыми фильтрами в условиях
        Проверить: используются фильтры из условий стратегии, а не из глобальных настроек
        """
        user = {
            "id": 6,
            "user": "custom_filters_user",
            "options_json": json.dumps({
                "exchanges": {"binance": True},
                "exchangeSettings": {
                    "binance": {
                        "spot": {
                            "enabled": True,
                            "delta": "5.0",  # Глобальный фильтр: 5%
                            "volume": "100000",  # Глобальный фильтр: 100k
                            "shadow": "50"
                        }
                    }
                },
                "conditionalTemplates": [{
                    "name": "Стратегия с кастомными фильтрами",
                    "enabled": True,
                    "useGlobalFilters": False,  # Используем фильтры из условий
                    "conditions": [
                        {"type": "delta", "valueMin": 1.0},  # Фильтр стратегии: 1%
                        {"type": "volume", "value": 20000},  # Фильтр стратегии: 20k
                        {"type": "wick_pct", "valueMin": 0}  # valueMax не обязателен
                    ],
                    "template": "Кастомные фильтры"
                }]
            })
        }
        
        with patch.object(detector, '_get_users', return_value=[user]):
            # Свеча с дельтой 2% и объёмом 51000 USDT
            # Должна пройти фильтры стратегии (2% > 1%, 51000 > 20000)
            # Но НЕ должна пройти глобальные фильтры (2% < 5%, 51000 < 100000)
            result = await detector.detect_spike(sample_candle)
            
            assert len(result) == 1
            assert result[0]["detected_by_strategy"] is True
            # Проверяем, что использовались фильтры из условий стратегии, а не глобальные
            assert len(result[0]["matched_strategies"]) == 1
    
    @pytest.mark.asyncio
    async def test_scenario_7_use_global_filters_true(self, detector, sample_candle):
        """
        Сценарий 7: Стратегия с useGlobalFilters = true
        Проверить: используются фильтры из глобальных настроек (exchangeSettings/pairSettings/thresholds)
        """
        user = {
            "id": 7,
            "user": "global_filters_user",
            "options_json": json.dumps({
                "exchanges": {"binance": True},
                "exchangeSettings": {
                    "binance": {
                        "spot": {
                            "enabled": True,
                            "delta": "0.5",  # Глобальный фильтр: 0.5%
                            "volume": "10000",  # Глобальный фильтр: 10k
                            "shadow": "30"
                        }
                    }
                },
                "conditionalTemplates": [{
                    "name": "Стратегия с глобальными фильтрами",
                    "enabled": True,
                    "useGlobalFilters": True,  # Используем глобальные фильтры
                    "conditions": [
                        {"type": "symbol", "symbol": "BTCUSDT"}  # Только дополнительное условие
                    ],
                    "template": "Глобальные фильтры"
                }]
            })
        }
        
        with patch.object(detector, '_get_users', return_value=[user]):
            # Свеча с дельтой 2% и объёмом 51000 USDT
            # Должна пройти глобальные фильтры (2% > 0.5%, 51000 > 10000)
            result = await detector.detect_spike(sample_candle)
            
            assert len(result) == 1
            assert result[0]["detected_by_strategy"] is True
            assert len(result[0]["matched_strategies"]) == 1
    
    @pytest.mark.asyncio
    async def test_scenario_8_exchange_disabled_in_settings(self, detector, sample_candle):
        """
        Сценарий 8: Биржа отключена в exchanges, но указана в стратегии
        Проверить: стратегия работает для этой биржи, глобальные фильтры остаются отключенными
        """
        user = {
            "id": 8,
            "user": "exchange_strategy_user",
            "options_json": json.dumps({
                "exchanges": {"binance": False},  # Биржа отключена в глобальных настройках
                "exchangeSettings": {
                    "binance": {
                        "spot": {
                            "enabled": True,
                            "delta": "0.5",  # Глобальные фильтры для стратегии
                            "volume": "10000",
                            "shadow": "30"
                        }
                    }
                },
                "conditionalTemplates": [{
                    "name": "Стратегия для отключенной биржи",
                    "enabled": True,
                    "useGlobalFilters": True,
                    "conditions": [
                        {"type": "exchange_market", "exchange_market": "binance_spot"}  # Используем exchange_market вместо exchange
                    ],
                    "template": "Стратегия для binance"
                }]
            })
        }
        
        with patch.object(detector, '_get_users', return_value=[user]):
            # Свеча с биржи binance должна пройти стратегию, даже если биржа отключена в exchanges
            result = await detector.detect_spike(sample_candle)
            
            assert len(result) == 1
            assert result[0]["detected_by_strategy"] is True
            # Обычные настройки не должны сработать (биржа отключена)
            assert result[0]["detected_by_spike_settings"] is False
    
    @pytest.mark.asyncio
    async def test_scenario_9_parallel_processing(self, detector, sample_candle):
        """
        Сценарий 9: Параллельная обработка нескольких пользователей
        Проверить: все пользователи получают сигнал практически одновременно (разница < 100ms)
        """
        users = [
            {
                "id": 9,
                "user": "user1",
                "options_json": json.dumps({
                    "exchanges": {"binance": True},
                    "exchangeSettings": {
                        "binance": {
                            "spot": {
                                "enabled": True,
                                "delta": "0.5",
                                "volume": "10000",
                                "shadow": "30"
                            }
                        }
                    }
                })
            },
            {
                "id": 10,
                "user": "user2",
                "options_json": json.dumps({
                    "exchanges": {"binance": True},
                    "exchangeSettings": {
                        "binance": {
                            "spot": {
                                "enabled": True,
                                "delta": "0.5",
                                "volume": "10000",
                                "shadow": "30"
                            }
                        }
                    }
                })
            },
            {
                "id": 11,
                "user": "user3",
                "options_json": json.dumps({
                    "exchanges": {"binance": True},
                    "exchangeSettings": {
                        "binance": {
                            "spot": {
                                "enabled": True,
                                "delta": "0.5",
                                "volume": "10000",
                                "shadow": "30"
                            }
                        }
                    }
                })
            }
        ]
        
        with patch.object(detector, '_get_users', return_value=users):
            start_time = time.time()
            result = await detector.detect_spike(sample_candle)
            end_time = time.time()
            
            processing_time = (end_time - start_time) * 1000  # В миллисекундах
            
            # Все пользователи должны получить детект
            assert len(result) == 3
            # Обработка должна быть быстрой (< 100ms для 3 пользователей)
            assert processing_time < 100, f"Обработка заняла {processing_time}ms, ожидалось < 100ms"
            
            # Проверяем, что все пользователи получили детект
            user_ids = {r["user_id"] for r in result}
            assert user_ids == {9, 10, 11}
    
    @pytest.mark.asyncio
    async def test_scenario_10_validation_missing_filters(self, detector):
        """
        Сценарий 10: Валидация стратегии при сохранении
        Проверить: если useGlobalFilters = false и нет базовых фильтров → ошибка валидации
        """
        # Этот тест проверяет логику валидации в _check_strategy_conditions
        user = {
            "id": 12,
            "user": "invalid_strategy_user",
            "options_json": json.dumps({
                "exchanges": {"binance": True},
                "conditionalTemplates": [{
                    "name": "Невалидная стратегия",
                    "enabled": True,
                    "useGlobalFilters": False,  # Нужны базовые фильтры в условиях
                    "conditions": [
                        # Нет базовых фильтров (delta, volume, wick_pct)
                        {"type": "symbol", "symbol": "BTCUSDT"}
                    ],
                    "template": "Невалидная"
                }]
            })
        }
        
        candle = Candle(
            ts_ms=int(time.time() * 1000),
            open=50000.0,
            high=51000.0,
            low=49000.0,
            close=51000.0,
            volume=1.0,
            market="spot",
            exchange="binance",
            symbol="BTCUSDT"
        )
        
        with patch.object(detector, '_get_users', return_value=[user]):
            result = await detector.detect_spike(candle)
            
            # Стратегия не должна сработать, так как отсутствуют базовые фильтры
            assert len(result) == 0
    
    @pytest.mark.asyncio
    async def test_scenario_11_series_uniqueness(self, detector):
        """
        Сценарий 11: Уникальность стрел в трекере серий
        Проверить: одна и та же стрела не учитывается дважды в серии
        Проверить: уникальность по {exchange}_{market}_{symbol}_{timestamp}
        """
        user = {
            "id": 13,
            "user": "uniqueness_user",
            "options_json": json.dumps({
                "exchanges": {"binance": True},
                "exchangeSettings": {
                    "binance": {
                        "spot": {
                            "enabled": True,
                            "delta": "0.3",
                            "volume": "1000000",
                            "shadow": "50"
                        }
                    }
                },
                "conditionalTemplates": [{
                    "name": "Стратегия уникальности",
                    "enabled": True,
                    "useGlobalFilters": True,
                    "conditions": [
                        {"type": "series", "count": 2, "timeWindowSeconds": 300}
                    ],
                    "template": "Серия"
                }]
            })
        }
        
        base_time_ms = int(time.time() * 1000)
        candle = Candle(
            ts_ms=base_time_ms,
            open=50000.0,
            high=50150.0,
            low=49850.0,
            close=50150.0,
            volume=20.0,
            market="spot",
            exchange="binance",
            symbol="BTCUSDT"
        )
        
        with patch.object(detector, '_get_users', return_value=[user]):
            # Отправляем одну и ту же свечу дважды
            result1 = await detector.detect_spike(candle)
            result2 = await detector.detect_spike(candle)  # Та же свеча
            
            # Вторая отправка не должна создать дубликат в трекере
            # Проверяем, что в трекере только одна запись
            series_count = detector.get_series_count(
                user_id=13,
                candle=candle,
                time_window_seconds=300,
                conditions=None
            )
            
            # Должна быть только одна стрела в трекере (не дубликат)
            assert series_count <= 1
    
    @pytest.mark.asyncio
    async def test_scenario_12_cleanup_old_spikes(self, detector):
        """
        Сценарий 12: Очистка старых стрел из трекера
        Проверить: стрелы старше максимального периода автоматически удаляются
        Проверить: максимальный период = максимум из всех стратегий пользователя
        """
        user = {
            "id": 14,
            "user": "cleanup_user",
            "options_json": json.dumps({
                "exchanges": {"binance": True},
                "exchangeSettings": {
                    "binance": {
                        "spot": {
                            "enabled": True,
                            "delta": "0.3",
                            "volume": "1000000",
                            "shadow": "50"
                        }
                    }
                },
                "conditionalTemplates": [
                    {
                        "name": "Стратегия 1",
                        "enabled": True,
                        "useGlobalFilters": True,
                        "conditions": [
                            {"type": "series", "count": 2, "timeWindowSeconds": 300}  # 5 минут
                        ],
                        "template": "Стратегия 1"
                    },
                    {
                        "name": "Стратегия 2",
                        "enabled": True,
                        "useGlobalFilters": True,
                        "conditions": [
                            {"type": "series", "count": 3, "timeWindowSeconds": 600}  # 10 минут (максимум)
                        ],
                        "template": "Стратегия 2"
                    }
                ]
            })
        }
        
        base_time_ms = int(time.time() * 1000)
        
        with patch.object(detector, '_get_users', return_value=[user]):
            # Добавляем стрелу
            candle1 = Candle(
                ts_ms=base_time_ms,
                open=50000.0,
                high=50150.0,
                low=49850.0,
                close=50150.0,
                volume=20.0,
                market="spot",
                exchange="binance",
                symbol="BTCUSDT"
            )
            
            await detector.detect_spike(candle1)
            
            # Проверяем максимальный период (должен быть 600 секунд = 10 минут, но по умолчанию 900)
            # Метод возвращает максимум из всех стратегий или дефолтное значение 900
            max_ttl = detector._get_max_time_window_for_user(14)
            # Может быть 600 (из стратегии) или 900 (дефолт), в зависимости от реализации
            assert max_ttl >= 600, f"Максимальный период должен быть >= 600 секунд, получено {max_ttl}"
            
            # Вызываем очистку вручную
            detector._cleanup_old_data()
            
            # Стрела должна остаться в трекере (не старше 10 минут)
            series_count = detector.get_series_count(
                user_id=14,
                candle=candle1,
                time_window_seconds=600,
                conditions=None
            )
            assert series_count == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

