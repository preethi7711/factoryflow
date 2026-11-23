"""Benchmark master data and opening stock (PROBLEM.md section 5) plus the six demo logins.

Run with:  python -m app.seed
It does nothing if users already exist, so running it twice is safe.
GSTINs here are dummy values in the right format, not real registrations.
"""

from datetime import date, datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.models import AppUser, Role
from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.security import hash_password
from app.core.units import to_base
from app.core.wac import cost_per_unit_paise, receipt_value
from app.inventory.service import OpeningLine, post_opening_stock
from app.masters.models import Bom, BomLine, CompanySettings, Customer, Item, ItemUnit, Supplier

IST = ZoneInfo("Asia/Kolkata")
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
MATERIALS = [
    ("FLOUR", "Flour", "RAW", "g", ("100", "kg", 4200)),
    ("OIL", "Cooking oil", "RAW", "ml", ("30", "l", 14000)),
    ("SPICE-MIX", "Salt and spice mix", "RAW", "g", ("5", "kg", 20000)),
    ("POUCH-200G", "200 g pouch", "PACKAGING", "pcs", ("500", "pcs", 250)),
    ("CARTON", "Carton (holds 20 packets)", "PACKAGING", "pcs", ("30", "pcs", 1500)),
]
BOM_LINES = [  # one batch = 200 packets expected
    ("FLOUR", "40", "kg"),
    ("OIL", "10", "l"),
    ("SPICE-MIX", "1.2", "kg"),
    ("POUCH-200G", "200", "pcs"),
    ("CARTON", "10", "pcs"),
]
BATCH_OUTPUT = Decimal(200)
OPENING_FG_PACKETS = Decimal(50)


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

    items = {
        code: Item(code=code, name=name, kind=kind, base_uom=base, gst_rate_bp=0)
        for code, name, kind, base, _ in MATERIALS
    }
    items["MURUKKU-200G"] = Item(
        code="MURUKKU-200G",
        name="Murukku 200 g",
        kind="FG",
        base_uom="pkt",
        hsn="2106",
        gst_rate_bp=500,  # 5% for this exercise
        sale_price_paise=5000,  # Rs 50 per packet before tax
        pack_size="200 g",
        shelf_life_days=90,  # A16: not given in the brief
        units=[ItemUnit(uom="carton", factor=Decimal(20))],
    )
    db.add_all(items.values())
    db.flush()

    murukku = items["MURUKKU-200G"]
    db.add(
        Bom(
            code="MURUKKU-200G-STD",
            item_id=murukku.id,
            output_qty=BATCH_OUTPUT,
            lines=[
                BomLine(item_id=items[code].id, qty=to_base(qty, uom, items[code].base_uom))
                for code, qty, uom in BOM_LINES
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
            Supplier(
                code="FLOUR-SUPPLIER",
                name="Flour Supplier",
                gstin="33BBBBB2222B1Z2",
                state_code="33",
            ),
        ]
    )
    db.flush()

    # Opening stock, valued at the opening rates.
    rates = {code: (qty, uom, rate) for code, _, _, _, (qty, uom, rate) in MATERIALS}
    lines = [
        OpeningLine(
            item_id=items[code].id,
            qty=to_base(qty, uom, items[code].base_uom),
            value_paise=receipt_value(Decimal(qty), rate),
        )
        for code, (qty, uom, rate) in rates.items()
    ]
    # A5: the 50 opening packets are valued at standard material cost at opening rates.
    standard_batch = sum(
        receipt_value(Decimal(qty), rates[code][2]) for code, qty, uom in BOM_LINES
    )
    standard_per_packet = cost_per_unit_paise(standard_batch, BATCH_OUTPUT)  # 1985 = Rs 19.85
    lines.append(
        OpeningLine(
            item_id=murukku.id,
            qty=OPENING_FG_PACKETS,
            value_paise=int(OPENING_FG_PACKETS) * standard_per_packet,
        )
    )
    post_opening_stock(
        db,
        as_of=OPENING_DATE,
        received_at=datetime.combine(OPENING_DATE, time(0, 0), tzinfo=IST),
        user_id=users["admin"].id,
        lines=lines,
    )


if __name__ == "__main__":
    run()
