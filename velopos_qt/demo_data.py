"""Populate *only* a dedicated VeloPOS 8 preview database with sample stock.

This module must never be called by the production application.
"""
import os

SAMPLES = (
    ("DEMO-001", "Sample Rice 1 kg", "සහල් කිලෝ 1", 245.00, 36),
    ("DEMO-002", "Sample Milk Powder", "කිරි පිටි", 890.00, 18),
    ("DEMO-003", "Sample Notebook", "පොත", 180.00, 54),
    ("DEMO-004", "Sample Shampoo", "ஷாம்பு", 650.00, 12),
    ("DEMO-005", "Sample USB Cable", "USB කේබලය", 790.00, 9),
)


def ensure_preview_products(database):
    """Seed five harmless products, but only when preview stock is empty."""
    directory = os.path.normpath(os.path.abspath(database.DATA_DIR))
    if os.path.normcase(os.path.basename(directory)) != os.path.normcase("VeloPOS8PreviewData"):
        raise RuntimeError("Refusing to seed outside dedicated VeloPOS8PreviewData")
    with database.db() as connection:
        count = connection.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    if count:
        return 0
    # Seeding through the original service keeps inventory ledger and audit
    # consistent for *new* preview databases. Do not touch existing rows.
    from velopos import services
    for barcode, name, local_name, price, quantity in SAMPLES:
        services.save_product(
            barcode, name, "v8-preview",
            name_local=local_name, sell=price, stock=quantity,
            reason="V8 preview sample item",
        )
    return len(SAMPLES)


def ensure_preview_directories(database):
    """Insert clearly fictional records into empty preview-only directories."""
    directory = os.path.normpath(os.path.abspath(database.DATA_DIR))
    if os.path.normcase(os.path.basename(directory)) != os.path.normcase("VeloPOS8PreviewData"):
        raise RuntimeError("Refusing to seed outside dedicated VeloPOS8PreviewData")
    with database.db() as connection:
        if not connection.execute("SELECT 1 FROM customers LIMIT 1").fetchone():
            connection.executemany(
                "INSERT INTO customers (name, phone, address, credit_balance) VALUES (?, ?, ?, ?)",
                [
                    ("Demo Customer A", "0000000001", "Sample Address", 0),
                    ("Demo Customer B", "0000000002", "Sample Address", 120.50),
                ],
            )
        if not connection.execute("SELECT 1 FROM suppliers LIMIT 1").fetchone():
            connection.executemany(
                "INSERT INTO suppliers (name, contact, phone, active) VALUES (?, ?, ?, ?)",
                [
                    ("Demo Supplier A", "Sample Contact", "0000000011", 1),
                    ("Demo Supplier B", "Sample Contact", "0000000012", 0),
                ],
            )
