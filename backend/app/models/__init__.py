"""
Import all models here so SQLAlchemy's metadata and Alembic's
autogenerate can discover every table in one import.

Any new model file must be imported in this module.
"""
from app.models.user import Role, User, RefreshTokenBlacklist  # noqa: F401
from app.models.product import Category, Supplier, Product  # noqa: F401
from app.models.inventory import InventoryBatch, StockTransaction  # noqa: F401
from app.models.purchase_request import PurchaseRequest, PurchaseRequestItem  # noqa: F401
from app.models.notification import Notification  # noqa: F401
from app.models.audit_log import AuditLog  # noqa: F401
