"""
Движок рекомендаций с поддержкой смешивания онлайн и офлайн.
"""

import logging
from typing import List

from app.models.schemas import RecommendationResponse
from app.core.store import RecommendationsStore
from app.core.config import EngineConfig

logger = logging.getLogger(__name__)


class RecommendationsEngine:
    """
    Движок рекомендаций с поддержкой смешивания онлайн и офлайн.

    Стратегия смешивания (blending):
    1. Если нет персональных рекомендаций -> возвращаем топ популярных (default)
    2. Если нет онлайн-истории -> возвращаем персональные ALS (personal)
    3. Если есть онлайн-история -> смешиваем (blended):
       - 50% - похожие на последние прослушанные треки
       - 50% - персональные ALS рекомендации
       - Исключаем уже прослушанные треки

    Гиперпараметры:
        recent_tracks_count: Количество последних треков для онлайн-рекомендаций
        max_history_size: Максимальный размер онлайн-истории пользователя
    """

    def __init__(
        self,
        store: RecommendationsStore,
        config: EngineConfig | None = None,
        recent_tracks_count: int = 5,
        max_history_size: int = 100,
        default_k: int = 10
    ):
        """
        Инициализация движка рекомендаций.

        Args:
            store: Хранилище рекомендаций
            config: Конфигурация движка (опционально). Если передан config,
                    остальные параметры игнорируются.
            recent_tracks_count: Количество последних треков для онлайн-рекомендаций
            max_history_size: Максимальный размер онлайн-истории пользователя
            default_k: Количество рекомендаций по умолчанию

        Raises:
            ValidationError: Если параметры конфигурации невалидны
        """
        self.store = store

        # Используем переданный config или создаём новый с валидацией
        if config is not None:
            self._config = config
        else:
            self._config = EngineConfig(
                recent_tracks_count=recent_tracks_count,
                max_history_size=max_history_size,
                default_k=default_k
            )

        self.recent_tracks_count = self._config.recent_tracks_count
        self.max_history_size = self._config.max_history_size
        self.default_k = self._config.default_k

    @property
    def config(self) -> EngineConfig:
        """Получить текущую конфигурацию движка."""
        return self._config

    def get_recommendations(
        self,
        user_id: int,
        k: int = None
    ) -> RecommendationResponse:
        """
        Получить рекомендации для пользователя.

        Args:
            user_id: Идентификатор пользователя
            k: Количество рекомендаций

        Returns:
            RecommendationResponse с рекомендациями и их типом
        """
        if k is None:
            k = self.default_k

        # Проверяем наличие персональных рекомендаций
        has_personal = user_id in self.store.personal_recs

        # Проверяем наличие онлайн-истории
        online_history = self.store.online_history.get(user_id, [])
        has_online_history = len(online_history) > 0

        # Выбираем стратегию
        if not has_personal:
            # Нет персональных -> топ популярных
            recs = self._get_default_recommendations(k)
            rec_type = "default"
            logger.info(f"User {user_id}: default recommendations (no personal recs)")

        elif not has_online_history:
            # Есть персональные, нет онлайн-истории -> персональные ALS
            recs = self._get_personal_recommendations(user_id, k)
            rec_type = "personal"
            logger.info(f"User {user_id}: personal recommendations (no online history)")

        else:
            # Есть всё -> смешиваем
            recs = self._get_blended_recommendations(user_id, k, online_history)
            rec_type = "blended"
            logger.info(
                f"User {user_id}: blended recommendations "
                f"(online history: {len(online_history)} tracks)"
            )

        return RecommendationResponse(
            user_id=user_id,
            recommendations=recs,
            recommendation_type=rec_type
        )

    def _get_default_recommendations(self, k: int) -> List[int]:
        """Получить топ популярных треков."""
        return self.store.top_popular[:k]

    def _get_personal_recommendations(self, user_id: int, k: int) -> List[int]:
        """Получить персональные рекомендации ALS."""
        return self.store.personal_recs.get(user_id, [])[:k]

    def _get_blended_recommendations(
        self,
        user_id: int,
        k: int,
        online_history: List[int]
    ) -> List[int]:
        """
        Получить смешанные рекомендации.

        Стратегия:
        - 50% (k//2) рекомендаций - похожие на последние прослушанные
        - 50% (k - k//2) рекомендаций - персональные ALS
        - Исключаем уже прослушанные треки
        """
        # Множество уже прослушанных треков для фильтрации
        listened = set(online_history)

        # 1. Получаем похожие треки на основе последних прослушанных
        online_k = k // 2
        online_recs = self._get_similar_to_history(online_history, online_k, listened)

        # 2. Получаем персональные рекомендации (исключая уже рекомендованные)
        personal_k = k - len(online_recs)
        already_recommended = set(online_recs)
        personal_recs = [
            track_id
            for track_id in self.store.personal_recs.get(user_id, [])
            if track_id not in listened and track_id not in already_recommended
        ][:personal_k]

        # 3. Объединяем: сначала онлайн, потом персональные
        blended = online_recs + personal_recs

        # 4. Если не хватает, добираем из топ популярных
        if len(blended) < k:
            already_have = set(blended) | listened
            additional = [
                track_id
                for track_id in self.store.top_popular
                if track_id not in already_have
            ][:k - len(blended)]
            blended.extend(additional)

        return blended[:k]

    def _get_similar_to_history(
        self,
        online_history: List[int],
        k: int,
        exclude: set
    ) -> List[int]:
        """
        Получить треки, похожие на последние прослушанные.

        Args:
            online_history: Список последних прослушанных треков
            k: Количество рекомендаций
            exclude: Множество треков для исключения

        Returns:
            Список похожих треков
        """
        similar_candidates = []
        seen = set()

        # Берём последние N треков из истории (более свежие = более релевантные)
        recent_tracks = online_history[-self.recent_tracks_count:][::-1]

        for track_id in recent_tracks:
            similar = self.store.similar_tracks.get(track_id, [])
            for similar_track in similar:
                if similar_track not in exclude and similar_track not in seen:
                    similar_candidates.append(similar_track)
                    seen.add(similar_track)
                    if len(similar_candidates) >= k:
                        return similar_candidates

        return similar_candidates

    def add_to_online_history(self, user_id: int, track_id: int) -> None:
        """
        Добавить трек в онлайн-историю пользователя.

        Args:
            user_id: Идентификатор пользователя
            track_id: Идентификатор трека
        """
        self.store.online_history[user_id].append(track_id)

        # Ограничиваем размер истории
        if len(self.store.online_history[user_id]) > self.max_history_size:
            self.store.online_history[user_id] = (
                self.store.online_history[user_id][-self.max_history_size:]
            )

        logger.info(f"User {user_id}: added track {track_id} to online history")
