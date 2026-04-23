from sqlalchemy import Column, Integer, String, Float, Date, ForeignKey
from sqlalchemy.orm import relationship
from database import Base


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)

    invoices = relationship("Invoice", back_populates="owner")
    expenses = relationship("ExpenseRecord", back_populates="owner")


class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, index=True)
    total_gross = Column(Float, default=0.0)
    deductions = Column(Float, default=0.0)
    net_total = Column(Float, default=0.0)
    owner_id = Column(Integer, ForeignKey("users.id"))

    items = relationship("InvoiceItem", back_populates="invoice", cascade="all, delete-orphan")
    owner = relationship("User", back_populates="invoices")


class InvoiceItem(Base):
    __tablename__ = "invoice_items"

    id = Column(Integer, primary_key=True, index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"))
    crop_name = Column(String, index=True)
    box_count = Column(Integer)
    net_weight = Column(Float)
    unit_price = Column(Float)
    subtotal = Column(Float)

    invoice = relationship("Invoice", back_populates="items")


class ExpenseRecord(Base):
    __tablename__ = "expenses"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, index=True)
    category = Column(String, index=True)
    description = Column(String)
    amount = Column(Float)
    owner_id = Column(Integer, ForeignKey("users.id"))

    owner = relationship("User", back_populates="expenses")