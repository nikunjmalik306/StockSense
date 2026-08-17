"""Initial schema — all tables

Revision ID: 0001
Revises:
Create Date: 2025-01-01 00:00:00.000000

Creates all tables for StockSense:
  - roles, users, refresh_token_blacklist
  - categories, suppliers, products
  - inventory_batches, stock_transactions
  - purchase_requests, purchase_request_items
  - notifications, audit_logs
"""
from typing import Sequence, Union
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # roles
    # ------------------------------------------------------------------
    op.create_table(
        "roles",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(50), nullable=False),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    # ------------------------------------------------------------------
    # users
    # ------------------------------------------------------------------
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("username", sa.String(100), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=True),
        sa.Column("role_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
        sa.UniqueConstraint("username"),
    )
    op.create_index("idx_users_email", "users", ["email"])
    op.create_index("idx_users_role_id", "users", ["role_id"])

    # ------------------------------------------------------------------
    # refresh_token_blacklist
    # ------------------------------------------------------------------
    op.create_table(
        "refresh_token_blacklist",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("jti", sa.String(255), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("jti"),
    )
    op.create_index("idx_rtb_jti", "refresh_token_blacklist", ["jti"])

    # ------------------------------------------------------------------
    # categories
    # ------------------------------------------------------------------
    op.create_table(
        "categories",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    # ------------------------------------------------------------------
    # suppliers
    # ------------------------------------------------------------------
    op.create_table(
        "suppliers",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("contact_name", sa.String(255), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("phone", sa.String(50), nullable=True),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("lead_time_days", sa.Integer(), nullable=False, server_default="7"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.CheckConstraint("lead_time_days > 0", name="chk_supplier_lead_time_positive"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    # ------------------------------------------------------------------
    # products
    # ------------------------------------------------------------------
    op.create_table(
        "products",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sku", sa.String(100), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("supplier_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("unit", sa.String(50), nullable=False, server_default="units"),
        sa.Column("reorder_point", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("reorder_quantity", sa.Integer(), nullable=False, server_default="50"),
        sa.Column("max_stock_level", sa.Integer(), nullable=True),
        sa.Column("expiry_alert_days", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("current_stock", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_risk_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("last_risk_level", sa.String(10), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.CheckConstraint("reorder_point >= 0", name="chk_product_reorder_point_non_negative"),
        sa.CheckConstraint("reorder_quantity > 0", name="chk_product_reorder_quantity_positive"),
        sa.CheckConstraint("current_stock >= 0", name="chk_product_current_stock_non_negative"),
        sa.CheckConstraint(
            "max_stock_level IS NULL OR max_stock_level > reorder_point",
            name="chk_product_max_stock_gt_reorder",
        ),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"]),
        sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("sku"),
    )
    op.create_index("idx_products_category_id", "products", ["category_id"])
    op.create_index("idx_products_supplier_id", "products", ["supplier_id"])
    op.create_index("idx_products_sku", "products", ["sku"])
    op.create_index("idx_products_current_stock", "products", ["current_stock"])

    # ------------------------------------------------------------------
    # inventory_batches
    # ------------------------------------------------------------------
    op.create_table(
        "inventory_batches",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("batch_number", sa.String(100), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("remaining_qty", sa.Integer(), nullable=False),
        sa.Column("cost_per_unit", sa.Numeric(10, 4), nullable=False),
        sa.Column("expiry_date", sa.Date(), nullable=True),
        sa.Column("manufacture_date", sa.Date(), nullable=True),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.CheckConstraint("quantity >= 0", name="chk_batch_quantity_non_negative"),
        sa.CheckConstraint("remaining_qty >= 0", name="chk_batch_remaining_non_negative"),
        sa.CheckConstraint("remaining_qty <= quantity", name="chk_batch_remaining_lte_quantity"),
        sa.CheckConstraint("cost_per_unit >= 0", name="chk_batch_cost_non_negative"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_inventory_batches_product_id", "inventory_batches", ["product_id"])
    op.create_index("idx_inventory_batches_expiry_date", "inventory_batches", ["expiry_date"])

    # ------------------------------------------------------------------
    # stock_transactions
    # ------------------------------------------------------------------
    op.create_table(
        "stock_transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("batch_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("transaction_type", sa.String(20), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_cost", sa.Numeric(10, 4), nullable=True),
        sa.Column("reference_type", sa.String(50), nullable=True),
        sa.Column("reference_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("performed_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "transaction_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "transaction_type IN ('STOCK_IN','STOCK_OUT','ADJUSTMENT','WRITE_OFF','TRANSFER')",
            name="chk_transaction_type_valid",
        ),
        sa.ForeignKeyConstraint(["batch_id"], ["inventory_batches.id"]),
        sa.ForeignKeyConstraint(["performed_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_stock_transactions_product_id", "stock_transactions", ["product_id"])
    op.create_index("idx_stock_transactions_performed_by", "stock_transactions", ["performed_by"])
    op.create_index(
        "idx_stock_transactions_transaction_at",
        "stock_transactions",
        ["transaction_at"],
        postgresql_ops={"transaction_at": "DESC"},
    )
    op.create_index("idx_stock_transactions_type", "stock_transactions", ["transaction_type"])

    # ------------------------------------------------------------------
    # purchase_requests
    # ------------------------------------------------------------------
    op.create_table(
        "purchase_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("request_number", sa.String(50), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="DRAFT"),
        sa.Column("requested_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reviewed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("review_notes", sa.Text(), nullable=True),
        sa.Column("total_value", sa.Numeric(12, 2), nullable=True),
        sa.Column("is_ai_generated", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('DRAFT','PENDING','APPROVED','REJECTED','FULFILLED')",
            name="chk_purchase_request_status_valid",
        ),
        sa.ForeignKeyConstraint(["requested_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("request_number"),
    )
    op.create_index("idx_purchase_requests_status", "purchase_requests", ["status"])
    op.create_index("idx_purchase_requests_requested_by", "purchase_requests", ["requested_by"])

    # ------------------------------------------------------------------
    # purchase_request_items
    # ------------------------------------------------------------------
    op.create_table(
        "purchase_request_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("purchase_request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("quantity_requested", sa.Integer(), nullable=False),
        sa.Column("estimated_unit_cost", sa.Numeric(10, 4), nullable=True),
        sa.Column("justification", sa.Text(), nullable=True),
        sa.Column("urgency_score", sa.Numeric(5, 2), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.CheckConstraint("quantity_requested > 0", name="chk_pri_quantity_positive"),
        sa.ForeignKeyConstraint(
            ["purchase_request_id"],
            ["purchase_requests.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_pri_purchase_request_id", "purchase_request_items", ["purchase_request_id"]
    )
    op.create_index("idx_pri_product_id", "purchase_request_items", ["product_id"])

    # ------------------------------------------------------------------
    # notifications
    # ------------------------------------------------------------------
    op.create_table(
        "notifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("type", sa.String(30), nullable=False),
        sa.Column("severity", sa.String(10), nullable=False, server_default="INFO"),
        sa.Column("reference_type", sa.String(50), nullable=True),
        sa.Column("reference_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "type IN ('LOW_STOCK','EXPIRY','CRITICAL_RISK','PURCHASE_REQUEST_UPDATE','SYSTEM')",
            name="chk_notification_type_valid",
        ),
        sa.CheckConstraint(
            "severity IN ('INFO','WARNING','ERROR','CRITICAL')",
            name="chk_notification_severity_valid",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_notifications_user_id", "notifications", ["user_id"])
    op.create_index("idx_notifications_created_at", "notifications", ["created_at"])

    # ------------------------------------------------------------------
    # audit_logs
    # ------------------------------------------------------------------
    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("resource_type", sa.String(50), nullable=False),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("old_value", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("new_value", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("ip_address", postgresql.INET(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_audit_logs_user_id", "audit_logs", ["user_id"])
    op.create_index("idx_audit_logs_created_at", "audit_logs", ["created_at"])
    op.create_index(
        "idx_audit_logs_resource",
        "audit_logs",
        ["resource_type", "resource_id"],
    )


def downgrade() -> None:
    # Drop in reverse dependency order
    op.drop_table("audit_logs")
    op.drop_table("notifications")
    op.drop_table("purchase_request_items")
    op.drop_table("purchase_requests")
    op.drop_table("stock_transactions")
    op.drop_table("inventory_batches")
    op.drop_table("products")
    op.drop_table("suppliers")
    op.drop_table("categories")
    op.drop_table("refresh_token_blacklist")
    op.drop_table("users")
    op.drop_table("roles")
