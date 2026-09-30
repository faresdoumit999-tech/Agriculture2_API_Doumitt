# routers/invoices.py
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

import models, schemas
from database import get_db
from auth import get_current_user
from services.invoice_service import (
    create_invoice_service,
    create_invoices_bulk_service,
    get_user_invoices_service,
    update_invoice_deductions_service,
    delete_invoice_service
)

router = APIRouter(
    prefix="/api/invoices",
    tags=["Invoices (الفواتير)"]
)


@router.post("", response_model=schemas.InvoiceResponse, status_code=status.HTTP_201_CREATED)
async def add_invoice(
    invoice: schemas.InvoiceCreate,
    current_user: models.User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    return await create_invoice_service(invoice_data=invoice, owner_id=current_user.id, db=db)


@router.post("/bulk", response_model=List[schemas.InvoiceResponse], status_code=status.HTTP_201_CREATED)
async def add_invoices_bulk(
    invoices: List[schemas.InvoiceCreate],
    current_user: models.User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    return await create_invoices_bulk_service(invoices_data=invoices, owner_id=current_user.id, db=db)


@router.get("", response_model=List[schemas.InvoiceResponse])
async def get_invoices(
    skip: int = 0,
    limit: int = 20,
    current_user: models.User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    return await get_user_invoices_service(owner_id=current_user.id, skip=skip, limit=limit, db=db)


@router.patch("/{invoice_id}")
async def update_invoice(
    invoice_id: int,
    new_deductions: float,
    current_user: models.User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    return await update_invoice_deductions_service(
        invoice_id=invoice_id,
        new_deductions=new_deductions,
        owner_id=current_user.id,
        db=db
    )


@router.delete("/{invoice_id}")
async def delete_single_invoice(
    invoice_id: int,
    current_user: models.User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    return await delete_invoice_service(invoice_id=invoice_id, owner_id=current_user.id, db=db)