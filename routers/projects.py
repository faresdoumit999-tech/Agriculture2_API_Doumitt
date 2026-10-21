"""Projects and seasons."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_current_user, get_owned_project, is_admin
from database import get_db
from exceptions import ConflictError
from models import ExpenseRecord, Invoice, InvoiceItem, Project, User
from routers.reports import invalidate_reports_cache, project_with_summary
from schemas import (
    MessageResponse,
    ProjectCreate,
    ProjectUpdate,
    ProjectWithSummary,
)

router = APIRouter(prefix="/api/projects", tags=["Projects & Seasons"])


@router.post(
    "",
    response_model=ProjectWithSummary,
    status_code=status.HTTP_201_CREATED,
    summary="إنشاء مشروع/موسم جديد",
)
async def create_project(
    payload: ProjectCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProjectWithSummary:
    project = Project(
        owner_id=current_user.id,
        **payload.model_dump(),
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)
    await invalidate_reports_cache()
    return await project_with_summary(db, project)


@router.get(
    "",
    response_model=list[ProjectWithSummary],
    summary="جلب كل مشاريع المستخدم مع ملخص مالي سريع",
)
async def list_projects(
    is_active: bool | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ProjectWithSummary]:
    query = select(Project).order_by(Project.id.desc())
    if not is_admin(current_user):
        query = query.where(Project.owner_id == current_user.id)
    if is_active is not None:
        query = query.where(Project.is_active == is_active)

    projects = (await db.execute(query)).scalars().all()
    return [await project_with_summary(db, project) for project in projects]


@router.get(
    "/{project_id}",
    response_model=ProjectWithSummary,
    summary="تفاصيل مشروع محدد مع ملخصه المالي",
)
async def get_project(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProjectWithSummary:
    project = await get_owned_project(db, project_id, current_user)
    return await project_with_summary(db, project)


@router.put(
    "/{project_id}",
    response_model=ProjectWithSummary,
    summary="تعديل مشروع أو إغلاق الموسم",
)
async def update_project(
    project_id: int,
    payload: ProjectUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProjectWithSummary:
    project = await get_owned_project(db, project_id, current_user)
    data = payload.model_dump(exclude_unset=True)

    for field, value in data.items():
        setattr(project, field, value)

    start = project.season_start_date
    if project.season_end_date and start and project.season_end_date < start:
        raise ConflictError("تاريخ نهاية الموسم يجب أن يكون بعد تاريخ البداية.")

    if payload.is_active is False and "season_end_date" not in data:
        project.season_end_date = date.today()

    await db.commit()
    await db.refresh(project)
    await invalidate_reports_cache()
    return await project_with_summary(db, project)


@router.delete(
    "/{project_id}",
    response_model=MessageResponse,
    summary="حذف مشروع وجميع متعلقاته",
)
async def delete_project(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    project = await get_owned_project(db, project_id, current_user)

    invoice_ids = select(Invoice.id).where(Invoice.project_id == project.id)
    await db.execute(delete(InvoiceItem).where(InvoiceItem.invoice_id.in_(invoice_ids)))
    await db.execute(delete(ExpenseRecord).where(ExpenseRecord.project_id == project.id))
    await db.execute(delete(Invoice).where(Invoice.project_id == project.id))
    await db.execute(delete(Project).where(Project.id == project.id))
    await db.commit()

    await invalidate_reports_cache()
    return MessageResponse(message="تم حذف المشروع وجميع بياناته المرتبطة بنجاح.")
