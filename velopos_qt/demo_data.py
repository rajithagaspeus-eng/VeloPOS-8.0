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
        connection.executemany(
            "INSERT INTO products "
            "(barcode, name_en, name_local, selling_price, stock_qty) "
            "VALUES (?, ?, ?, ?, ?)",
            SAMPLES,
        )
    return len(SAMPLES)
