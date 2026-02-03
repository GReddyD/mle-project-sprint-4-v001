"""
FastAPI приложение для сервиса рекомендаций.
"""

import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from models import (
    RecommendationResponse,
    FeedbackRequest,
    FeedbackResponse,
    HealthResponse
)
from store import RecommendationsStore, DataValidationError
from engine import RecommendationsEngine

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Глобальные объекты
store = RecommendationsStore()
engine: RecommendationsEngine = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle события приложения."""
    global engine

    # Startup: загружаем данные
    data_path = os.getenv("RECOMMENDATIONS_PATH", "recsys/recommendations")

    # Гиперпараметры движка из переменных окружения
    recent_tracks_count = int(os.getenv("RECENT_TRACKS_COUNT", "5"))
    max_history_size = int(os.getenv("MAX_HISTORY_SIZE", "100"))
    default_k = int(os.getenv("DEFAULT_K", "10"))

    try:
        store.load_recommendations(data_path)
        engine = RecommendationsEngine(
            store=store,
            recent_tracks_count=recent_tracks_count,
            max_history_size=max_history_size,
            default_k=default_k
        )
        logger.info(
            f"Движок инициализирован: "
            f"recent_tracks_count={recent_tracks_count}, "
            f"max_history_size={max_history_size}, "
            f"default_k={default_k}"
        )
    except (DataValidationError, FileNotFoundError) as e:
        logger.error(f"Ошибка загрузки данных: {e}")
        raise

    yield
    # Shutdown: ничего особенного


app = FastAPI(
    title="Recommendations Service",
    description="Микросервис для выдачи персонализированных рекомендаций треков",
    version="1.0.0",
    lifespan=lifespan
)


# ============================================================================
# Эндпоинты API
# ============================================================================

@app.get("/health", response_model=HealthResponse)
def health_check():
    """Проверка состояния сервиса."""
    if not store.is_loaded():
        raise HTTPException(status_code=503, detail="Service not ready - data not loaded")

    stats = store.get_stats()
    return HealthResponse(
        status="healthy",
        users_with_personal_recs=stats["users_with_personal_recs"],
        tracks_with_similar=stats["tracks_with_similar"],
        users_with_online_history=stats["users_with_online_history"]
    )


@app.get("/recommendations/{user_id}", response_model=RecommendationResponse)
def get_recommendations(user_id: int, k: int = 10):
    """
    Получить рекомендации для пользователя.

    - **user_id**: Идентификатор пользователя
    - **k**: Количество рекомендаций (по умолчанию 10)

    Возвращает рекомендации с указанием их типа:
    - **default**: Топ популярных (для пользователей без персональных рекомендаций)
    - **personal**: Персональные ALS (для пользователей без онлайн-истории)
    - **blended**: Смешанные онлайн + офлайн (для пользователей с историей)
    """
    if not store.is_loaded():
        raise HTTPException(status_code=503, detail="Service not ready - data not loaded")

    if k < 1 or k > 100:
        raise HTTPException(status_code=400, detail="k must be between 1 and 100")

    return engine.get_recommendations(user_id, k)


@app.put("/recommendations/{user_id}/feedback", response_model=FeedbackResponse)
def add_feedback(user_id: int, feedback: FeedbackRequest):
    """
    Добавить взаимодействие в онлайн-историю пользователя.

    - **user_id**: Идентификатор пользователя
    - **track_id**: Идентификатор прослушанного трека

    После добавления трека в историю, последующие запросы рекомендаций
    будут учитывать этот трек при формировании онлайн-рекомендаций.
    """
    if not store.is_loaded():
        raise HTTPException(status_code=503, detail="Service not ready - data not loaded")

    engine.add_to_online_history(user_id, feedback.track_id)

    return FeedbackResponse(
        user_id=user_id,
        track_id=feedback.track_id,
        message=f"Track {feedback.track_id} added to online history"
    )
