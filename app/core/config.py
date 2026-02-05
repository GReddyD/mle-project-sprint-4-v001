"""
Конфигурация движка рекомендаций с pydantic валидацией.
"""

from pydantic import BaseModel, Field, model_validator


class EngineConfig(BaseModel):
    """
    Конфигурация движка рекомендаций с валидацией параметров.

    Attributes:
        recent_tracks_count: Количество последних треков для онлайн-рекомендаций.
            Должно быть от 1 до 50.
        max_history_size: Максимальный размер онлайн-истории пользователя.
            Должно быть от 1 до 10000 и не меньше recent_tracks_count.
        default_k: Количество рекомендаций по умолчанию.
            Должно быть от 1 до 100.
    """

    recent_tracks_count: int = Field(
        default=5,
        ge=1,
        le=50,
        description="Количество последних треков для онлайн-рекомендаций"
    )
    max_history_size: int = Field(
        default=100,
        ge=1,
        le=10000,
        description="Максимальный размер онлайн-истории пользователя"
    )
    default_k: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Количество рекомендаций по умолчанию"
    )

    @model_validator(mode='after')
    def validate_history_size(self) -> 'EngineConfig':
        """Проверка, что max_history_size >= recent_tracks_count."""
        if self.max_history_size < self.recent_tracks_count:
            raise ValueError(
                f"max_history_size ({self.max_history_size}) должен быть >= "
                f"recent_tracks_count ({self.recent_tracks_count})"
            )
        return self

    model_config = {
        "frozen": False,
        "extra": "forbid"
    }
