"""
Эндпоинты API сервиса рекомендаций.
"""

from fastapi import APIRouter, HTTPException

from app.models import (
    RecommendationResponse,
    FeedbackRequest,
    FeedbackResponse,
    HealthResponse
)
from app.main import get_store, get_engine

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health_check():
    """Проверка состояния сервиса."""
    store = get_store()
    if not store.is_loaded():
        raise HTTPException(status_code=503, detail="Service not ready - data not loaded")

    stats = store.get_stats()
    return HealthResponse(
        status="healthy",
        users_with_personal_recs=stats["users_with_personal_recs"],
        tracks_with_similar=stats["tracks_with_similar"],
        users_with_online_history=stats["users_with_online_history"]
    )


@router.get("/recommendations/{user_id}", response_model=RecommendationResponse)
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
    store = get_store()
    engine = get_engine()

    if not store.is_loaded():
        raise HTTPException(status_code=503, detail="Service not ready - data not loaded")

    if k < 1 or k > 100:
        raise HTTPException(status_code=400, detail="k must be between 1 and 100")

    return engine.get_recommendations(user_id, k)


@router.put("/recommendations/{user_id}/feedback", response_model=FeedbackResponse)
def add_feedback(user_id: int, feedback: FeedbackRequest):
    """
    Добавить взаимодействие в онлайн-историю пользователя.

    - **user_id**: Идентификатор пользователя
    - **track_id**: Идентификатор прослушанного трека

    После добавления трека в историю, последующие запросы рекомендаций
    будут учитывать этот трек при формировании онлайн-рекомендаций.
    """
    store = get_store()
    engine = get_engine()

    if not store.is_loaded():
        raise HTTPException(status_code=503, detail="Service not ready - data not loaded")

    engine.add_to_online_history(user_id, feedback.track_id)

    return FeedbackResponse(
        user_id=user_id,
        track_id=feedback.track_id,
        message=f"Track {feedback.track_id} added to online history"
    )
