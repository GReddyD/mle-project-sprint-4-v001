"""
Pydantic модели для API сервиса рекомендаций.
"""

from typing import List, Literal
from pydantic import BaseModel, Field


# Типы рекомендаций
RecommendationType = Literal["personal", "default", "blended"]


class RecommendationResponse(BaseModel):
    """Ответ с рекомендациями."""
    user_id: int = Field(..., ge=0, description="Идентификатор пользователя")
    recommendations: List[int] = Field(
        ...,
        min_length=0,
        max_length=100,
        description="Список идентификаторов рекомендованных треков"
    )
    recommendation_type: RecommendationType = Field(
        ...,
        description="Тип рекомендаций: personal, default или blended"
    )


class FeedbackRequest(BaseModel):
    """Запрос на добавление взаимодействия в онлайн-историю."""
    track_id: int = Field(..., ge=0, description="Идентификатор трека")


class FeedbackResponse(BaseModel):
    """Ответ на добавление взаимодействия."""
    user_id: int = Field(..., ge=0, description="Идентификатор пользователя")
    track_id: int = Field(..., ge=0, description="Идентификатор трека")
    message: str = Field(..., min_length=1, description="Сообщение о результате")


class HealthResponse(BaseModel):
    """Ответ о состоянии сервиса."""
    status: str = Field(..., description="Статус сервиса")
    users_with_personal_recs: int = Field(
        ...,
        ge=0,
        description="Количество пользователей с персональными рекомендациями"
    )
    tracks_with_similar: int = Field(
        ...,
        ge=0,
        description="Количество треков с похожими"
    )
    users_with_online_history: int = Field(
        ...,
        ge=0,
        description="Количество пользователей с онлайн-историей"
    )
