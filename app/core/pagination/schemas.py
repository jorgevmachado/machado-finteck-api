import math
from typing import Optional, Sequence, TypeVar

from fastapi_pagination import LimitOffsetParams
from fastapi_pagination.bases import AbstractPage, AbstractParams
from pydantic import BaseModel

T = TypeVar("T")


class PaginationMeta(BaseModel):
    total: int
    limit: int
    offset: int
    next_page: Optional[int] = None
    previous_page: Optional[int] = None
    total_pages: int
    current_page: int


class CustomLimitOffsetPage(AbstractPage[T]):
    items: list[T]
    meta: PaginationMeta

    __params_type__ = LimitOffsetParams

    @classmethod
    def create(
        cls, items: Sequence[T], params: AbstractParams, *, total: Optional[int] = None
    ) -> "CustomLimitOffsetPage[T]":
        assert isinstance(params, LimitOffsetParams)
        limit = params.limit
        offset = params.offset
        total_list = total or len(items)

        current_page = (offset // limit) + 1 if limit > 0 else 1
        total_pages = math.ceil(total_list / limit) if limit > 0 else 1
        next_page = current_page + 1 if current_page < total_pages else None
        previous_page = current_page - 1 if current_page > 1 else None

        return cls.model_validate(
            {
                "items": list(items),
                "meta": PaginationMeta(
                    total=total_list,
                    limit=limit,
                    offset=offset,
                    next_page=next_page,
                    previous_page=previous_page,
                    total_pages=total_pages,
                    current_page=current_page,
                ),
            }
        )
