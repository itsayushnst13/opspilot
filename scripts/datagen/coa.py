"""15 synthetic Certificates of Analysis (PDF) with ground-truth verdicts."""
from __future__ import annotations

import random
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .catalog import World
from .docs import DISCLAIMER
from .reference import reference_coa

LABELS = {
    "purity": ("Purity (GC)", "%", "GC-FID"),
    "moisture": ("Moisture (KF)", "%", "Karl Fischer"),
    "color_apha": ("Color (APHA)", "APHA", "APHA scale"),
    "ph": ("pH (10% aq. solution)", "", "pH meter"),
    "residual_solvent_ppm": ("Residual solvents", "ppm", "Headspace GC"),
    "heavy_metals_ppm": ("Heavy metals (as Pb)", "ppm", "ICP-MS"),
}
SENTENCE = {
    "purity": "Purity by gas chromatography was found to be {v} percent.",
    "moisture": "Moisture content by Karl Fischer titration was {v} percent.",
    "color_apha": "Color was measured as {v} APHA.",
    "ph": "The pH was {v}.",
    "residual_solvent_ppm": "Residual solvents were measured at {v} ppm.",
    "heavy_metals_ppm": "Heavy metals as Pb were measured at {v} ppm.",
}


def _fmt(v: float, param: str) -> str:
    if param in ("color_apha", "residual_solvent_ppm", "heavy_metals_ppm"):
        return str(int(round(v)))
    if param == "moisture":
        return f"{v:.2f}"
    if param == "ph":
        return f"{v:.1f}"
    return f"{v:.2f}"


def _spec_text(s: dict) -> str:
    if s["operator"] == ">=":
        return f">= {s['min_value']}"
    if s["operator"] == "<=":
        return f"<= {s['max_value']}"
    return f"{s['min_value']} - {s['max_value']}"


def _pass_value(rng: random.Random, s: dict) -> float:
    lo = float(s["min_value"]) if s["min_value"] != "" else None
    hi = float(s["max_value"]) if s["max_value"] != "" else None
    if s["parameter"] == "purity":
        return round(lo + rng.uniform(0.2, 0.7), 2)
    if s["operator"] == "between":
        return round((lo + hi) / 2 + rng.uniform(-0.2, 0.2), 1)
    return round(hi * rng.uniform(0.35, 0.8), 2 if s["parameter"] == "moisture" else 0)


SCENARIOS = [
    # product, layout, override fn(spec dict)->(param, value) | None, drop param
    ("CHEM-X01", "table", None, None), ("CHEM-X02", "table", None, None), ("CHEM-X03", "kv", None, None),
    ("CHEM-X04", "table", None, None), ("CHEM-X05", "sentence", None, None), ("CHEM-X07", "table", None, None),
    ("CHEM-X09", "table", None, None),
    ("CHEM-X01", "table", ("purity", lambda lo, hi: 98.7), None),
    ("CHEM-X08", "table", ("moisture", lambda lo, hi: round(hi + 0.3, 2)), None),
    ("CHEM-X10", "kv", ("heavy_metals_ppm", lambda lo, hi: round(hi * 2)), None),
    ("CHEM-X13", "table", ("purity", lambda lo, hi: round(lo - 0.6, 2)), None),
    ("CHEM-X14", "sentence", ("residual_solvent_ppm", lambda lo, hi: round(hi + 200)), None),
    ("CHEM-X16", "table", ("purity", lambda lo, hi: round(lo - 0.05, 2)), None),
    ("CHEM-X18", "table", None, "ph"),
    ("CHEM-X06", "kv", ("color_apha", lambda lo, hi: round(hi + 20)), None),
]


def _write_pdf(path: Path, header: list[str], layout: str, rows: list[dict], world: World, code: str,
               batch: str) -> None:
    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(str(path), pagesize=A4, title="Certificate of Analysis")
    story = [Paragraph("CERTIFICATE OF ANALYSIS", styles["Title"])]
    story += [Paragraph(h, styles["BodyText"]) for h in header]
    story.append(Spacer(1, 10))
    if layout == "table":
        data = [["Test", "Result", "Unit", "Specification", "Method"]]
        for r in rows:
            label, unit, method = LABELS[r["parameter"]]
            data.append([label, r["text"], unit or "-", r["spec"], method])
        t = Table(data, hAlign="LEFT")
        t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                               ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey)]))
        story.append(t)
    elif layout == "kv":
        for r in rows:
            label, unit, _ = LABELS[r["parameter"]]
            story.append(Paragraph(f"{label}: {r['text']} {unit}".strip(), styles["BodyText"]))
    else:
        prod = next(p for p in world.products if p["code"] == code)
        text = f"Batch {batch} of {prod['name']} ({code}) was analysed. " + " ".join(
            SENTENCE[r["parameter"]].format(v=r["text"]) for r in rows)
        story.append(Paragraph(text, styles["BodyText"]))
    story += [Spacer(1, 12), Paragraph(DISCLAIMER, styles["Italic"])]
    doc.build(story)


def build_coas(rng: random.Random, world: World, out_dir: Path) -> list[dict]:
    out_dir.mkdir(parents=True, exist_ok=True)
    cases = []
    for idx, (code, layout, override, drop) in enumerate(SCENARIOS, start=1):
        prod = next(p for p in world.products if p["code"] == code)
        specs = [s for s in world.specs if s["product_code"] == code]
        values: dict[str, float] = {}
        for s in specs:
            values[s["parameter"]] = _pass_value(rng, s)
        if override:
            param, fn = override
            s = next(x for x in specs if x["parameter"] == param)
            lo = float(s["min_value"]) if s["min_value"] != "" else None
            hi = float(s["max_value"]) if s["max_value"] != "" else None
            values[param] = float(fn(lo, hi))
        if drop:
            values.pop(drop, None)
        batch = f"B26-{rng.randint(100, 999):04d}"
        rows = [{"parameter": s["parameter"], "text": _fmt(values[s["parameter"]], s["parameter"]),
                 "spec": _spec_text(s)} for s in specs if s["parameter"] in values]
        header = [f"Product: {code} ({prod['name']})", f"Batch No.: {batch}",
                  f"Manufacture date: 2026-09-{rng.randint(1, 28):02d}", "Quantity: 5000 kg",
                  "Issued by: Quality Control (synthetic supplier lab)"]
        name = f"COA-{idx:03d}"
        _write_pdf(out_dir / f"{name}.pdf", header, layout, rows, world, code, batch)
        ref = reference_coa(world, code, {p: values.get(p) for p in [s["parameter"] for s in specs]})
        cases.append({
            "id": name, "file": f"coas/{name}.pdf", "layout": layout,
            "expected": {
                "extracted": {"product_code": code, "batch_no": batch,
                              "params": {p: float(_fmt(v, p)) for p, v in values.items()}},
                "verdict": ref["verdict"],
                "statuses": {r["parameter"]: r["status"] for r in ref["results"]},
            },
        })
    return cases
