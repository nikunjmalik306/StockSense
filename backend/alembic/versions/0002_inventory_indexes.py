"""Add inventory performance indexes for FIFO and batch queries.

Revision ID: 0002
Revises: 0001
Create Date: 2025-01-02 00:00:00.000000

Adds two indexes required by Block 3 inventory operations:

1. idx_inventory_batches_fifo
   A partial composite index on (product_id, received_at) WHERE remaining_qty > 0.
   Used by the FIFO stock-out query that selects non-empty batches for a product
   ordered by receipt date. The partial predicate keeps the index small — fully
   depleted batches (remaining_qty = 0) are never selected for FIFO depletion.

2. idx_stock_transactions_batch_id
   Simple index on batch_id. Used for batch-level transaction history queries
   (e.g. "show all movements for this batch"). The column exists but was not
   indexed in migration 0001.

Neither index changes table structure or existing data.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Partial composite index: FIFO query needs non-empty batches for a product
    # ordered by received_at. The WHERE predicate excludes depleted batches
    # so the index stays lean over time.
    op.create_index(
        "idx_inventory_batches_fifo",
        "inventory_batches",
        ["product_id", "received_at"],
        postgresql_where=sa.text("remaining_qty > 0"),
    )

    # Simple index on batch_id for transaction history lookups by batch
    op.create_index(
        "idx_stock_transactions_batch_id",
        "stock_transactions",
        ["batch_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_stock_transactions_batch_id", table_name="stock_transactions")
    op.drop_index("idx_inventory_batches_fifo", table_name="inventory_batches")
