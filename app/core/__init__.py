"""
Ядро сервиса рекомендаций: движок, хранилище, конфигурация.
"""

from app.core.config import EngineConfig
from app.core.store import RecommendationsStore, DataValidationError
from app.core.engine import RecommendationsEngine

__all__ = [
    "EngineConfig",
    "RecommendationsStore",
    "DataValidationError",
    "RecommendationsEngine"
]
