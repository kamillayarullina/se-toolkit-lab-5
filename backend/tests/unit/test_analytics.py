"""Router for analytics endpoints.

Each endpoint performs SQL aggregation queries on the interaction data
populated by the ETL pipeline. All endpoints require a lab query
parameter to filter results by lab (e.g., "lab-01").
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, cast, Date, select
from sqlalchemy.orm import selectinload
from sqlmodel.ext.asyncio.session import AsyncSession
from typing import List

from app.database import get_session
from app.models.item import ItemRecord
from app.models.learner import Learner
from app.models.interaction import InteractionLog

router = APIRouter()


@router.get("/scores")
async def get_scores(
    lab: str = Query(..., description="Lab identifier, e.g. 'lab-01'"),
    session: AsyncSession = Depends(get_session),
) -> List[dict]:
    """Score distribution histogram for a given lab."""
    # Находим лабораторию
    lab_title = lab.replace('-', ' ').title()
    stmt = select(ItemRecord).where(
        ItemRecord.type == 'lab',
        ItemRecord.title.contains(lab_title)
    )
    result = await session.execute(stmt)
    lab_item = result.scalar_one_or_none()
    if not lab_item:
        return []

    # Получаем ID задач
    task_stmt = select(ItemRecord.id).where(ItemRecord.parent_id == lab_item.id)
    task_result = await session.execute(task_stmt)
    task_ids = [row[0] for row in task_result.all()]

    # Подзапрос для фильтрации по задачам
    # Строим запрос для каждой корзины
    buckets = [
        ("0-25", (InteractionLog.score >= 0) & (InteractionLog.score <= 25)),
        ("26-50", (InteractionLog.score >= 26) & (InteractionLog.score <= 50)),
        ("51-75", (InteractionLog.score >= 51) & (InteractionLog.score <= 75)),
        ("76-100", (InteractionLog.score >= 76) & (InteractionLog.score <= 100)),
    ]

    result = []
    for bucket_name, condition in buckets:
        count_stmt = select(func.count(InteractionLog.id)).where(
            InteractionLog.item_id.in_(task_ids),
            condition,
            InteractionLog.kind == 'attempt'
        )
        count_result = await session.execute(count_stmt)
        count = count_result.scalar() or 0
        result.append({"bucket": bucket_name, "count": count})

    return result


@router.get("/pass-rates")
async def get_pass_rates(
    lab: str = Query(..., description="Lab identifier, e.g. 'lab-01'"),
    session: AsyncSession = Depends(get_session),
) -> List[dict]:
    """Per-task pass rates for a given lab."""
    lab_title = lab.replace('-', ' ').title()
    lab_stmt = select(ItemRecord).where(
        ItemRecord.type == 'lab',
        ItemRecord.title.contains(lab_title)
    )
    lab_result = await session.execute(lab_stmt)
    lab_item = lab_result.scalar_one_or_none()
    if not lab_item:
        return []

    # Получаем все задачи этой лаборатории
    task_stmt = select(ItemRecord).where(ItemRecord.parent_id == lab_item.id)
    task_result = await session.execute(task_stmt)
    tasks = task_result.scalars().all()

    result = []
    for task in tasks:
        stats_stmt = select(
            func.round(func.avg(InteractionLog.score), 1).label('avg_score'),
            func.count(InteractionLog.id).label('attempts')
        ).where(
            InteractionLog.item_id == task.id,
            InteractionLog.kind == 'attempt'
        )
        stats_result = await session.execute(stats_stmt)
        stats = stats_result.first()
        result.append({
            "task": task.title,
            "avg_score": stats.avg_score if stats.avg_score is not None else 0.0,
            "attempts": stats.attempts
        })

    result.sort(key=lambda x: x["task"])
    return result
@router.get("/timeline")
async def get_timeline(
    lab: str = Query(..., description="Lab identifier, e.g. 'lab-01'"),
    session: AsyncSession = Depends(get_session),
) -> List[dict]:
    """Submissions per day for a given lab."""
    lab_title = lab.replace('-', ' ').title()
    lab_stmt = select(ItemRecord).where(
        ItemRecord.type == 'lab',
        ItemRecord.title.contains(lab_title)
    )
    lab_result = await session.execute(lab_stmt)
    lab_item = lab_result.scalar_one_or_none()
    if not lab_item:
        return []

    task_stmt = select(ItemRecord.id).where(ItemRecord.parent_id == lab_item.id)
    task_result = await session.execute(task_stmt)
    task_ids = [row[0] for row in task_result.all()]

    timeline_stmt = select(
        cast(InteractionLog.created_at, Date).label('date'),
        func.count(InteractionLog.id).label('submissions')
    ).where(
        InteractionLog.item_id.in_(task_ids),
        InteractionLog.kind == 'attempt'
    ).group_by('date').order_by('date')

    timeline_result = await session.execute(timeline_stmt)
    rows = timeline_result.all()
    return [{"date": str(row.date), "submissions": row.submissions} for row in rows]


@router.get("/groups")
async def get_groups(
    lab: str = Query(..., description="Lab identifier, e.g. 'lab-01'"),
    session: AsyncSession = Depends(get_session),
) -> List[dict]:
    """Per-group performance for a given lab."""
    lab_title = lab.replace('-', ' ').title()
    lab_stmt = select(ItemRecord).where(
        ItemRecord.type == 'lab',
        ItemRecord.title.contains(lab_title)
    )
    lab_result = await session.execute(lab_stmt)
    lab_item = lab_result.scalar_one_or_none()
    if not lab_item:
        return []

    task_stmt = select(ItemRecord.id).where(ItemRecord.parent_id == lab_item.id)
    task_result = await session.execute(task_stmt)
    task_ids = [row[0] for row in task_result.all()]

    groups_stmt = select(
        Learner.student_group,
        func.round(func.avg(InteractionLog.score), 1).label('avg_score'),
        func.count(func.distinct(InteractionLog.learner_id)).label('students')
    ).join(
        InteractionLog, InteractionLog.learner_id == Learner.id
    ).where(
        InteractionLog.item_id.in_(task_ids),
        InteractionLog.kind == 'attempt'
    ).group_by(Learner.student_group).order_by(Learner.student_group)

    groups_result = await session.execute(groups_stmt)
    rows = groups_result.all()
    return [
        {
            "group": row.student_group,
            "avg_score": row.avg_score if row.avg_score is not None else 0.0,
            "students": row.students
        }
        for row in rows
    ]   