"""
Shared Pydantic schemas used across all resources.

PaginatedResponse is generic — it works for any item type:
    PaginatedResponse[CategoryResponse]
    PaginatedResponse[ProductResponse]

QueryParams bundles the pagination / sort / search fields that
every list endpoint accepts so we don't duplicate them everywhere.
"""
from typing import Generic, TypeVar
from pydantic import BaseModel, Field

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    """
    Standard envelope for all paginated list responses.

    Frontend can rely on this shape for every list endpoint.
    """
    items: list[T]
    total: int          # total rows matching the query (before pagination)
    page: int           # current 1-based page number
    page_size: int      # rows per page
    pages: int          # total number of pages

    model_config = {"from_attributes": True}


class MessageResponse(BaseModel):
    """Generic success message — used for DELETE and other mutations."""
    message: str


# Re-export MessageResponse from auth schemas here too so callers
# can import from a single place. (auth.py defines its own copy;
# we keep both to avoid a circular import — they are identical.)
