"""
Точка входа для запуска FastAPI сервиса рекомендаций.

Сервис поддерживает:
- Офлайн-рекомендации (персональные ALS, топ популярных)
- Онлайн-рекомендации (похожие треки на основе истории пользователя)
- Смешивание онлайн и офлайн рекомендаций

Запуск:
    python recommendations_service.py

Или с помощью uvicorn:
    uvicorn app:app --host 0.0.0.0 --port 8000
"""

import os

import uvicorn

from app import app


if __name__ == "__main__":
    # Параметры запуска
    host = os.getenv("SERVICE_HOST", "0.0.0.0")
    port = int(os.getenv("SERVICE_PORT", "8000"))

    uvicorn.run(app, host=host, port=port)
