# services/invoice_service.py
import sentry_sdk
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from fastapi_cache import FastAPICache
from typing import List
import models, schemas
from exceptions import InvoiceNotFoundError


async def create_invoice_service(invoice_data: schemas.InvoiceCreate, owner_id: int, db: AsyncSession):
    db_invoice = models.Invoice(
        **invoice_data.model_dump(exclude={"items"}),
        owner_id=owner_id
    )
    try:
        db.add(db_invoice)
        await db.flush()

        for item in invoice_data.items:
            db_item = models.InvoiceItem(**item.model_dump(), invoice_id=db_invoice.id)
            db.add(db_item)

        await db.commit()
        await db.refresh(db_invoice)
        await FastAPICache.clear()
        return db_invoice
    except Exception as e:
        await db.rollback()
        sentry_sdk.capture_exception(e)
        raise HTTPException(status_code=500, detail="تم فشل حفظ الفاتورة، تم التراجع عن العملية بأمان")


async def create_invoices_bulk_service(invoices_data: List[schemas.InvoiceCreate], owner_id: int, db: AsyncSession):
    db_invoices = []
    try:
        for invoice in invoices_data:
            db_invoice = models.Invoice(
                **invoice.model_dump(exclude={"items"}),
                owner_id=owner_id
            )
            db.add(db_invoice)
            await db.flush()

            for item in invoice.items:
                db_item = models.InvoiceItem(**item.model_dump(), invoice_id=db_invoice.id)
                db.add(db_item)

            db_invoices.append(db_invoice)

        await db.commit()
        for inv in db_invoices:
            await db.refresh(inv)

        await FastAPICache.clear()
        return db_invoices
    except Exception as e:
        await db.rollback()
        sentry_sdk.capture_exception(e)
        raise HTTPException(status_code=500, detail="فشل الحفظ الجماعي، تم التراجع عن جميع الفواتير بأمان")


async def get_user_invoices_service(owner_id: int, skip: int, limit: int, db: AsyncSession):
    query = (
        select(models.Invoice)
        .where(models.Invoice.owner_id == owner_id)
        .options(selectinload(models.Invoice.items))
        .order_by(models.Invoice.date.desc())
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(query)
    return result.scalars().all()


async def update_invoice_deductions_service(invoice_id: int, new_deductions: float, owner_id: int, db: AsyncSession):
    query = select(models.Invoice).where(models.Invoice.id == invoice_id, models.Invoice.owner_id == owner_id)
    result = await db.execute(query)
    invoice = result.scalars().first()

    if not invoice:
        raise InvoiceNotFoundError(invoice_id=invoice_id)

    try:
        invoice.deductions = new_deductions
        invoice.net_total = invoice.total_gross - new_deductions
        await db.commit()
        await db.refresh(invoice)
        await FastAPICache.clear()
        return invoice
    except Exception as e:
        await db.rollback()
        sentry_sdk.capture_exception(e)
        raise HTTPException(status_code=500, detail="فشل التعديل")


async def delete_invoice_service(invoice_id: int, owner_id: int, db: AsyncSession):
    query = select(models.Invoice).where(models.Invoice.id == invoice_id, models.Invoice.owner_id == owner_id)
    result = await db.execute(query)
    invoice = result.scalars().first()

    if not invoice:
        raise InvoiceNotFoundError(invoice_id=invoice_id)

    try:
        await db.delete(invoice)
        await db.commit()
        await FastAPICache.clear()
        return {"message": f"تم حذف الفاتورة رقم {invoice_id} بنجاح"}
    except Exception as e:
        await db.rollback()
        sentry_sdk.capture_exception(e)
        raise HTTPException(status_code=500, detail="فشل الحذف")