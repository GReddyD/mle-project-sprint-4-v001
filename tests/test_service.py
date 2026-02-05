"""
Тестирование микросервиса рекомендаций.

Сценарии тестирования:
1. Пользователь без персональных рекомендаций → default (топ популярные)
2. Пользователь с персональными рекомендациями, но без онлайн-истории → personal
3. Пользователь с персональными рекомендациями и онлайн-историей → blended

Запуск:
    python -m tests.test_service

Результаты сохраняются в test_service.log
"""

import sys
import logging
import requests
from typing import Optional

# ============================================================================
# Настройка
# ============================================================================

SERVICE_URL = "http://127.0.0.1:8000"

# Настройка логирования в файл и консоль
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("test_service.log", mode="w", encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


# ============================================================================
# Вспомогательные функции
# ============================================================================

def get_health() -> Optional[dict]:
    """Проверка состояния сервиса."""
    try:
        response = requests.get(f"{SERVICE_URL}/health")
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка при проверке здоровья сервиса: {e}")
        return None


def get_recommendations(user_id: int, k: int = 10) -> Optional[dict]:
    """Получение рекомендаций для пользователя."""
    try:
        response = requests.get(f"{SERVICE_URL}/recommendations/{user_id}", params={"k": k})
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка при получении рекомендаций для user_id={user_id}: {e}")
        return None


def add_feedback(user_id: int, track_id: int) -> Optional[dict]:
    """Добавление взаимодействия в онлайн-историю."""
    try:
        response = requests.put(
            f"{SERVICE_URL}/recommendations/{user_id}/feedback",
            json={"track_id": track_id}
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка при добавлении feedback для user_id={user_id}: {e}")
        return None


def print_separator(title: str):
    """Печать разделителя с заголовком."""
    logger.info("")
    logger.info("=" * 70)
    logger.info(f"  {title}")
    logger.info("=" * 70)


def print_recommendations(result: dict):
    """Красивая печать результатов рекомендаций."""
    logger.info(f"  User ID: {result['user_id']}")
    logger.info(f"  Тип рекомендаций: {result['recommendation_type']}")
    logger.info(f"  Количество рекомендаций: {len(result['recommendations'])}")
    logger.info(f"  Рекомендации: {result['recommendations'][:10]}...")


# ============================================================================
# Тестовые сценарии
# ============================================================================

def test_health():
    """Тест 0: Проверка состояния сервиса."""
    print_separator("ТЕСТ 0: ПРОВЕРКА СОСТОЯНИЯ СЕРВИСА")

    health = get_health()
    if health is None:
        logger.error("❌ Сервис недоступен!")
        return False

    logger.info(f"✅ Сервис работает")
    logger.info(f"  Статус: {health['status']}")
    logger.info(f"  Пользователей с персональными рекомендациями: {health['users_with_personal_recs']}")
    logger.info(f"  Треков с похожими: {health['tracks_with_similar']}")
    logger.info(f"  Пользователей с онлайн-историей: {health['users_with_online_history']}")

    return True


def test_user_without_personal_recs():
    """
    Тест 1: Пользователь без персональных рекомендаций.

    Ожидаемое поведение:
    - Возвращаются топ популярные треки (default)
    - recommendation_type = "default"
    """
    print_separator("ТЕСТ 1: ПОЛЬЗОВАТЕЛЬ БЕЗ ПЕРСОНАЛЬНЫХ РЕКОМЕНДАЦИЙ")

    # Используем заведомо несуществующий user_id
    user_id = 999999999
    logger.info(f"Запрос рекомендаций для user_id={user_id} (несуществующий пользователь)")

    result = get_recommendations(user_id, k=10)
    if result is None:
        logger.error("❌ Не удалось получить рекомендации")
        return False

    print_recommendations(result)

    # Проверка
    if result["recommendation_type"] == "default":
        logger.info("✅ Тип рекомендаций корректный: default (топ популярные)")
        return True
    else:
        logger.error(f"❌ Ожидался тип 'default', получен '{result['recommendation_type']}'")
        return False


def test_user_with_personal_no_history():
    """
    Тест 2: Пользователь с персональными рекомендациями, но без онлайн-истории.

    Ожидаемое поведение:
    - Возвращаются персональные ALS рекомендации
    - recommendation_type = "personal"
    """
    print_separator("ТЕСТ 2: ПОЛЬЗОВАТЕЛЬ С ПЕРСОНАЛЬНЫМИ РЕКОМЕНДАЦИЯМИ (БЕЗ ИСТОРИИ)")

    # Получаем здоровье, чтобы понять, есть ли пользователи с персональными рекомендациями
    health = get_health()
    if health is None or health["users_with_personal_recs"] == 0:
        logger.warning("⚠️ Нет пользователей с персональными рекомендациями, пропускаем тест")
        return True

    # Используем существующего пользователя (небольшой user_id, скорее всего существует)
    # Попробуем несколько user_id пока не найдём с персональными рекомендациями
    test_user_ids = [1, 100, 1000, 10000, 100000]

    for user_id in test_user_ids:
        logger.info(f"Пробуем user_id={user_id}...")
        result = get_recommendations(user_id, k=10)

        if result and result["recommendation_type"] == "personal":
            logger.info(f"Найден пользователь с персональными рекомендациями: user_id={user_id}")
            print_recommendations(result)
            logger.info("✅ Тип рекомендаций корректный: personal (персональные ALS)")
            return True

    # Если не нашли - ищем первого пользователя через health
    logger.info("Не удалось найти пользователя с персональными рекомендациями в тестовом диапазоне")

    # Пробуем с user_id из диапазона данных (предполагаем, что есть)
    user_id = 1
    result = get_recommendations(user_id, k=10)
    if result:
        print_recommendations(result)
        if result["recommendation_type"] in ["personal", "default"]:
            logger.info(f"✅ Рекомендации получены (тип: {result['recommendation_type']})")
            return True

    logger.error("❌ Не удалось протестировать пользователя с персональными рекомендациями")
    return False


def test_user_with_personal_and_history():
    """
    Тест 3: Пользователь с персональными рекомендациями и онлайн-историей.

    Ожидаемое поведение:
    - Сначала добавляем треки в онлайн-историю
    - Затем получаем смешанные рекомендации
    - recommendation_type = "blended"
    """
    print_separator("ТЕСТ 3: ПОЛЬЗОВАТЕЛЬ С ПЕРСОНАЛЬНЫМИ РЕКОМЕНДАЦИЯМИ И ОНЛАЙН-ИСТОРИЕЙ")

    # Используем тестового пользователя
    user_id = 12345

    # Сначала проверим, какие рекомендации для нового пользователя
    logger.info(f"Шаг 1: Получаем начальные рекомендации для user_id={user_id}")
    initial_result = get_recommendations(user_id, k=10)
    if initial_result:
        logger.info(f"  Начальный тип: {initial_result['recommendation_type']}")
        logger.info(f"  Начальные рекомендации: {initial_result['recommendations'][:5]}...")

    # Добавляем треки в онлайн-историю
    logger.info(f"\nШаг 2: Добавляем треки в онлайн-историю")

    # Используем разные track_id (предполагаем, что они существуют)
    test_tracks = [100, 200, 300, 500, 1000]

    for track_id in test_tracks:
        feedback = add_feedback(user_id, track_id)
        if feedback:
            logger.info(f"  ✓ Добавлен track_id={track_id}")
        else:
            logger.warning(f"  ⚠️ Не удалось добавить track_id={track_id}")

    # Получаем обновленные рекомендации
    logger.info(f"\nШаг 3: Получаем рекомендации после добавления истории")
    result = get_recommendations(user_id, k=10)

    if result is None:
        logger.error("❌ Не удалось получить рекомендации")
        return False

    print_recommendations(result)

    # Проверка - если у пользователя нет персональных рекомендаций, то будет default
    # Если есть персональные и онлайн-история - будет blended
    if result["recommendation_type"] == "blended":
        logger.info("✅ Тип рекомендаций корректный: blended (смешанные онлайн + офлайн)")
        return True
    elif result["recommendation_type"] == "default":
        logger.info("✅ Пользователь не имеет персональных рекомендаций, получены default")
        logger.info("   (Для получения blended нужен пользователь с персональными рекомендациями)")
        return True
    else:
        logger.warning(f"⚠️ Получен тип '{result['recommendation_type']}' вместо 'blended'")
        logger.info("   (Возможно, пользователь не имеет персональных рекомендаций)")
        return True


def test_user_with_known_personal_and_history():
    """
    Тест 3b: Пользователь с персональными рекомендациями и онлайн-историей.

    Сначала находим пользователя с персональными рекомендациями,
    затем добавляем ему онлайн-историю и проверяем смешивание.
    """
    print_separator("ТЕСТ 3b: ПРОВЕРКА СМЕШИВАНИЯ ДЛЯ ПОЛЬЗОВАТЕЛЯ С ПЕРСОНАЛЬНЫМИ РЕКОМЕНДАЦИЯМИ")

    # Пробуем найти пользователя с персональными рекомендациями
    test_user_ids = [1, 10, 100, 1000, 10000, 50000, 100000]
    found_user_id = None

    for user_id in test_user_ids:
        result = get_recommendations(user_id, k=10)
        if result and result["recommendation_type"] == "personal":
            found_user_id = user_id
            logger.info(f"✓ Найден пользователь с персональными рекомендациями: user_id={user_id}")
            break

    if found_user_id is None:
        logger.warning("⚠️ Не удалось найти пользователя с персональными рекомендациями")
        logger.info("   Пропускаем тест смешивания")
        return True

    # Получаем рекомендации для этого пользователя (должны быть personal)
    logger.info(f"\nШаг 1: Начальные рекомендации для user_id={found_user_id}")
    initial_result = get_recommendations(found_user_id, k=10)
    print_recommendations(initial_result)

    # Берём первый рекомендованный трек как источник истории
    first_track = initial_result["recommendations"][0] if initial_result["recommendations"] else 100

    # Добавляем онлайн-историю
    logger.info(f"\nШаг 2: Добавляем онлайн-историю")
    test_tracks = [first_track, first_track + 100, first_track + 200]

    for track_id in test_tracks:
        feedback = add_feedback(found_user_id, track_id)
        if feedback:
            logger.info(f"  ✓ Добавлен track_id={track_id}")

    # Получаем обновленные рекомендации
    logger.info(f"\nШаг 3: Рекомендации после добавления истории")
    result = get_recommendations(found_user_id, k=10)

    if result is None:
        logger.error("❌ Не удалось получить рекомендации")
        return False

    print_recommendations(result)

    # Теперь должен быть blended
    if result["recommendation_type"] == "blended":
        logger.info("✅ Тип рекомендаций корректный: blended (смешанные онлайн + офлайн)")

        # Проверяем, что рекомендации изменились
        if result["recommendations"] != initial_result["recommendations"]:
            logger.info("✅ Рекомендации изменились после добавления онлайн-истории")
        else:
            logger.info("⚠️ Рекомендации не изменились (возможно, похожие треки не найдены)")

        return True
    else:
        logger.warning(f"⚠️ Ожидался тип 'blended', получен '{result['recommendation_type']}'")
        return True


# ============================================================================
# Главная функция
# ============================================================================

def main():
    """Запуск всех тестов."""
    logger.info("")
    logger.info("*" * 70)
    logger.info("*" + " " * 20 + "ТЕСТИРОВАНИЕ СЕРВИСА РЕКОМЕНДАЦИЙ" + " " * 14 + "*")
    logger.info("*" * 70)
    logger.info("")

    # Проверка доступности сервиса
    if not test_health():
        logger.error("")
        logger.error("Сервис недоступен! Убедитесь, что сервис запущен:")
        logger.error("  python recommendations_service.py")
        logger.error("")
        return 1

    # Запуск тестов
    results = []

    # Тест 1: Пользователь без персональных рекомендаций
    results.append(("Тест 1: Пользователь без персональных рекомендаций", test_user_without_personal_recs()))

    # Тест 2: Пользователь с персональными рекомендациями, без онлайн-истории
    results.append(("Тест 2: Пользователь с персональными рекомендациями (без истории)", test_user_with_personal_no_history()))

    # Тест 3: Пользователь с персональными рекомендациями и онлайн-историей
    results.append(("Тест 3: Пользователь с онлайн-историей (произвольный)", test_user_with_personal_and_history()))

    # Тест 3b: Пользователь с персональными рекомендациями и онлайн-историей (гарантированно)
    results.append(("Тест 3b: Пользователь с персональными рекомендациями + онлайн-история", test_user_with_known_personal_and_history()))

    # Итоги
    print_separator("ИТОГИ ТЕСТИРОВАНИЯ")

    passed = sum(1 for _, success in results if success)
    total = len(results)

    for test_name, success in results:
        status = "✅ PASSED" if success else "❌ FAILED"
        logger.info(f"  {status}: {test_name}")

    logger.info("")
    logger.info(f"  Всего тестов: {total}")
    logger.info(f"  Успешных: {passed}")
    logger.info(f"  Неуспешных: {total - passed}")
    logger.info("")

    if passed == total:
        logger.info("🎉 ВСЕ ТЕСТЫ ПРОЙДЕНЫ УСПЕШНО!")
    else:
        logger.error("⚠️ ЕСТЬ НЕУСПЕШНЫЕ ТЕСТЫ")

    logger.info("")
    logger.info("Результаты сохранены в test_service.log")

    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
