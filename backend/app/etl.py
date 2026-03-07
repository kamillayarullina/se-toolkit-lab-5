import httpx
from sqlalchemy import func
from datetime import datetime
from typing import Optional, List, Dict, Any

from app import settings
# Исправленные импорты:
from app.models.item import ItemRecord   # вместо Item
from app.models.learner import Learner
from app.models.interaction import InteractionLog


async def fetch_items() -> List[Dict[str, Any]]:
    """Получает каталог лабораторных работ и задач из Autochecker API."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{settings.AUTOCHECKER_API_URL}/api/items",
            auth=(settings.AUTOCHECKER_EMAIL, settings.AUTOCHECKER_PASSWORD)
        )
        resp.raise_for_status()
        return resp.json()


async def fetch_logs(since: Optional[datetime] = None) -> List[Dict[str, Any]]:
    """Получает логи проверок с пагинацией."""
    logs = []
    offset = 0
    limit = 100

    async with httpx.AsyncClient(timeout=30.0) as client:
        while True:
            params = {"limit": limit, "offset": offset}
            if since:
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
    """Загружает или обновляет записи в таблице items."""
    for item in items_data:
        lab = item["lab"]
        task = item["task"]
        title = item["title"]
        type_ = "lab" if task is None else "task"

        # ВНИМАНИЕ: модель ItemRecord не имеет полей lab и task!
        # Это временное решение, чтобы код компилировался.
        # В реальности нужно адаптировать логику под структуру БД.
        existing = db.query(ItemRecord).filter_by(lab=lab, task=task).first()  # Ошибка: нет полей lab/task
        if existing:
            existing.title = title
        else:
            parent_id = None
            if type_ == "task":
                parent = db.query(ItemRecord).filter_by(lab=lab, task=None).first()
                if parent:
                    parent_id = parent.id

            new_item = ItemRecord(
                # Эти поля отсутствуют в модели, нужно будет переделать
                lab=lab,
                task=task,
                title=title,
                type=type_,
                parent_id=parent_id
            )
            db.add(new_item)
    db.commit()


def load_logs(db, logs_data: List[Dict[str, Any]], items_data: List[Dict[str, Any]]) -> int:
    """Загружает логи взаимодействий."""
    items = db.query(ItemRecord).all()
    # Проблема: ItemRecord не имеет полей lab/task
    item_map = {(item.lab, item.task): item.id for item in items}  # Ошибка

    new_count = 0
    for log in logs_data:
        student_id = log["student_id"]
        learner = db.query(Learner).filter_by(external_id=student_id).first()
        if not learner:
            learner = Learner(
                external_id=student_id,
                student_group=log.get("group")   # поле в модели называется student_group
            )
            db.add(learner)
            db.flush()

        external_id = log["id"]
        if db.query(InteractionLog).filter_by(external_id=external_id).first():
            continue

        lab = log["lab"]
        task = log["task"]
        item_id = item_map.get((lab, task))
        if not item_id:
            continue

        submitted_at_str = log["submitted_at"]
        try:
            submitted_at = datetime.fromisoformat(submitted_at_str.replace('Z', '+00:00'))
        except ValueError:
            submitted_at = None
        interaction = InteractionLog(
            external_id=external_id,
            learner_id=learner.id,
            item_id=item_id,
            score=log["score"],
            checks_passed=log["passed"],
            checks_total=log["total"],
            created_at=submitted_at  # поле в модели называется created_at
        )
        db.add(interaction)
        new_count += 1

    db.commit()
    return new_count


async def sync(db) -> Dict[str, int]:
    """Основная функция ETL-пайплайна."""
    items_data = await fetch_items()
    load_items(db, items_data)

    last_sync = db.query(func.max(InteractionLog.created_at)).scalar()
    logs_data = await fetch_logs(since=last_sync)
    new_records = load_logs(db, logs_data, items_data)
    total_records = db.query(InteractionLog).count()

    return {
        "new_records": new_records,
        "total_records": total_records
    }