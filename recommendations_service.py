"""
FastAPI микросервис для выдачи рекомендаций.

Сервис поддерживает:
- Офлайн-рекомендации (персональные ALS, топ популярных)
- Онлайн-рекомендации (похожие треки на основе истории пользователя)
- Смешивание онлайн и офлайн рекомендаций
"""

import os
import logging
from typing import List, Optional
from contextlib import asynccontextmanager
from collections import defaultdict

import pandas as pd
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================================================
# Pydantic модели для API
# ============================================================================

class RecommendationResponse(BaseModel):
    """Ответ с рекомендациями."""
    user_id: int
    recommendations: List[int]
    recommendation_type: str  # "personal", "default", "blended"


class FeedbackRequest(BaseModel):
    """Запрос на добавление взаимодействия в онлайн-историю."""
    track_id: int


class FeedbackResponse(BaseModel):
    """Ответ на добавление взаимодействия."""
    user_id: int
    track_id: int
    message: str


class HealthResponse(BaseModel):
    """Ответ о состоянии сервиса."""
    status: str
    users_with_personal_recs: int
    tracks_with_similar: int
    users_with_online_history: int


# ============================================================================
# Хранилище данных
# ============================================================================

class RecommendationsStore:
    """
    Хранилище рекомендаций и онлайн-истории пользователей.

    Атрибуты:
        top_popular: DataFrame с топ популярными треками
        personal_recs: Dict[user_id -> List[track_id]] персональные рекомендации
        similar_tracks: Dict[track_id -> List[track_id]] похожие треки
        online_history: Dict[user_id -> List[track_id]] онлайн-история пользователей
    """

    def __init__(self):
        self.top_popular: List[int] = []
        self.personal_recs: dict = {}
        self.similar_tracks: dict = {}
        self.online_history: dict = defaultdict(list)
        self._loaded = False

    def load_recommendations(self, data_path: str = "recsys/recommendations"):
        """
        Загрузка рекомендаций из parquet файлов.

        Args:
            data_path: Путь к директории с файлами рекомендаций
        """
        logger.info(f"Загрузка рекомендаций из {data_path}...")

        # 1. Загрузка топ популярных треков
        top_popular_path = os.path.join(data_path, "top_popular.parquet")
        if os.path.exists(top_popular_path):
            df = pd.read_parquet(top_popular_path)
            # Берём уникальные треки, отсортированные по рангу
            self.top_popular = (
                df.drop_duplicates(subset=['track_id'])
                .sort_values('rank')['track_id']
                .tolist()
            )
            logger.info(f"  ✓ Загружено {len(self.top_popular)} топ популярных треков")
        else:
            logger.warning(f"  ⚠️ Файл {top_popular_path} не найден")

        # 2. Загрузка персональных рекомендаций
        personal_path = os.path.join(data_path, "personal_als.parquet")
        if os.path.exists(personal_path):
            df = pd.read_parquet(personal_path)
            # Группируем по пользователям
            for user_id, group in df.groupby('user_id'):
                self.personal_recs[int(user_id)] = (
                    group.sort_values('rank')['track_id'].tolist()
                )
            logger.info(f"  ✓ Загружены персональные рекомендации для {len(self.personal_recs)} пользователей")
        else:
            logger.warning(f"  ⚠️ Файл {personal_path} не найден")

        # 3. Загрузка похожих треков
        similar_path = os.path.join(data_path, "similar.parquet")
        if os.path.exists(similar_path):
            df = pd.read_parquet(similar_path)
            # Группируем по трекам
            for track_id, group in df.groupby('track_id'):
                self.similar_tracks[int(track_id)] = (
                    group.sort_values('rank')['similar_track_id'].tolist()
                )
            logger.info(f"  ✓ Загружены похожие треки для {len(self.similar_tracks)} треков")
        else:
            logger.warning(f"  ⚠️ Файл {similar_path} не найден")

        self._loaded = True
        logger.info("Загрузка рекомендаций завершена!")

    def is_loaded(self) -> bool:
        """Проверка, загружены ли данные."""
        return self._loaded

    def get_stats(self) -> dict:
        """Получение статистики хранилища."""
        return {
            "users_with_personal_recs": len(self.personal_recs),
            "tracks_with_similar": len(self.similar_tracks),
            "users_with_online_history": len(self.online_history),
            "top_popular_count": len(self.top_popular)
        }


# ============================================================================
# Логика рекомендаций
# ============================================================================

class RecommendationsEngine:
    """
    Движок рекомендаций с поддержкой смешивания онлайн и офлайн.

    Стратегия смешивания (blending):
    1. Если нет персональных рекомендаций → возвращаем топ популярных (default)
    2. Если нет онлайн-истории → возвращаем персональные ALS (personal)
    3. Если есть онлайн-история → смешиваем (blended):
       - 50% - похожие на последние прослушанные треки
       - 50% - персональные ALS рекомендации
       - Исключаем уже прослушанные треки
    """

    def __init__(self, store: RecommendationsStore):
        self.store = store
        self.default_k = 10  # Количество рекомендаций по умолчанию

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
            # Нет персональных → топ популярных
            recs = self._get_default_recommendations(k)
            rec_type = "default"
            logger.info(f"User {user_id}: default recommendations (no personal recs)")

        elif not has_online_history:
            # Есть персональные, нет онлайн-истории → персональные ALS
            recs = self._get_personal_recommendations(user_id, k)
            rec_type = "personal"
            logger.info(f"User {user_id}: personal recommendations (no online history)")

        else:
            # Есть всё → смешиваем
            recs = self._get_blended_recommendations(user_id, k, online_history)
            rec_type = "blended"
            logger.info(f"User {user_id}: blended recommendations (online history: {len(online_history)} tracks)")

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
        recent_tracks = online_history[-5:][::-1]  # Последние 5 в обратном порядке

        for track_id in recent_tracks:
            similar = self.store.similar_tracks.get(track_id, [])
            for similar_track in similar:
                if similar_track not in exclude and similar_track not in seen:
                    similar_candidates.append(similar_track)
                    seen.add(similar_track)
                    if len(similar_candidates) >= k:
                        return similar_candidates

        return similar_candidates

    def add_to_online_history(self, user_id: int, track_id: int):
        """
        Добавить трек в онлайн-историю пользователя.

        Args:
            user_id: Идентификатор пользователя
            track_id: Идентификатор трека
        """
        self.store.online_history[user_id].append(track_id)
        # Ограничиваем размер истории (последние 100 треков)
        if len(self.store.online_history[user_id]) > 100:
            self.store.online_history[user_id] = self.store.online_history[user_id][-100:]

        logger.info(f"User {user_id}: added track {track_id} to online history")


# ============================================================================
# FastAPI приложение
# ============================================================================

# Глобальные объекты
store = RecommendationsStore()
engine = RecommendationsEngine(store)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle события приложения."""
    # Startup: загружаем данные
    data_path = os.getenv("RECOMMENDATIONS_PATH", "recsys/recommendations")
    store.load_recommendations(data_path)
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


# ============================================================================
# Запуск сервиса
# ============================================================================

if __name__ == "__main__":
    import uvicorn

    # Параметры запуска
    host = os.getenv("SERVICE_HOST", "0.0.0.0")
    port = int(os.getenv("SERVICE_PORT", "8000"))

    uvicorn.run(app, host=host, port=port)
