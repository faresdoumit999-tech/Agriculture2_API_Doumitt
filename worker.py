"""Celery background worker.

Run with::

    celery -A worker.celery_app worker --loglevel=info
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from celery import Celery
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload

from config import settings
from database import get_async_database_url
from models import ExpenseRecord, Invoice, Project, WarehouseItem

celery_app = Celery(
    "doumitt",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    broker_connection_retry_on_startup=True,
    result_expires=60 * 60 * 24,
)


async def _build_inventory(owner_id: int) -> dict:
    """Aggregate a complete inventory for one tenant in a dedicated engine."""
    url, connect_args = get_async_database_url()
    engine = create_async_engine(url, connect_args=connect_args, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as db:
            projects = (
                await db.execute(
                    select(Project)
                    .where(Project.owner_id == owner_id)
                    .order_by(Project.id)
                )
            ).scalars().all()

            warehouse_items = (
                await db.execute(
                    select(WarehouseItem)
                    .where(WarehouseItem.owner_id == owner_id)
                    .order_by(WarehouseItem.id)
                )
            ).scalars().all()

            expenses = (
                await db.execute(
                    select(ExpenseRecord)
                    .where(ExpenseRecord.owner_id == owner_id)
                    .order_by(ExpenseRecord.date)
                )
            ).scalars().all()

            invoices = (
                await db.execute(
                    select(Invoice)
                    .options(selectinload(Invoice.items))
                    .where(Invoice.owner_id == owner_id)
                    .order_by(Invoice.date)
                )
            ).scalars().all()

            project_rows = []
            for project in projects:
                project_expenses = [row for row in expenses if row.project_id == project.id]
                project_invoices = [row for row in invoices if row.project_id == project.id]

                expenses_usd = sum(row.total_amount_usd for row in project_expenses)
                expenses_syp = sum(row.total_amount_syp for row in project_expenses)
                sales_usd = sum(row.net_total_usd for row in project_invoices)
                sales_syp = sum(row.net_total_syp for row in project_invoices)
                payouts_usd = sum(row.sharecropper_net_payout_usd for row in project_invoices)
                payouts_syp = sum(row.sharecropper_net_payout_syp for row in project_invoices)

                project_rows.append(
                    {
                        "id": project.id,
                        "name": project.name,
                        "greenhouse_count": project.greenhouse_count,
                        "is_active": project.is_active,
                        "expenses_usd": round(expenses_usd, 4),
                        "expenses_syp": round(expenses_syp, 4),
                        "sales_usd": round(sales_usd, 4),
                        "sales_syp": round(sales_syp, 4),
                        "sharecropper_payout_usd": round(payouts_usd, 4),
                        "sharecropper_payout_syp": round(payouts_syp, 4),
                        "net_profit_usd": round(sales_usd - expenses_usd - payouts_usd, 4),
                        "net_profit_syp": round(sales_syp - expenses_syp - payouts_syp, 4),
                        "invoice_count": len(project_invoices),
                        "expense_count": len(project_expenses),
                    }
                )

            return {
                "owner_id": owner_id,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "totals": {
                    "projects": len(project_rows),
                    "warehouse_items": len(warehouse_items),
                    "expenses": len(expenses),
                    "invoices": len(invoices),
                    "expenses_usd": round(sum(row["expenses_usd"] for row in project_rows), 4),
                    "expenses_syp": round(sum(row["expenses_syp"] for row in project_rows), 4),
                    "sales_usd": round(sum(row["sales_usd"] for row in project_rows), 4),
                    "sales_syp": round(sum(row["sales_syp"] for row in project_rows), 4),
                    "net_profit_usd": round(
                        sum(row["net_profit_usd"] for row in project_rows), 4
                    ),
                    "net_profit_syp": round(
                        sum(row["net_profit_syp"] for row in project_rows), 4
                    ),
                },
                "projects": project_rows,
                "warehouse": [
                    {
                        "id": item.id,
                        "product_name": item.product_name,
                        "pharmacy_name": item.pharmacy_name,
                        "purchase_date": item.purchase_date.isoformat(),
                        "initial_quantity": item.initial_quantity,
                        "remaining_quantity": item.remaining_quantity,
                        "unit": item.unit,
                        "currency": item.currency,
                        "total_cost_usd": item.total_cost_usd,
                        "total_cost_syp": item.total_cost_syp,
                    }
                    for item in warehouse_items
                ],
            }
    finally:
        await engine.dispose()


@celery_app.task(name="reports.generate_full_inventory", bind=True)
def generate_full_inventory(self, owner_id: int) -> dict:
    """Generate the complete tenant inventory in the background."""
    return asyncio.run(_build_inventory(owner_id))
