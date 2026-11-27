"""Benchmark master data and opening stock (PROBLEM.md section 5) plus the six demo logins.

Run with:  python -m app.seed
It does nothing if users already exist, so running it twice is safe.
GSTINs here are dummy values in the right format, not real registrations.
"""

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.models import AppUser, Role
from app.core.clock import start_of_day
from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.security import hash_password
from app.core.units import to_base
from app.core.wac import cost_per_unit_paise, receipt_value
from app.inventory.service import OpeningLine, post_opening_stock
from app.masters.models import Bom, BomLine, CompanySettings, Customer, Item, ItemUnit, Supplier

OPENING_DATE = date(2026, 10, 31)  # A17: the day before the benchmark month

USERS = [  # spec section 2
    ("salesman_a", "Salesman A", Role.SALESMAN),
    ("salesman_b", "Salesman B", Role.SALESMAN),
    ("admin", "Billing Admin", Role.ADMIN),
    ("production", "Production Supervisor", Role.PRODUCTION),
    ("accountant", "Accountant", Role.AUDITOR),
    ("owner", "Owner", Role.OWNER),
]

# code, name, kind, base unit, opening (qty, unit, rate in paise per that unit)
# --- Benchmark materials (PROBLEM.md §5) — do not change ---
MATERIALS = [
    ("FLOUR", "Flour", "RAW", "g", ("100", "kg", 4200)),
    ("OIL", "Cooking oil", "RAW", "ml", ("30", "l", 14000)),
    ("SPICE-MIX", "Salt and spice mix", "RAW", "g", ("5", "kg", 20000)),
    ("POUCH-200G", "200 g pouch", "PACKAGING", "pcs", ("500", "pcs", 250)),
    ("CARTON", "Carton (holds 20 packets)", "PACKAGING", "pcs", ("30", "pcs", 1500)),
]
# --- Extra raw materials for Mixture and Chips ---
EXTRA_MATERIALS = [
    ("RICE-FLAKES", "Rice flakes (Poha)", "RAW", "g", ("50", "kg", 3000)),
    ("PEANUT", "Peanuts", "RAW", "g", ("20", "kg", 8000)),
    ("BANANA-RAW", "Raw bananas", "RAW", "g", ("30", "kg", 2500)),
]

# Benchmark BOM: Murukku 200 g, one batch = 200 packets
BOM_LINES = [
    ("FLOUR", "40", "kg"),
    ("OIL", "10", "l"),
    ("SPICE-MIX", "1.2", "kg"),
    ("POUCH-200G", "200", "pcs"),
    ("CARTON", "10", "pcs"),
]
BATCH_OUTPUT = Decimal(200)
OPENING_FG_PACKETS = Decimal(50)

# Extra FG items: (code, name, sale_price_paise, opening_qty, bom_code, bom_lines)
EXTRA_FG = [
    (
        "MIXTURE-200G",
        "Mixture 200 g",
        5500,
        Decimal(30),
        "MIXTURE-200G-STD",
        [
            ("RICE-FLAKES", "25", "kg"),
            ("PEANUT", "10", "kg"),
            ("OIL", "8", "l"),
            ("SPICE-MIX", "1.2", "kg"),
            ("POUCH-200G", "200", "pcs"),
            ("CARTON", "10", "pcs"),
        ],
    ),
    (
        "CHIPS-200G",
        "Banana Chips 200 g",
        6000,
        Decimal(20),
        "CHIPS-200G-STD",
        [
            ("BANANA-RAW", "60", "kg"),
            ("OIL", "15", "l"),
            ("SPICE-MIX", "0.5", "kg"),
            ("POUCH-200G", "200", "pcs"),
            ("CARTON", "10", "pcs"),
        ],
    ),
]


def run(db: Session | None = None) -> bool:
    """Seed an empty database. Returns False (and changes nothing) if it was already seeded."""
    own_session = db is None
    session = db or SessionLocal()
    try:
        if session.scalar(select(AppUser.id).limit(1)) is not None:
            print("Seed skipped: the database already has users.")
            return False
        _seed(session)
        session.commit()
        print("Seeded benchmark data and demo logins.")
        return True
    finally:
        if own_session:
            session.close()


def _seed(db: Session) -> None:
    password_hash = hash_password(get_settings().seed_demo_password)
    users = {
        username: AppUser(username=username, full_name=name, role=role, password_hash=password_hash)
        for username, name, role in USERS
    }
    db.add_all(users.values())
    db.add(
        CompanySettings(
            id=1,
            name="FactoryFlow Demo Snacks",
            gstin="33AAAAA0000A1Z5",
            state_code="33",  # Tamil Nadu
            address="Tamil Nadu, India",
            invoice_prefix="FF",
        )
    )

    # Raw and packaging items (benchmark + extra)
    items: dict[str, Item] = {}
    for code, name, kind, base, _ in MATERIALS + EXTRA_MATERIALS:
        items[code] = Item(code=code, name=name, kind=kind, base_uom=base, gst_rate_bp=0)

    # Finished goods
    items["MURUKKU-200G"] = Item(
        code="MURUKKU-200G",
        name="Murukku 200 g",
        kind="FG",
        base_uom="pkt",
        hsn="2106",
        gst_rate_bp=500,
        sale_price_paise=5000,
        pack_size="200 g",
        shelf_life_days=90,
        units=[ItemUnit(uom="carton", factor=Decimal(20))],
    )
    for code, name, sale_price_paise, _opening, _bom_code, _bom_lines in EXTRA_FG:
        items[code] = Item(
            code=code,
            name=name,
            kind="FG",
            base_uom="pkt",
            hsn="2106",
            gst_rate_bp=500,
            sale_price_paise=sale_price_paise,
            pack_size="200 g",
            shelf_life_days=90,
            units=[ItemUnit(uom="carton", factor=Decimal(20))],
        )

    db.add_all(items.values())
    db.flush()

    # Murukku BOM (benchmark)
    db.add(
        Bom(
            code="MURUKKU-200G-STD",
            item_id=items["MURUKKU-200G"].id,
            output_qty=BATCH_OUTPUT,
            lines=[
                BomLine(item_id=items[code].id, qty=to_base(qty, uom, items[code].base_uom))
                for code, qty, uom in BOM_LINES
            ],
        )
    )
    # Extra product BOMs
    for fg_code, _, _, _, bom_code, bom_lines in EXTRA_FG:
        db.add(
            Bom(
                code=bom_code,
                item_id=items[fg_code].id,
                output_qty=BATCH_OUTPUT,
                lines=[
                    BomLine(item_id=items[code].id, qty=to_base(qty, uom, items[code].base_uom))
                    for code, qty, uom in bom_lines
                ],
            )
        )

    db.add_all(
        [  # spec section 2: salesman_a owns Retailer A, salesman_b owns Distributor B
            Customer(
                code="RETAILER-A",
                name="Retailer A",
                gstin="33ABCDE1234F1Z5",
                state_code="33",  # Tamil Nadu: CGST + SGST
                salesman_id=users["salesman_a"].id,
            ),
            Customer(
                code="DISTRIBUTOR-B",
                name="Distributor B",
                gstin="29ABCDE5678G1Z3",
                state_code="29",  # Karnataka: IGST
                salesman_id=users["salesman_b"].id,
            ),
            Customer(
                code="RETAILER-C",
                name="Retailer C",
                gstin="32ABCDE9999H1Z1",
                state_code="32",  # Kerala: IGST
                salesman_id=users["salesman_a"].id,
            ),
            Supplier(
                code="FLOUR-SUPPLIER",
                name="Flour Supplier",
                gstin="33BBBBB2222B1Z2",
                state_code="33",
            ),
            Supplier(
                code="SNACK-INGREDIENTS",
                name="South Indian Ingredients Supplier",
                gstin="33CCCCC3333C1Z3",
                state_code="33",
            ),
        ]
    )
    db.flush()

    # Opening stock: all materials (benchmark + extra) + all FG items
    all_rates = {
        code: (qty, uom, rate) for code, _, _, _, (qty, uom, rate) in MATERIALS + EXTRA_MATERIALS
    }
    opening_lines = [
        OpeningLine(
            item_id=items[code].id,
            qty=to_base(qty, uom, items[code].base_uom),
            value_paise=receipt_value(Decimal(qty), rate),
        )
        for code, (qty, uom, rate) in all_rates.items()
    ]

    # A5: Murukku opening FG at standard material cost
    murukku_std_batch = sum(
        receipt_value(Decimal(qty), all_rates[code][2]) for code, qty, uom in BOM_LINES
    )
    murukku_std_per_pkt = cost_per_unit_paise(murukku_std_batch, BATCH_OUTPUT)  # 1985 = Rs 19.85
    opening_lines.append(
        OpeningLine(
            item_id=items["MURUKKU-200G"].id,
            qty=OPENING_FG_PACKETS,
            value_paise=int(OPENING_FG_PACKETS) * murukku_std_per_pkt,
        )
    )

    # Extra FG opening stock at standard material cost per product
    for fg_code, _, _, opening_qty, _, bom_lines in EXTRA_FG:
        std_batch = sum(
            receipt_value(Decimal(qty), all_rates[code][2]) for code, qty, uom in bom_lines
        )
        std_per_pkt = cost_per_unit_paise(std_batch, BATCH_OUTPUT)
        opening_lines.append(
            OpeningLine(
                item_id=items[fg_code].id,
                qty=opening_qty,
                value_paise=int(opening_qty) * std_per_pkt,
            )
        )

    post_opening_stock(
        db,
        as_of=OPENING_DATE,
        received_at=start_of_day(OPENING_DATE),
        user_id=users["admin"].id,
        lines=opening_lines,
    )


if __name__ == "__main__":
    run()
