"""
Хранилище рекомендаций с валидацией загрузки данных.
"""

import os
import logging
from typing import List, Dict
from collections import defaultdict

import pandas as pd

logger = logging.getLogger(__name__)


class DataValidationError(Exception):
    """Ошибка валидации загруженных данных."""
    pass


class RecommendationsStore:
    """
    Хранилище рекомендаций и онлайн-истории пользователей.

    Атрибуты:
        top_popular: Список топ популярных треков
        personal_recs: Dict[user_id -> List[track_id]] персональные рекомендации
        similar_tracks: Dict[track_id -> List[track_id]] похожие треки
        online_history: Dict[user_id -> List[track_id]] онлайн-история пользователей
    """

    # Ожидаемые колонки для каждого файла
    EXPECTED_COLUMNS = {
        "top_popular": {"track_id", "rank"},
        "personal_als": {"user_id", "track_id", "rank"},
        "similar": {"track_id", "similar_track_id", "rank"}
    }

    def __init__(self):
        self.top_popular: List[int] = []
        self.personal_recs: Dict[int, List[int]] = {}
        self.similar_tracks: Dict[int, List[int]] = {}
        self.online_history: Dict[int, List[int]] = defaultdict(list)
        self._loaded = False

    def _validate_dataframe(
        self,
        df: pd.DataFrame,
        file_type: str,
        file_path: str
    ) -> None:
        """
        Валидация загруженного DataFrame.

        Args:
            df: Загруженный DataFrame
            file_type: Тип файла (top_popular, personal_als, similar)
            file_path: Путь к файлу для сообщений об ошибках

        Raises:
            DataValidationError: Если данные не прошли валидацию
        """
        # Проверка на пустой DataFrame
        if df.empty:
            raise DataValidationError(
                f"Файл {file_path} пустой"
            )

        # Проверка наличия обязательных колонок
        expected_cols = self.EXPECTED_COLUMNS.get(file_type, set())
        missing_cols = expected_cols - set(df.columns)
        if missing_cols:
            raise DataValidationError(
                f"Файл {file_path} не содержит обязательные колонки: {missing_cols}"
            )

        # Проверка на отрицательные значения в ID колонках
        id_columns = [col for col in df.columns if "id" in col.lower()]
        for col in id_columns:
            if (df[col] < 0).any():
                raise DataValidationError(
                    f"Файл {file_path} содержит отрицательные значения в колонке {col}"
                )

        # Проверка на NaN в ключевых колонках
        for col in expected_cols:
            if df[col].isna().any():
                raise DataValidationError(
                    f"Файл {file_path} содержит NaN значения в колонке {col}"
                )

        logger.debug(f"Валидация {file_path} успешна: {len(df)} записей")

    def load_recommendations(self, data_path: str = "recsys/recommendations") -> None:
        """
        Загрузка рекомендаций из parquet файлов с валидацией.

        Args:
            data_path: Путь к директории с файлами рекомендаций

        Raises:
            DataValidationError: Если данные не прошли валидацию
            FileNotFoundError: Если директория не существует
        """
        logger.info(f"Загрузка рекомендаций из {data_path}...")

        if not os.path.exists(data_path):
            raise FileNotFoundError(f"Директория {data_path} не существует")

        errors = []

        # 1. Загрузка топ популярных треков
        top_popular_path = os.path.join(data_path, "top_popular.parquet")
        if os.path.exists(top_popular_path):
            try:
                df = pd.read_parquet(top_popular_path)
                self._validate_dataframe(df, "top_popular", top_popular_path)
                self.top_popular = (
                    df.drop_duplicates(subset=['track_id'])
                    .sort_values('rank')['track_id']
                    .tolist()
                )
                logger.info(f"  Загружено {len(self.top_popular)} топ популярных треков")
            except DataValidationError as e:
                errors.append(str(e))
            except Exception as e:
                errors.append(f"Ошибка загрузки {top_popular_path}: {e}")
        else:
            logger.warning(f"  Файл {top_popular_path} не найден")

        # 2. Загрузка персональных рекомендаций
        personal_path = os.path.join(data_path, "personal_als.parquet")
        if os.path.exists(personal_path):
            try:
                df = pd.read_parquet(personal_path)
                self._validate_dataframe(df, "personal_als", personal_path)
                for user_id, group in df.groupby('user_id'):
                    self.personal_recs[int(user_id)] = (
                        group.sort_values('rank')['track_id'].tolist()
                    )
                logger.info(
                    f"  Загружены персональные рекомендации "
                    f"для {len(self.personal_recs)} пользователей"
                )
            except DataValidationError as e:
                errors.append(str(e))
            except Exception as e:
                errors.append(f"Ошибка загрузки {personal_path}: {e}")
        else:
            logger.warning(f"  Файл {personal_path} не найден")

        # 3. Загрузка похожих треков
        similar_path = os.path.join(data_path, "similar.parquet")
        if os.path.exists(similar_path):
            try:
                df = pd.read_parquet(similar_path)
                self._validate_dataframe(df, "similar", similar_path)
                for track_id, group in df.groupby('track_id'):
                    self.similar_tracks[int(track_id)] = (
                        group.sort_values('rank')['similar_track_id'].tolist()
                    )
                logger.info(
                    f"  Загружены похожие треки для {len(self.similar_tracks)} треков"
                )
            except DataValidationError as e:
                errors.append(str(e))
            except Exception as e:
                errors.append(f"Ошибка загрузки {similar_path}: {e}")
        else:
            logger.warning(f"  Файл {similar_path} не найден")

        # Проверка наличия критических ошибок
        if errors:
            error_msg = "Ошибки валидации данных:\n" + "\n".join(errors)
            logger.error(error_msg)
            raise DataValidationError(error_msg)

        # Проверка что загружены минимально необходимые данные
        if not self.top_popular:
            raise DataValidationError(
                "Не загружены топ-популярные треки - сервис не сможет работать"
            )

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
