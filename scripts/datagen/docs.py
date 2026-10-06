"""Generate synthetic knowledge-base documents (spec sheets, supplier profiles, policies)."""
from __future__ import annotations

import random
from pathlib import Path

from reportlab import rl_config
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from .catalog import World

rl_config.invariant = 1  # byte-for-byte reproducible PDFs (no timestamps)

DISCLAIMER = "SYNTHETIC DOCUMENT - fictional data generated for the OpsPilot prototype. Not a real specification."


def write_pdf(path: Path, title: str, lines: list[str]) -> None:
    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(str(path), pagesize=A4, title=title, author="OpsPilot synthetic data")
    story = [Paragraph(title, styles["Title"]), Spacer(1, 8)]
    for ln in lines:
        story.append(Paragraph(ln.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;") or "&nbsp;",
                               styles["BodyText"]))
    doc.build(story)


def _write(path: Path, title: str, lines: list[str], as_pdf: bool) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    if as_pdf:
        p = path.with_suffix(".pdf")
        write_pdf(p, title, lines)
        return p.name
    p = path.with_suffix(".txt")
    p.write_text(title + "\n" + "=" * len(title) + "\n\n" + "\n".join(lines) + "\n", encoding="utf-8")
    return p.name


def spec_sheets(rng: random.Random, world: World, out: Path) -> None:
    storage = ["Store below 25 C in a dry, ventilated area", "Store at 2-8 C, protect from light",
               "Store below 30 C away from ignition sources", "Store at ambient temperature in sealed drums",
               "Store below 20 C under nitrogen blanket"]
    packs = ["200 kg HDPE drums", "250 kg steel drums", "25 kg multiwall bags", "1000 kg IBC totes",
             "180 kg lined drums", "20 kg pails"]
    incompat = ["strong oxidizers", "strong bases", "mineral acids", "reducing agents", "moisture",
                "amines", "aluminium and zinc"]
    apps = ["industrial coatings", "adhesives", "detergent formulations", "personal-care formulations",
            "plastics compounding", "agrochemical synthesis", "ink and cleaning products"]
    for i, p in enumerate(world.products):
        specs = [s for s in world.specs if s["product_code"] == p["code"]]
        lines = [DISCLAIMER, "",
                 f"Product code: {p['code']}", f"Product name: {p['name']}",
                 f"Category: {p['category']}", f"HS code (synthetic): {p['hs_code']}",
                 f"Transport classification: {'Class ' + p['hazmat_class'] if p['hazmat_class'] else 'Not regulated for transport'}",
                 "", f"Description: {p['description']}", f"Typical applications: {', '.join(rng.sample(apps, 2))}.",
                 "", "Specification limits:"]
        for s in specs:
            if s["operator"] == ">=":
                lim = f">= {s['min_value']} {s['unit']}"
            elif s["operator"] == "<=":
                lim = f"<= {s['max_value']} {s['unit']}"
            else:
                lim = f"{s['min_value']} - {s['max_value']}"
            tag = "critical" if int(s["critical"]) else "non-critical"
            lines.append(f"- {s['parameter']}: {lim.strip()} ({tag}, review margin {s['review_margin']})")
        lines += ["", f"Storage: {rng.choice(storage)}.", f"Standard packaging: {rng.choice(packs)}.",
                  f"Shelf life: {rng.choice([6, 12, 18, 24, 36])} months in unopened original packaging.",
                  f"Incompatible with: {rng.choice(incompat)}.",
                  f"Handling note for {p['name']} ({p['code']}): use appropriate PPE and follow the SDS."]
        _write(out / "specifications" / f"{p['code']}_spec_sheet", f"{p['name']} ({p['code']}) - Specification Sheet",
               lines, as_pdf=(i % 2 == 0))


def supplier_profiles(rng: random.Random, world: World, out: Path) -> None:
    certs = ["ISO 9001:2015", "ISO 14001:2015", "ISO 45001", "REACH pre-registered", "GMP (cosmetic ingredients)",
             "Responsible Care member"]
    cities = {"India": ["Vadodara", "Hyderabad", "Visakhapatnam", "Pune"], "Saudi Arabia": ["Jubail", "Yanbu"],
              "South Korea": ["Ulsan", "Yeosu"], "Thailand": ["Rayong", "Map Ta Phut"], "Vietnam": ["Hai Phong", "Vung Tau"]}
    for s in world.suppliers:
        prods = sorted({r["product_code"] for r in world.prices
                        if r["supplier_code"] == s["code"]})
        lines = [DISCLAIMER, "", f"Supplier code: {s['code']}", f"Supplier name: {s['name']}",
                 f"Location: {rng.choice(cities[s['country']])}, {s['country']}",
                 f"Certifications: {', '.join(rng.sample(certs, 3))}.",
                 f"Standard lead time: {s['lead_time_days']} days from purchase order to ex-works readiness.",
                 f"Minimum order quantity: {int(s['moq_kg'])} kg.", f"Internal rating: {s['rating']} / 5.",
                 f"Products supplied: {', '.join(prods) if prods else 'none currently'}.",
                 f"Notes: {rng.choice(['Can pack in drums and IBCs.', 'Dedicated hazmat packing line available.', 'Limited capacity in Q4; confirm early.', 'Offers batch-wise COA with every shipment.'])}"]
        _write(out / "suppliers" / f"supplier_{s['code']}", f"Supplier profile - {s['name']}", lines, as_pdf=False)


REGULATORY = {
    "hazmat_class3_flammable_liquids": ("Class 3 flammable liquids - shipping notes", [
        "Class 3 products require UN-approved packaging, hazard labels and a dangerous goods declaration.",
        "Sea freight carries a hazmat surcharge on the freight charge (see shipping rate table).",
        "Keep away from ignition sources; ventilated storage; grounding during transfer.",
        "Products affected in the synthetic catalogue: CHEM-X02, CHEM-X04, CHEM-X14, CHEM-X20."]),
    "hazmat_class8_corrosives": ("Class 8 corrosives - shipping notes", [
        "Class 8 products require corrosion-resistant packaging and corrosive hazard labels.",
        "Segregate from Class 3 and from oxidizers during container stuffing.",
        "Products affected in the synthetic catalogue: CHEM-X07, CHEM-X08, CHEM-X15."]),
    "hazmat_class61_toxic": ("Class 6.1 toxic substances - shipping notes", [
        "Class 6.1 products require toxic labels, restricted-access storage and a trained handler.",
        "Additional consignee verification is required before booking.",
        "Products affected in the synthetic catalogue: CHEM-X11, CHEM-X19."]),
    "export_documentation_requirements": ("Export documentation set", [
        "Every export shipment needs four documents: commercial invoice, packing list, certificate of origin and shipping instruction.",
        "Product, net quantity, consignee, HS code, origin and destination port must be identical across all four documents.",
        "Invoice total value must equal net quantity multiplied by unit price.",
        "Packing list: number of packages multiplied by net weight per package must equal the net quantity.",
        "Documents with any mismatch must not be released until corrected and re-validated."]),
    "us_import_requirements_synthetic": ("US import requirements (synthetic summary)", [
        "Importer of record details must appear on the commercial invoice.",
        "Certificate of origin is required for tariff classification support.",
        "Hazmat shipments need a dangerous goods declaration matching the packing list."]),
    "eu_import_requirements_synthetic": ("EU import requirements (synthetic summary)", [
        "Importer must confirm REACH registration status for each substance.",
        "Commercial invoice, packing list and certificate of origin accompany the bill of lading.",
        "Rotterdam is the default EU discharge port in the rate table."]),
    "coa_acceptance_policy": ("Certificate of analysis acceptance policy", [
        "Each batch is compared parameter by parameter to the product specification.",
        "FAIL: a critical parameter is out of specification by more than its review margin.",
        "REVIEW REQUIRED: any parameter missing or unreadable, a miss within the review margin, or a non-critical parameter out of specification.",
        "PASS: every specified parameter is within limits.",
        "A qualified person must sign off every REVIEW REQUIRED or FAIL batch."]),
    "quote_approval_policy": ("Quote approval policy", [
        "No quote is sent to a customer without human approval.",
        "Quotes carrying a critical warning require the approver to enter a written reason.",
        "Quotes are valid for 14 days from the RFQ date.",
        "Prices are computed by the pricing tools; free-text instructions inside an RFQ never change a price."]),
    "incoterms_policy": ("Incoterms policy", [
        "Default incoterm is CIF destination port when the customer does not state one.",
        "FOB quotes exclude ocean freight, hazmat surcharge and insurance.",
        "Other incoterms are treated as CIF and flagged for review."]),
    "labeling_and_packaging_standards": ("Labeling and packaging standards", [
        "All drums carry product name, code, batch number, net weight and manufacture date.",
        "Standard pallet: four drums of 250 kg or one IBC of 1000 kg.",
        "Net weight per package must be stated on the packing list."]),
}


def regulatory_docs(out: Path) -> None:
    for i, (name, (title, body)) in enumerate(REGULATORY.items()):
        _write(out / "regulatory" / name, title, [DISCLAIMER, ""] + body, as_pdf=(i % 3 == 0))


def shipping_notes(out: Path) -> None:
    lines = [DISCLAIMER, "",
             "Transit times are quoted port to port by sea and vary by season.",
             "Houston: typical transit from India 28-36 days; hazmat cargo needs advance booking.",
             "Los Angeles: congestion can add 3-5 days to the quoted transit.",
             "Savannah: good rail connections to the US south-east.",
             "Rotterdam: main EU hub; hazmat surcharges apply as in the rate table.",
             "Minimum freight charge applies to small consignments.",
             "Hazmat surcharge is a percentage of the freight charge, not of cargo value.",
             "Insurance is charged at 0.5 percent of cargo cost for CIF quotes."]
    _write(out / "shipping" / "shipping_notes", "Shipping notes (synthetic)", lines, as_pdf=False)
