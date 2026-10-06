"""Reference (business) data. Seeded from data/*.csv|xlsx; the source of truth for deterministic tools."""
from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Optional

from sqlalchemy import Boolean, Date, Float, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.db import Base


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(String(60))
    hazmat_class: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    hs_code: Mapped[str] = mapped_column(String(12))
    description: Mapped[str] = mapped_column(Text, default="")
    source_ref: Mapped[str] = mapped_column(String(120), default="")

    specs: Mapped[list["SpecParameter"]] = relationship(back_populates="product")


class SpecParameter(Base):
    __tablename__ = "spec_parameters"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    parameter: Mapped[str] = mapped_column(String(40))  # canonical name, e.g. purity
    operator: Mapped[str] = mapped_column(String(10))  # >=, <=, between
    min_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    unit: Mapped[str] = mapped_column(String(20), default="")
    critical: Mapped[bool] = mapped_column(Boolean, default=False)
    review_margin: Mapped[float] = mapped_column(Float, default=0.0)
    source_ref: Mapped[str] = mapped_column(String(120), default="")

    product: Mapped[Product] = relationship(back_populates="specs")


class Supplier(Base):
    __tablename__ = "suppliers"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(10), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    country: Mapped[str] = mapped_column(String(60))
    lead_time_days: Mapped[int] = mapped_column(Integer)
    moq_kg: Mapped[float] = mapped_column(Float)
    rating: Mapped[float] = mapped_column(Float, default=0.0)
    source_ref: Mapped[str] = mapped_column(String(120), default="")


class SupplierPrice(Base):
    __tablename__ = "supplier_prices"

    id: Mapped[int] = mapped_column(primary_key=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    purity_grade: Mapped[float] = mapped_column(Float)
    tier_min_kg: Mapped[float] = mapped_column(Float)
    price_per_kg: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    valid_until: Mapped[dt.date] = mapped_column(Date)
    source_ref: Mapped[str] = mapped_column(String(120), default="")

    supplier: Mapped[Supplier] = relationship()
    product: Mapped[Product] = relationship()


class ManufacturingCost(Base):
    __tablename__ = "manufacturing_costs"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    plant_name: Mapped[str] = mapped_column(String(120))
    country: Mapped[str] = mapped_column(String(60))
    purity_grade: Mapped[float] = mapped_column(Float)
    cost_per_kg: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    min_batch_kg: Mapped[float] = mapped_column(Float)
    capacity_kg_month: Mapped[float] = mapped_column(Float)
    lead_time_days: Mapped[int] = mapped_column(Integer)
    source_ref: Mapped[str] = mapped_column(String(120), default="")

    product: Mapped[Product] = relationship()


class ShippingRate(Base):
    __tablename__ = "shipping_rates"

    id: Mapped[int] = mapped_column(primary_key=True)
    origin_country: Mapped[str] = mapped_column(String(60), index=True)
    dest_port: Mapped[str] = mapped_column(String(60), index=True)
    dest_country: Mapped[str] = mapped_column(String(60))
    mode: Mapped[str] = mapped_column(String(10), default="sea")
    rate_per_kg: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    min_charge: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    transit_days: Mapped[int] = mapped_column(Integer)
    hazmat_surcharge_pct: Mapped[Decimal] = mapped_column(Numeric(6, 4))
    source_ref: Mapped[str] = mapped_column(String(120), default="")


class MarginRule(Base):
    __tablename__ = "margin_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    category: Mapped[str] = mapped_column(String(60), index=True)
    qty_tier_min_kg: Mapped[float] = mapped_column(Float)
    customer_tier: Mapped[str] = mapped_column(String(20))
    margin_pct: Mapped[Decimal] = mapped_column(Numeric(6, 4))
    source_ref: Mapped[str] = mapped_column(String(120), default="")


class HistoricalQuote(Base):
    __tablename__ = "historical_quotes"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    qty_kg: Mapped[float] = mapped_column(Float)
    dest_port: Mapped[str] = mapped_column(String(60))
    quoted_price_per_kg: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    outcome: Mapped[str] = mapped_column(String(10))
    quoted_at: Mapped[dt.date] = mapped_column(Date)
    source_ref: Mapped[str] = mapped_column(String(120), default="")

    product: Mapped[Product] = relationship()


__all__ = [
    "Product", "SpecParameter", "Supplier", "SupplierPrice", "ManufacturingCost",
    "ShippingRate", "MarginRule", "HistoricalQuote", "Text",
]
