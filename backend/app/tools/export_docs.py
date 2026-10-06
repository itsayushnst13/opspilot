"""Generate the four export documents from ONE structured order, so they cannot silently diverge."""
from __future__ import annotations

import datetime as dt
import math
from decimal import Decimal

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Product, ShippingRate
from .pricing_engine import ToolError, dec, get_product

LOADING_PORT = {"India": "Nhava Sheva", "Saudi Arabia": "Jubail", "South Korea": "Busan",
                "Thailand": "Laem Chabang", "Vietnam": "Hai Phong"}


class ExportOrder(BaseModel):
    order_ref: str
    date: dt.date
    seller_name: str = "Seller Trading Co (synthetic)"
    customer_name: str
    customer_address: str = "Address on file (synthetic)"
    product_code: str
    qty_kg: float = Field(gt=0)
    unit_price_per_kg: Decimal
    total_value: Decimal
    currency: str = "USD"
    incoterm: str = "CIF"
    origin_country: str
    destination_port: str
    package_type: str = "250 kg steel drum"
    package_unit_kg: float = Field(default=250.0, gt=0)


def _common(db: Session, o: ExportOrder) -> dict:
    p: Product | None = get_product(db, o.product_code)
    if p is None:
        raise ToolError(f"Unknown product code: {o.product_code}")
    dest_country = db.scalar(select(ShippingRate.dest_country).where(ShippingRate.dest_port == o.destination_port))
    packages = max(1, math.ceil(o.qty_kg / o.package_unit_kg))
    per_pkg = o.package_unit_kg if abs(packages * o.package_unit_kg - o.qty_kg) < 1e-9 else round(o.qty_kg / packages, 3)
    tare = round(o.package_unit_kg * 0.06, 3)
    return {
        "product": {"code": p.code, "name": p.name, "hs_code": p.hs_code},
        "consignee": {"name": o.customer_name, "address": o.customer_address},
        "net_quantity_kg": o.qty_kg, "packages": packages, "per_pkg": per_pkg,
        "gross": round(o.qty_kg + packages * tare, 3), "dest_country": dest_country or "",
        "hazmat": p.hazmat_class,
    }


def generate_invoice(db: Session, o: ExportOrder) -> dict:
    c = _common(db, o)
    return {"doc_type": "commercial_invoice", "invoice_no": f"INV-{o.order_ref}", "date": o.date.isoformat(),
            "seller": {"name": o.seller_name}, "consignee": c["consignee"], "product": c["product"],
            "net_quantity_kg": c["net_quantity_kg"], "unit_price_per_kg": float(o.unit_price_per_kg),
            "total_value": float(o.total_value), "currency": o.currency, "incoterm": o.incoterm,
            "origin_country": o.origin_country, "destination_port": o.destination_port}


def generate_packing_list(db: Session, o: ExportOrder) -> dict:
    c = _common(db, o)
    return {"doc_type": "packing_list", "packing_list_no": f"PL-{o.order_ref}", "invoice_no": f"INV-{o.order_ref}",
            "consignee": c["consignee"], "product": c["product"], "net_quantity_kg": c["net_quantity_kg"],
            "gross_weight_kg": c["gross"], "package_type": o.package_type, "packages_count": c["packages"],
            "net_weight_per_package_kg": c["per_pkg"], "origin_country": o.origin_country,
            "destination_port": o.destination_port}


def generate_certificate_of_origin(db: Session, o: ExportOrder) -> dict:
    c = _common(db, o)
    return {"doc_type": "certificate_of_origin", "coo_no": f"CO-{o.order_ref}", "consignee": c["consignee"],
            "product": c["product"], "net_quantity_kg": c["net_quantity_kg"], "origin_country": o.origin_country,
            "destination_country": c["dest_country"]}


def generate_shipping_instruction(db: Session, o: ExportOrder) -> dict:
    c = _common(db, o)
    return {"doc_type": "shipping_instruction", "si_no": f"SI-{o.order_ref}", "shipper": {"name": o.seller_name},
            "consignee": c["consignee"], "product": c["product"], "net_quantity_kg": c["net_quantity_kg"],
            "gross_weight_kg": c["gross"], "packages_count": c["packages"],
            "port_of_loading": LOADING_PORT.get(o.origin_country, o.origin_country),
            "destination_port": o.destination_port, "incoterm": o.incoterm, "hazmat_class": c["hazmat"]}


GENERATORS = {"commercial_invoice": generate_invoice, "packing_list": generate_packing_list,
              "certificate_of_origin": generate_certificate_of_origin,
              "shipping_instruction": generate_shipping_instruction}


def generate_all(db: Session, o: ExportOrder) -> dict[str, dict]:
    return {k: fn(db, o) for k, fn in GENERATORS.items()}
