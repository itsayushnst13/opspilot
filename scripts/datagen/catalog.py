"""Synthetic catalog: products, specs, suppliers, prices, plants, shipping, margins.

Everything here is fictional. Product names are coined words, not real substances.
"""
from __future__ import annotations

import datetime as dt
import random
from dataclasses import dataclass, field
from decimal import Decimal

RFQ_REFERENCE_DATE = dt.date(2026, 10, 1)

# code, name, category, hazmat class (None = not regulated), HS code (synthetic), short description
PRODUCTS = [
    ("CHEM-X01", "Valtrane Ethyl Ester", "Intermediates", None, "291539", "Colorless liquid ester used as a coating and resin intermediate."),
    ("CHEM-X02", "Norphex Solvent A", "Solvents", "3", "290519", "Fast-evaporating flammable solvent for inks and cleaning formulations."),
    ("CHEM-X03", "Cyrolite Surfactant", "Surfactants", None, "340213", "Mild anionic surfactant for home-care detergents."),
    ("CHEM-X04", "Brevanol Alcohol", "Solvents", "3", "290549", "Medium-chain alcohol solvent for coatings and adhesives."),
    ("CHEM-X05", "Tessamide Additive", "Polymer Additives", None, "292429", "Slip and anti-block additive for polyolefin films."),
    ("CHEM-X06", "Lumivane Antioxidant", "Polymer Additives", None, "293090", "Hindered phenolic antioxidant powder for plastics."),
    ("CHEM-X07", "Orpentil Acid", "Intermediates", "8", "291619", "Corrosive organic acid used in synthesis of specialty esters."),
    ("CHEM-X08", "Kelvane Amine", "Agro Intermediates", "8", "292119", "Corrosive amine intermediate for crop-protection actives."),
    ("CHEM-X09", "Drovex Preservative", "Personal Care Actives", None, "293299", "Broad-spectrum preservative for leave-on cosmetics."),
    ("CHEM-X10", "Marlonate Emollient", "Personal Care Actives", None, "291590", "Light, fast-spreading emollient ester for skin care."),
    ("CHEM-X11", "Quindrel Chloride", "Agro Intermediates", "6.1", "293399", "Toxic chlorinated heterocycle intermediate for agrochemical synthesis."),
    ("CHEM-X12", "Solvitrex Glycol Ether", "Solvents", None, "290944", "Low-odor glycol ether coalescing solvent for water-based paints."),
    ("CHEM-X13", "Haldoran Stabilizer", "Polymer Additives", None, "292690", "Light stabilizer for PVC and engineering plastics."),
    ("CHEM-X14", "Ixaprene Monomer", "Intermediates", "3", "290129", "Flammable specialty monomer for resin manufacture."),
    ("CHEM-X15", "Zenthalic Anhydride", "Intermediates", "8", "291736", "Corrosive cyclic anhydride used in alkyd resins."),
    ("CHEM-X16", "Pelloran Wetting Agent", "Surfactants", None, "340212", "Non-ionic wetting agent for agrochemical and coating formulations."),
    ("CHEM-X17", "Brontex Plasticizer", "Polymer Additives", None, "291736", "Non-phthalate plasticizer for flexible PVC."),
    ("CHEM-X18", "Aulmeric Acid", "Personal Care Actives", None, "291814", "Exfoliating hydroxy acid used in skin-care actives."),
    ("CHEM-X19", "Trevalone Intermediate", "Agro Intermediates", "6.1", "293499", "Toxic nitrogen heterocycle intermediate for herbicide synthesis."),
    ("CHEM-X20", "Corvane Co-solvent", "Solvents", "3", "290919", "Flammable co-solvent for industrial cleaners and degreasers."),
]

BASE_COST_RANGE = {
    "Solvents": (2.2, 4.5),
    "Intermediates": (6.0, 18.0),
    "Surfactants": (3.0, 7.0),
    "Polymer Additives": (8.0, 25.0),
    "Agro Intermediates": (10.0, 30.0),
    "Personal Care Actives": (12.0, 40.0),
}

GRADE_FACTOR = {98.0: 0.92, 98.5: 0.96, 99.0: 1.00, 99.5: 1.15, 99.9: 1.45}
TIERS = [(0.0, 1.00), (1000.0, 0.97), (5000.0, 0.93), (20000.0, 0.88)]

PORTS = [
    ("Houston", "United States"),
    ("Los Angeles", "United States"),
    ("Savannah", "United States"),
    ("Rotterdam", "Netherlands"),
]
ORIGINS = ["India", "Saudi Arabia", "South Korea", "Thailand", "Vietnam"]

SUPPLIER_NAMES = [
    ("S01", "Aravali Fine Chemicals Pvt Ltd", "India"),
    ("S02", "Bharat Synthesis Works", "India"),
    ("S03", "Cauvery Organics Ltd", "India"),
    ("S04", "Deccan Specialty Intermediates", "India"),
    ("S05", "Eastern Ghats Chemicals", "India"),
    ("S06", "Ganga Process Industries", "India"),
    ("S07", "Najd Petrochemical Derivatives", "Saudi Arabia"),
    ("S08", "Red Sea Specialty Co", "Saudi Arabia"),
    ("S09", "Hanbit Fine Materials", "South Korea"),
    ("S10", "Seorak Chemical Solutions", "South Korea"),
    ("S11", "Chao Phraya Chemicals", "Thailand"),
    ("S12", "Andaman Process Materials", "Thailand"),
    ("S13", "Mekong Specialty Chemicals", "Vietnam"),
    ("S14", "Halong Fine Chemicals", "Vietnam"),
    ("S15", "Konkan Coastal Organics", "India"),
]

# Scenario products used by evals (see rfq.py)
P_EXPIRING = "CHEM-X12"   # only price rows expire shortly after the RFQ date
P_EXPIRED = "CHEM-X17"    # all price rows already expired -> no feasible source
P_NO_HIGH_GRADE = "CHEM-X05"
P_HAS_HIGH_GRADE = {"CHEM-X03", "CHEM-X10", "CHEM-X18"}
P_HISTORY_DEVIATES = "CHEM-X09"
P_WITH_HISTORY = [f"CHEM-X{i:02d}" for i in range(1, 11)]


@dataclass
class World:
    products: list[dict] = field(default_factory=list)
    specs: list[dict] = field(default_factory=list)
    suppliers: list[dict] = field(default_factory=list)
    prices: list[dict] = field(default_factory=list)
    plants: list[dict] = field(default_factory=list)
    shipping: list[dict] = field(default_factory=list)
    margins: list[dict] = field(default_factory=list)
    history: list[dict] = field(default_factory=list)


def d4(x: float) -> Decimal:
    return Decimal(str(round(x, 4)))


def build_products(rng: random.Random) -> tuple[list[dict], dict[str, float]]:
    products, base = [], {}
    for i, (code, name, cat, haz, hs, desc) in enumerate(PRODUCTS, start=1):
        lo, hi = BASE_COST_RANGE[cat]
        base[code] = round(rng.uniform(lo, hi), 2)
        products.append({"id": i, "code": code, "name": name, "category": cat,
                         "hazmat_class": haz or "", "hs_code": hs, "description": desc})
    return products, base


def build_specs(rng: random.Random, products: list[dict]) -> list[dict]:
    rows, rid = [], 1

    def add(code, param, op, mn, mx, unit, critical, margin):
        nonlocal rid
        rows.append({"id": rid, "product_code": code, "parameter": param, "operator": op,
                     "min_value": "" if mn is None else mn, "max_value": "" if mx is None else mx,
                     "unit": unit, "critical": int(critical), "review_margin": margin})
        rid += 1

    purity_choices = [98.0, 98.5, 99.0, 99.5]
    for p in products:
        code, cat = p["code"], p["category"]
        purity_min = 99.0 if code == "CHEM-X01" else rng.choice(purity_choices)
        add(code, "purity", ">=", purity_min, None, "%", True, 0.1)
        moisture_max = rng.choice([0.05, 0.10, 0.20, 0.50])
        add(code, "moisture", "<=", None, moisture_max, "%",
            cat in ("Intermediates", "Agro Intermediates"), 0.02)
        add(code, "color_apha", "<=", None, rng.choice([10, 15, 20, 30, 50]), "APHA", False, 5)
        if cat in ("Surfactants", "Personal Care Actives"):
            lo = rng.choice([4.5, 5.0, 5.5, 6.0])
            add(code, "ph", "between", lo, round(lo + rng.choice([1.5, 2.0, 2.5]), 1), "", False, 0.2)
        if cat in ("Intermediates", "Agro Intermediates", "Solvents"):
            add(code, "residual_solvent_ppm", "<=", None, rng.choice([100, 300, 500, 1000]), "ppm",
                cat != "Solvents", 50)
        if cat in ("Personal Care Actives", "Polymer Additives"):
            add(code, "heavy_metals_ppm", "<=", None, rng.choice([5, 10, 20]), "ppm",
                cat == "Personal Care Actives", 1)
    return rows


def build_suppliers(rng: random.Random) -> list[dict]:
    moqs = [500, 500, 1000, 1000, 1000, 2000]
    rows = []
    for i, (code, name, country) in enumerate(SUPPLIER_NAMES, start=1):
        rows.append({"id": i, "code": code, "name": name, "country": country,
                     "lead_time_days": rng.randint(12, 32), "moq_kg": rng.choice(moqs),
                     "rating": round(rng.uniform(3.6, 4.8), 1)})
    return rows


def build_prices(rng: random.Random, products: list[dict], specs: list[dict],
                 suppliers: list[dict], base: dict[str, float]) -> list[dict]:
    purity_min = {s["product_code"]: s["min_value"] for s in specs if s["parameter"] == "purity"}
    sup_factor = {s["code"]: round(rng.uniform(0.92, 1.12), 3) for s in suppliers}
    sup_codes = [s["code"] for s in suppliers]
    rows, rid = [], 1
    for p in products:
        code = p["code"]
        n_sup = rng.choice([2, 3, 3, 4])
        chosen = rng.sample(sup_codes, n_sup)
        base_min = float(purity_min[code])
        for idx, sc in enumerate(chosen):
            grades = [base_min]
            if base_min + 0.5 <= 99.5 and rng.random() < 0.6:
                grades.append(round(base_min + 0.5, 1))
            if base_min - 0.5 >= 98.0 and rng.random() < 0.3:
                grades.append(round(base_min - 0.5, 1))
            if code in P_HAS_HIGH_GRADE and idx == 0:
                grades.append(99.9)
            for g in sorted(set(grades)):
                if g > 99.5 and code not in P_HAS_HIGH_GRADE:
                    continue
                for tier_min, tier_f in TIERS:
                    price = base[code] * GRADE_FACTOR[g] * sup_factor[sc] * tier_f
                    valid = dt.date(2027, 3, 31)
                    if code == P_EXPIRING:
                        valid = dt.date(2026, 10, 12)
                    if code == P_EXPIRED:
                        valid = dt.date(2026, 8, 31)
                    rows.append({"id": rid, "supplier_code": sc, "product_code": code,
                                 "purity_grade": g, "tier_min_kg": tier_min,
                                 "price_per_kg": d4(price), "currency": "USD",
                                 "valid_until": valid.isoformat()})
                    rid += 1
    return rows


def build_plants(rng: random.Random, products: list[dict], specs: list[dict],
                 base: dict[str, float]) -> list[dict]:
    purity_min = {s["product_code"]: s["min_value"] for s in specs if s["parameter"] == "purity"}
    rows, rid = [], 1
    for p in products:
        code = p["code"]
        if code in (P_EXPIRING, P_EXPIRED) or int(code[-2:]) % 5 == 0:
            continue  # not every product is made in-house
        g = float(purity_min[code])
        for grade in sorted({g, min(round(g + 0.5, 1), 99.5)}):
            rows.append({"id": rid, "product_code": code,
                         "plant_name": "Internal Plant IN-1 (synthetic)", "country": "India",
                         "purity_grade": grade,
                         "cost_per_kg": d4(base[code] * 0.80 * GRADE_FACTOR[grade]),
                         "min_batch_kg": 1000, "capacity_kg_month": rng.choice([30000, 60000, 120000]),
                         "lead_time_days": rng.randint(24, 40)})
            rid += 1
    return rows


def build_shipping(rng: random.Random) -> list[dict]:
    rows, rid = [], 1
    transit_base = {"India": 28, "Saudi Arabia": 24, "South Korea": 34, "Thailand": 32, "Vietnam": 33}
    for origin in ORIGINS:
        for port, country in PORTS:
            rows.append({"id": rid, "origin_country": origin, "dest_port": port,
                         "dest_country": country, "mode": "sea",
                         "rate_per_kg": d4(rng.uniform(0.08, 0.22)),
                         "min_charge": Decimal(str(rng.choice([900, 1100, 1300, 1500]))),
                         "transit_days": transit_base[origin] + rng.randint(-4, 8),
                         "hazmat_surcharge_pct": d4(rng.choice([0.20, 0.25, 0.30, 0.35]))})
            rid += 1
    return rows


def build_margins() -> list[dict]:
    cat_adj = {"Solvents": -0.03, "Intermediates": 0.0, "Surfactants": -0.01,
               "Polymer Additives": 0.01, "Agro Intermediates": 0.02, "Personal Care Actives": 0.03}
    tier_margin = [0.24, 0.21, 0.18, 0.15]
    rows, rid = [], 1
    for cat, adj in cat_adj.items():
        for (tier_min, _), m in zip(TIERS, tier_margin):
            for cust, c_adj in (("standard", 0.0), ("strategic", -0.03)):
                rows.append({"id": rid, "category": cat, "qty_tier_min_kg": tier_min,
                             "customer_tier": cust, "margin_pct": d4(m + adj + c_adj)})
                rid += 1
    return rows
