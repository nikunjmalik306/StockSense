"""
StockSense deterministic seed script.

Produces a realistic, reproducible dataset for demo and development.
Safe to run multiple times — checks for admin@stocksense.com first.

Usage:
    python seed/seed.py                        (from backend/)
    docker compose exec backend python seed/seed.py

Highlights for demo:
  - 3 users (ADMIN, MANAGER, STAFF) with known passwords
  - 8 product categories
  - 10 suppliers with varied lead times
  - 40 products with deliberate inventory patterns:
      LOW_STOCK:  5 products  — current_stock < reorder_point
      EXPIRING:   4 products  — batch expiring within 30 days
      EXPIRED:    2 products  — batch already past expiry date
      OVERSTOCK:  4 products  — current_stock > max_stock_level
      HEALTHY:   25 products  — normal range
  - 90 days of deterministic historical STOCK_OUT transactions
  - FIFO demo: Paracetamol 500mg has two batches (A older, B newer)
"""
import asyncio
import os
import random
import sys
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import select

from app.config import get_settings
from app.models.user import Role, User
from app.models.product import Category, Product, Supplier
from app.models.inventory import InventoryBatch, StockTransaction
from app.utils.security import hash_password

settings = get_settings()
RNG = random.Random(42)
TODAY = date.today()
NOW = datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Reference data
# ---------------------------------------------------------------------------

CATEGORIES = [
    ("Antibiotics",   "Antibiotic and antimicrobial medications"),
    ("Analgesics",    "Pain relief medications"),
    ("Vitamins",      "Vitamins and nutritional supplements"),
    ("Antiseptics",   "Wound care and antiseptic products"),
    ("Lab Supplies",  "Laboratory consumables and reagents"),
    ("Cold Chain",    "Temperature-sensitive medications"),
    ("Surgical",      "Surgical supplies and instruments"),
    ("OTC Medicines", "Over-the-counter medications"),
]

SUPPLIERS = [
    # (name, contact, email, phone, lead_time_days)
    ("PharmaCo Ltd",       "James Webb",    "jwebb@pharmaco.com",      "+1-800-555-0101", 5),
    ("MedSupply Global",   "Sarah Chen",    "schen@medsupply.com",     "+1-800-555-0102", 7),
    ("LabSource Inc",      "Ahmed Hassan",  "ahassan@labsource.com",   "+1-800-555-0103", 10),
    ("ColdChain Direct",   "Priya Sharma",  "psharma@coldchain.com",   "+1-800-555-0104", 3),
    ("SurgicalPro",        "Marcus Jones",  "mjones@surgicalpro.com",  "+1-800-555-0105", 14),
    ("GenericMeds Co",     "Lisa Park",     "lpark@genericmeds.com",   "+1-800-555-0106", 7),
    ("BioPharm Inc",       "Wei Zhang",     "wzhang@biopharm.com",     "+1-800-555-0107", 5),
    ("QuickMed Supply",    "Fatima Al-Ali", "falali@quickmed.com",     "+1-800-555-0108", 2),
    ("AlphaVitamins",      "Tom Bradley",   "tbradley@alphavit.com",   "+1-800-555-0109", 6),
    ("MedEquip Direct",    "Claire Ross",   "cross@medequip.com",      "+1-800-555-0110", 8),
]

# Products: (sku, name, cat_i, sup_i, unit, reorder_pt, reorder_qty, max_stock, expiry_alert)
# cat_i and sup_i are 0-based indices into CATEGORIES and SUPPLIERS
PRODUCTS = [
    # ---- ANALGESICS ----
    ("PARA-500",  "Paracetamol 500mg",       1, 0, "tablets",  50, 500, 2000, 90),
    ("IBU-400",   "Ibuprofen 400mg",          1, 0, "tablets",  30, 300, 1500, 60),
    ("ASP-100",   "Aspirin 100mg",            1, 0, "tablets",  40, 400, 1500, 90),
    ("CODEINE",   "Codeine 30mg",             1, 0, "tablets",  20, 200, 800,  60),
    # ---- ANTIBIOTICS ----
    ("AMOX-250",  "Amoxicillin 250mg",        0, 1, "capsules", 30, 300, 1200, 60),
    ("AMOX-500",  "Amoxicillin 500mg",        0, 1, "capsules", 25, 250, 1000, 60),
    ("CEPH-500",  "Cephalexin 500mg",         0, 1, "capsules", 20, 200, 800,  60),
    ("METRO-400", "Metronidazole 400mg",      0, 5, "tablets",  20, 200, 800,  60),
    ("AZITH-250", "Azithromycin 250mg",       0, 1, "tablets",  15, 150, 600,  90),
    ("CLARI-500", "Clarithromycin 500mg",     0, 6, "tablets",  15, 150, 600,  60),
    # ---- VITAMINS ----
    ("VIT-C",     "Vitamin C 500mg",          2, 8, "tablets",  100, 1000, 5000, 180),
    ("VIT-D3",    "Vitamin D3 1000IU",        2, 8, "capsules", 80, 800, 4000, 180),
    ("VIT-B12",   "Vitamin B12 1000mcg",      2, 8, "tablets",  60, 600, 3000, 180),
    ("OMEGA3",    "Omega-3 Fish Oil 1g",      2, 8, "capsules", 50, 500, 2000, 180),
    ("ZINC-20",   "Zinc Sulphate 20mg",       2, 8, "tablets",  50, 500, 2000, 180),
    # ---- ANTISEPTICS ----
    ("BETADINE",  "Betadine Solution 10%",    3, 1, "bottles",  20, 100, 400,  365),
    ("CHLORHEX",  "Chlorhexidine 4%",         3, 1, "bottles",  15, 75,  300,  365),
    ("ISO-70",    "Isopropyl Alcohol 70%",    3, 1, "bottles",  30, 150, 600,  365),
    # ---- LAB SUPPLIES ----
    ("GLOVES-M",  "Nitrile Gloves M",         4, 2, "boxes",    60, 250, 1000, 730),
    ("GLOVES-L",  "Nitrile Gloves L",         4, 2, "boxes",    40, 200, 800,  730),
    ("SYRINGES",  "Disposable Syringes 5ml",  4, 2, "boxes",    30, 150, 600,  365),
    ("GAUZE",     "Sterile Gauze Pads",       4, 2, "packs",    40, 200, 800,  365),
    ("SALINE",    "Normal Saline 0.9%",       4, 1, "bags",     20, 100, 400,  365),
    # ---- COLD CHAIN ----
    ("INSULIN",   "Insulin Regular 100IU",    5, 3, "vials",    10, 50,  200,  30),
    ("VACC-FLU",  "Flu Vaccine 0.5ml",        5, 3, "doses",    20, 100, 300,  45),
    ("HEPARIN",   "Heparin 5000IU",           5, 3, "vials",    15, 60,  250,  60),
    ("DEXTROSE",  "Dextrose 5% 500ml",        5, 3, "bags",     15, 75,  300,  120),
    # ---- SURGICAL ----
    ("SUTURE-0",  "Absorbable Suture 0",      6, 4, "packs",    15, 50,  200,  730),
    ("SUTURE-2",  "Absorbable Suture 2-0",    6, 4, "packs",    15, 50,  200,  730),
    ("SCALPEL",   "Disposable Scalpels",      6, 4, "boxes",    10, 50,  200,  365),
    ("BANDAGE",   "Crepe Bandage 15cm",       6, 4, "rolls",    30, 150, 600,  730),
    # ---- OTC ----
    ("ANTACID",   "Antacid Tablets",          7, 5, "tablets",  80, 800, 3000, 180),
    ("LOPERA",    "Loperamide 2mg",           7, 5, "capsules", 30, 300, 1200, 90),
    ("LORATA",    "Loratadine 10mg",          7, 5, "tablets",  40, 400, 1600, 180),
    ("OMEPRA",    "Omeprazole 20mg",          7, 5, "capsules", 35, 350, 1400, 90),
    ("CETIRI",    "Cetirizine 10mg",          7, 5, "tablets",  30, 300, 1200, 90),
    ("FOLIC",     "Folic Acid 5mg",           2, 8, "tablets",  60, 600, 2400, 180),
    ("CALCIUM",   "Calcium Carbonate 500mg",  2, 8, "tablets",  70, 700, 2800, 180),
    ("GLOVES-S",  "Nitrile Gloves S",         4, 2, "boxes",    50, 200, 800,  730),
    ("HYDRO",     "Hydrogen Peroxide 3%",     3, 1, "bottles",  25, 100, 400,  365),
]


# ---------------------------------------------------------------------------
# Demand patterns — used to create realistic historical transactions
# Pattern: (avg_daily_units, spike_factor, declining: bool, slow_mover: bool)
# ---------------------------------------------------------------------------
DEMAND_PATTERNS = {
    # High movers
    "PARA-500":  (8.0,  1.5,  False, False),
    "IBU-400":   (5.0,  1.3,  False, False),
    "VIT-C":     (12.0, 1.2,  False, False),
    "ANTACID":   (10.0, 1.4,  False, False),
    "GLOVES-M":  (6.0,  1.2,  False, False),
    "SALINE":    (4.0,  1.3,  False, False),
    # Medium movers
    "AMOX-500":  (4.0,  1.4,  False, False),
    "VIT-D3":    (5.0,  1.2,  False, False),
    "OMEPRA":    (3.5,  1.3,  False, False),
    "LORATA":    (3.0,  1.2,  False, False),
    # Declining demand
    "CODEINE":   (2.0,  1.2,  True,  False),
    "ASP-100":   (1.5,  1.1,  True,  False),
    # Slow movers
    "SUTURE-0":  (0.3,  1.5,  False, True),
    "SUTURE-2":  (0.3,  1.5,  False, True),
    "SCALPEL":   (0.5,  1.3,  False, True),
    # Cold chain (high value, low volume)
    "INSULIN":   (1.2,  1.4,  False, False),
    "HEPARIN":   (0.8,  1.3,  False, False),
}


async def run_seed() -> None:
    engine = create_async_engine(settings.database_url, echo=False)
    Session = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async with Session() as db:
        # Idempotency check
        if await db.scalar(select(User).where(User.email == "admin@stocksense.com")):
            print("✓ Seed data already present — skipping.")
            await engine.dispose()
            return

        print("Seeding StockSense database…")

        # -----------------------------------------------------------------------
        # Roles + Users
        # -----------------------------------------------------------------------
        roles: dict[str, Role] = {}
        for rname in ("ADMIN", "MANAGER", "STAFF"):
            r = Role(name=rname, description=f"{rname} role")
            db.add(r); roles[rname] = r
        await db.flush()

        seed_users = [
            ("admin@stocksense.com",   "admin_ss",   "admin123!",   "Admin User",   "ADMIN"),
            ("manager@stocksense.com", "manager_ss", "manager123!", "Jane Manager", "MANAGER"),
            ("staff@stocksense.com",   "staff_ss",   "staff123!",   "Bob Staff",    "STAFF"),
        ]
        user_map: dict[str, User] = {}
        for email, uname, pwd, fname, rname in seed_users:
            u = User(email=email, username=uname, hashed_password=hash_password(pwd),
                     full_name=fname, role_id=roles[rname].id)
            db.add(u); user_map[rname] = u
        await db.flush()
        admin, manager, staff = user_map["ADMIN"], user_map["MANAGER"], user_map["STAFF"]

        # -----------------------------------------------------------------------
        # Categories + Suppliers
        # -----------------------------------------------------------------------
        cat_objs: list[Category] = []
        for cname, cdesc in CATEGORIES:
            c = Category(name=cname, description=cdesc); db.add(c); cat_objs.append(c)
        await db.flush()

        sup_objs: list[Supplier] = []
        for sname, contact, email, phone, lead in SUPPLIERS:
            s = Supplier(name=sname, contact_name=contact, email=email,
                         phone=phone, lead_time_days=lead)
            db.add(s); sup_objs.append(s)
        await db.flush()

        # -----------------------------------------------------------------------
        # Products
        # -----------------------------------------------------------------------
        product_map: dict[str, Product] = {}
        for sku, name, ci, si, unit, rp, rq, ms, ea in PRODUCTS:
            p = Product(sku=sku, name=name, category_id=cat_objs[ci].id,
                        supplier_id=sup_objs[si].id, unit=unit,
                        reorder_point=rp, reorder_quantity=rq,
                        max_stock_level=ms, expiry_alert_days=ea, current_stock=0)
            db.add(p); product_map[sku] = p
        await db.flush()

        # -----------------------------------------------------------------------
        # Helper: create a batch + STOCK_IN transaction
        # -----------------------------------------------------------------------
        async def add_batch(
            product: Product, qty: int, cost: float,
            expiry: date | None, days_ago: int,
            batch_num: str | None = None, user: User = None,
        ) -> InventoryBatch:
            recv = NOW - timedelta(days=days_ago)
            b = InventoryBatch(
                product_id=product.id, batch_number=batch_num,
                quantity=qty, remaining_qty=qty, cost_per_unit=cost,
                expiry_date=expiry, received_at=recv,
            )
            db.add(b); await db.flush()
            t = StockTransaction(
                product_id=product.id, batch_id=b.id,
                transaction_type="STOCK_IN", quantity=qty, unit_cost=cost,
                notes="Initial stock", performed_by=(user or admin).id,
                transaction_at=recv,
            )
            db.add(t); product.current_stock += qty; await db.flush()
            return b

        # -----------------------------------------------------------------------
        # SCENARIO 1: FIFO demo — Paracetamol (PARA-500)
        # Two explicit batches for clear FIFO demonstration
        # Stock-out of 250 → consumes all 200 from A, then 50 from B
        # -----------------------------------------------------------------------
        para = product_map["PARA-500"]
        await add_batch(para, 200, 1.20, TODAY + timedelta(days=180), 60, "PARA-A-2024", manager)
        await add_batch(para, 300, 1.35, TODAY + timedelta(days=270), 30, "PARA-B-2025", manager)

        # -----------------------------------------------------------------------
        # SCENARIO 2: LOW STOCK products (current_stock < reorder_point)
        # -----------------------------------------------------------------------
        # AMOX-500: rp=25, we'll leave only 8 units
        amox = product_map["AMOX-500"]
        await add_batch(amox, 300, 3.50, TODAY + timedelta(days=150), 90)
        t = StockTransaction(
            product_id=amox.id, transaction_type="STOCK_OUT", quantity=-292,
            unit_cost=3.50, notes="Dispensed to wards",
            performed_by=staff.id, transaction_at=NOW - timedelta(days=3),
        )
        db.add(t); amox.current_stock -= 292; await db.flush()

        # METRO-400: rp=20, leave only 5 units
        metro = product_map["METRO-400"]
        await add_batch(metro, 200, 2.80, TODAY + timedelta(days=200), 70)
        t2 = StockTransaction(
            product_id=metro.id, transaction_type="STOCK_OUT", quantity=-195,
            unit_cost=2.80, notes="Dispensed", performed_by=staff.id,
            transaction_at=NOW - timedelta(days=2),
        )
        db.add(t2); metro.current_stock -= 195; await db.flush()

        # CODEINE: rp=20, leave only 12 (declining demand product)
        codeine = product_map["CODEINE"]
        await add_batch(codeine, 200, 4.50, TODAY + timedelta(days=250), 120)
        t3 = StockTransaction(
            product_id=codeine.id, transaction_type="STOCK_OUT", quantity=-188,
            unit_cost=4.50, notes="Dispensed", performed_by=staff.id,
            transaction_at=NOW - timedelta(days=1),
        )
        db.add(t3); codeine.current_stock -= 188; await db.flush()

        # SCALPEL: rp=10, leave 3 units (slow mover, still low)
        scalpel = product_map["SCALPEL"]
        await add_batch(scalpel, 50, 8.00, TODAY + timedelta(days=400), 60)
        t4 = StockTransaction(
            product_id=scalpel.id, transaction_type="STOCK_OUT", quantity=-47,
            unit_cost=8.00, notes="Issued to OR", performed_by=staff.id,
            transaction_at=NOW - timedelta(days=5),
        )
        db.add(t4); scalpel.current_stock -= 47; await db.flush()

        # HEPARIN: rp=15, leave 6 units
        heparin = product_map["HEPARIN"]
        await add_batch(heparin, 60, 25.00, TODAY + timedelta(days=60), 30)
        t5 = StockTransaction(
            product_id=heparin.id, transaction_type="STOCK_OUT", quantity=-54,
            unit_cost=25.00, notes="ICU dispensing", performed_by=staff.id,
            transaction_at=NOW - timedelta(days=2),
        )
        db.add(t5); heparin.current_stock -= 54; await db.flush()

        # -----------------------------------------------------------------------
        # SCENARIO 3: EXPIRING batches (within expiry_alert_days)
        # -----------------------------------------------------------------------
        # INSULIN: expiry_alert_days=30, batch expires in 10 days
        insulin = product_map["INSULIN"]
        await add_batch(insulin, 50, 45.00, TODAY + timedelta(days=10), 40,
                        "INS-CRIT-2025", manager)
        await add_batch(insulin, 80, 47.00, TODAY + timedelta(days=90), 10,
                        "INS-B-2025", manager)

        # FLU VACCINE: expires in 18 days
        vacc = product_map["VACC-FLU"]
        await add_batch(vacc, 100, 12.00, TODAY + timedelta(days=18), 50,
                        "FLU-ALERT-2025", manager)

        # HEPARIN extra batch (expiring soon, separate from low-stock scenario)
        # Already seeded above with 60-day expiry — demonstrates combo risk

        # CEPH-500: expires in 15 days
        ceph = product_map["CEPH-500"]
        await add_batch(ceph, 120, 5.50, TODAY + timedelta(days=15), 45,
                        "CEPH-NEAR-2025", manager)
        await add_batch(ceph, 100, 5.80, TODAY + timedelta(days=200), 10,
                        "CEPH-GOOD-2025", manager)

        # -----------------------------------------------------------------------
        # SCENARIO 4: EXPIRED batches
        # -----------------------------------------------------------------------
        # VACC-FLU gets a second batch that's already expired
        await add_batch(vacc, 30, 11.50, TODAY - timedelta(days=5), 120,
                        "FLU-EXPIRED-2024", manager)

        # ASP-100: one expired batch
        asp = product_map["ASP-100"]
        await add_batch(asp, 400, 0.80, TODAY - timedelta(days=10), 180,
                        "ASP-EXP-2024", manager)
        await add_batch(asp, 200, 0.85, TODAY + timedelta(days=300), 30,
                        "ASP-GOOD-2025", manager)

        # -----------------------------------------------------------------------
        # SCENARIO 5: OVERSTOCKED products (current_stock > max_stock_level)
        # -----------------------------------------------------------------------
        # VIT-C: max=5000, we stock 5500
        vitc = product_map["VIT-C"]
        await add_batch(vitc, 3000, 0.45, TODAY + timedelta(days=400), 20,
                        "VITC-A-2025", admin)
        await add_batch(vitc, 2500, 0.48, TODAY + timedelta(days=450), 5,
                        "VITC-B-2025", admin)

        # ANTACID: max=3000, stock 3200
        antacid = product_map["ANTACID"]
        await add_batch(antacid, 2000, 0.30, TODAY + timedelta(days=500), 25,
                        "ANT-A-2025", admin)
        await add_batch(antacid, 1200, 0.32, TODAY + timedelta(days=480), 10,
                        "ANT-B-2025", admin)

        # LORATA: max=1600, stock 1700
        lorata = product_map["LORATA"]
        await add_batch(lorata, 1000, 1.20, TODAY + timedelta(days=350), 40,
                        "LOR-A-2025", admin)
        await add_batch(lorata, 700, 1.25, TODAY + timedelta(days=380), 15,
                        "LOR-B-2025", admin)

        # GLOVES-M: max=1000, stock 1100
        glovem = product_map["GLOVES-M"]
        await add_batch(glovem, 600, 12.00, TODAY + timedelta(days=700), 50,
                        "GLV-A-2025", admin)
        await add_batch(glovem, 500, 12.50, TODAY + timedelta(days=720), 20,
                        "GLV-B-2025", admin)

        # -----------------------------------------------------------------------
        # SCENARIO 6: HEALTHY products — remaining 25 products
        # -----------------------------------------------------------------------
        healthy_skus = [sku for sku, *_ in PRODUCTS
                        if sku not in product_map or product_map[sku].current_stock == 0]
        # Filter to products not yet seeded
        seeded_skus = {"PARA-500","IBU-400","AMOX-500","METRO-400","CODEINE","SCALPEL",
                       "HEPARIN","INSULIN","VACC-FLU","CEPH-500","ASP-100","VIT-C",
                       "ANTACID","LORATA","GLOVES-M"}

        for sku, name, ci, si, unit, rp, rq, ms, ea in PRODUCTS:
            if sku in seeded_skus:
                continue
            p = product_map[sku]
            # Healthy stock: 2–4× reorder_quantity
            base_qty = RNG.randint(rq * 2, rq * 4)
            cost = round(RNG.uniform(0.50, 30.00), 2)
            expiry_days = RNG.randint(ea + 30, ea * 5)
            days_ago = RNG.randint(10, 90)
            bn = f"{sku}-{RNG.randint(1000,9999)}"
            await add_batch(p, base_qty, cost, TODAY + timedelta(days=expiry_days),
                            days_ago, bn, manager)
            # 50% get a second batch
            if RNG.random() > 0.5:
                qty2 = RNG.randint(rq, rq * 2)
                cost2 = round(cost * RNG.uniform(0.95, 1.10), 2)
                expiry2 = TODAY + timedelta(days=expiry_days + RNG.randint(30, 120))
                bn2 = f"{sku}-{RNG.randint(1000,9999)}"
                await add_batch(p, qty2, cost2, expiry2,
                                max(1, days_ago - RNG.randint(5, 30)), bn2, admin)

        # -----------------------------------------------------------------------
        # SCENARIO 7: IBU-400 — second batch, normal stock
        # -----------------------------------------------------------------------
        ibu = product_map["IBU-400"]
        await add_batch(ibu, 200, 2.10, TODAY + timedelta(days=200), 45, "IBU-A-2024")
        await add_batch(ibu, 150, 2.25, TODAY + timedelta(days=300), 10, "IBU-B-2025")

        # -----------------------------------------------------------------------
        # 90 days of historical STOCK_OUT transactions
        # -----------------------------------------------------------------------
        all_products = list(product_map.values())
        txn_users = [admin, manager, staff]

        for day_offset in range(90, 0, -1):
            txn_dt = NOW - timedelta(days=day_offset)

            # 3–6 transactions per day
            n = RNG.randint(3, 6)
            for _ in range(n):
                p = RNG.choice(all_products)
                if p.current_stock < 5:
                    continue  # skip nearly empty products

                pattern = DEMAND_PATTERNS.get(p.sku)
                if pattern:
                    avg_d, spike_f, declining, slow = pattern
                    # Declining: reduce demand over time
                    if declining:
                        avg_d *= (1 - 0.003 * day_offset)  # ~27% less demand at day 90
                    # Slow mover: only consume 1 in 5 days
                    if slow and RNG.random() > 0.2:
                        continue
                    qty = max(1, int(RNG.gauss(avg_d, avg_d * 0.3)))
                    # Occasional spike
                    if RNG.random() < 0.05:
                        qty = int(qty * spike_f)
                else:
                    qty = RNG.randint(1, max(2, p.current_stock // 10))

                qty = min(qty, p.current_stock)
                if qty < 1:
                    continue

                t = StockTransaction(
                    product_id=p.id,
                    transaction_type="STOCK_OUT",
                    quantity=-qty,
                    unit_cost=round(RNG.uniform(0.50, 30.00), 4),
                    notes=RNG.choice(["Dispensed", "Issued to ward", "Patient order", None]),
                    performed_by=RNG.choice(txn_users).id,
                    transaction_at=txn_dt,
                )
                db.add(t)
                p.current_stock = max(0, p.current_stock - qty)
                await db.flush()

        # -----------------------------------------------------------------------
        # Ensure low-stock products are actually low after history (re-affirm)
        # -----------------------------------------------------------------------
        # Some historical txns may have further depleted these — that's fine.
        # The important thing is they start below reorder_point.

        await db.commit()

        # Summary
        from sqlalchemy import text
        counts = {}
        for tbl in ("roles", "users", "categories", "suppliers",
                    "products", "inventory_batches", "stock_transactions"):
            counts[tbl] = await db.scalar(
                select(func.count()).select_from(text(tbl))
            )

        print("✓ Seed complete.")
        print(f"  Roles:               {counts['roles']}")
        print(f"  Users:               {counts['users']}")
        print(f"  Categories:          {counts['categories']}")
        print(f"  Suppliers:           {counts['suppliers']}")
        print(f"  Products:            {counts['products']}")
        print(f"  Inventory batches:   {counts['inventory_batches']}")
        print(f"  Stock transactions:  {counts['stock_transactions']}")
        print()
        print("Demo accounts:")
        print("  admin@stocksense.com   / admin123!")
        print("  manager@stocksense.com / manager123!")
        print("  staff@stocksense.com   / staff123!")
        print()
        print("FIFO demo: stock-out 250 from PARA-500 (Paracetamol 500mg)")
        print("  → 200 units from PARA-A-2024 (older, exhausted)")
        print("  → 50 units from PARA-B-2025 (newer, partially depleted)")

    await engine.dispose()


if __name__ == "__main__":
    from sqlalchemy import func
    asyncio.run(run_seed())
