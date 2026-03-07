import httpx
from sqlalchemy import func
from datetime import datetime
from typing import Optional, List, Dict, Any

from app import settings
from app.models import Item, Learner, InteractionLog


async def fetch_items() -> List[Dict[str, Any]]:
    """
    Получает каталог лабораторных работ и задач из Autochecker API.
    Возвращает список словарей с полями lab, task, title и др.
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{settings.AUTOCHECKER_API_URL}/api/items",
            auth=(settings.AUTOCHECKER_EMAIL, settings.AUTOCHECKER_PASSWORD)
        )
        resp.raise_for_status()  # выбросит исключение при HTTP-ошибке
        return resp.json()


async def fetch_logs(since: Optional[datetime] = None) -> List[Dict[str, Any]]:
    """
    Получает логи проверок с поддержкой пагинации.
    Если указан since, возвращает только логи после этой даты.
    Возвращает полный список всех логов.
    """
    logs = []
    offset = 0
    limit = 100  # можно изменить, если API поддерживает другой лимит

    async with httpx.AsyncClient(timeout=30.0) as client:
        while True:
            params = {"limit": limit, "offset": offset}
            if since:
                # преобразуем datetime в строку ISO 8601
                params["since"] = since.isoformat()

            resp = await client.get(
                f"{settings.AUTOCHECKER_API_URL}/api/logs",
                auth=(settings.AUTOCHECKER_EMAIL, settings.AUTOCHECKER_PASSWORD),
                params=params
            )
            resp.raise_for_status()
            data = resp.json()

            logs.extend(data["logs"])

            if not data.get("has_more", False):
                break

            offset += limit

    return logs


def load_items(db, items_data: List[Dict[str, Any]]) -> None:
    """
    Загружает или обновляет записи в таблице items.
    Использует паттерн upsert: если элемент с (lab, task) уже существует,
    обновляет название, иначе создаёт новый.
    """
    for item in items_data:
        lab = item["lab"]
        task = item["task"]          # для лабораторных работ task = None
        title = item["title"]
        type_ = "lab" if task is None else "task"

        # Проверяем, есть ли уже такая запись
        existing = db.query(Item).filter_by(lab=lab, task=task).first()
        if existing:
            # Обновляем название (остальные поля не меняются)
            existing.title = title
        else:
            # Для задачи ищем родительскую лабораторию, чтобы установить parent_id
            parent_id = None
            if type_ == "task":
                parent = db.query(Item).filter_by(lab=lab, task=None).first()
                if parent:
                    parent_id = parent.id

            new_item = Item(
                lab=lab,
                task=task,
                title=title,
                type=type_,          # убедитесь, что в модели поле называется type
                parent_id=parent_id
            )
            db.add(new_item)

    db.commit()


def load_logs(db, logs_data: List[Dict[str, Any]], items_data: List[Dict[str, Any]]) -> int:
    """
    Загружает логи взаимодействий.
    Студенты создаются при необходимости (find‑or‑create по external_id).
    Логи вставляются идемпотентно: если запись с таким external_id уже есть, пропускаем.
    Возвращает количество новых добавленных записей.
    """
    # Строим отображение (lab, task) → item_id для быстрого поиска
    items = db.query(Item).all()
    item_map = {(item.lab, item.task): item.id for item in items}

    new_count = 0

    for log in logs_data:
        # ---- Студент ----
        student_id = log["student_id"]
        learner = db.query(Learner).filter_by(external_id=student_id).first()
        if not learner:
            learner = Learner(
                external_id=student_id,
                group=log.get("group")   # группа приходит из API
            )
            db.add(learner)
            db.flush()   # чтобы получить id
# ---- Лог взаимодействия ----
        external_id = log["id"]
        # Пропускаем, если такой лог уже есть в БД
        if db.query(InteractionLog).filter_by(external_id=external_id).first():
            continue

        # Ищем item_id по паре (lab, task)
        lab = log["lab"]
        task = log["task"]
        item_id = item_map.get((lab, task))
        if not item_id:
            # Такого быть не должно, если items загружены корректно.
            # Можно добавить логирование предупреждения.
            continue

        # Преобразуем строку с датой в объект datetime
        submitted_at_str = log["submitted_at"]
        # API отдаёт даты в формате ISO (например, "2026-02-01T14:30:00Z")
        # Заменяем Z на +00:00 для совместимости с fromisoformat
        try:
            submitted_at = datetime.fromisoformat(submitted_at_str.replace('Z', '+00:00'))
        except ValueError:
            # На случай неожиданного формата можно сохранить как есть,
            # но модель ожидает datetime, поэтому лучше установить None или текущее время.
            # В реальном коде можно добавить логирование и fallback.
            submitted_at = None

        interaction = InteractionLog(
            external_id=external_id,
            learner_id=learner.id,
            item_id=item_id,
            score=log["score"],
            checks_passed=log["passed"],
            checks_total=log["total"],
            submitted_at=submitted_at
        )
        db.add(interaction)
        new_count += 1

    db.commit()
    return new_count


async def sync(db) -> Dict[str, int]:
    """
    Основная функция ETL-пайплайна:
    1. Получает и загружает items.
    2. Определяет время последней синхронизации из БД.
    3. Получает новые логи с момента last_sync.
    4. Загружает логи в БД.
    Возвращает словарь с количеством новых записей и общим количеством.
    """
    # Шаг 1: items
    items_data = await fetch_items()
    load_items(db, items_data)

    # Шаг 2: определяем последнюю синхронизацию
    last_sync = db.query(func.max(InteractionLog.submitted_at)).scalar()

    # Шаг 3: получаем логи (инкрементально, если last_sync не None)
    logs_data = await fetch_logs(since=last_sync)

    # Шаг 4: загружаем логи
    new_records = load_logs(db, logs_data, items_data)

    # Шаг 5: общее количество записей (для отчёта)
    total_records = db.query(InteractionLog).count()

    return {
        "new_records": new_records,
        "total_records": total_records
    }
                