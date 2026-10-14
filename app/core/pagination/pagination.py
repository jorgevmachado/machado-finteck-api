import logging
from typing import Annotated, Optional

from fastapi import Query
from fastapi_pagination import LimitOffsetParams

from app.core.exceptions import handle_service_exception
from app.core.pagination.schemas import CustomLimitOffsetPage
from app.shared.schemas import FilterPage

logger = logging.getLogger(__name__)


def limit_paginate(limit: Optional[int] = None, max_limit: int = 100) -> int:
    if not limit:
        return max_limit
    return min(limit, max_limit)


def is_paginate(page_filter: Annotated[FilterPage, Query()] = None) -> bool:
    if not page_filter:
        return False
    has_page = page_filter.page is not None
    has_offset = page_filter.offset is not None or has_page
    has_limit = page_filter.limit is not None
    return has_offset and has_limit


def exception_pagination(page_filter: Annotated[FilterPage, Query()] = None):
    try:
        if is_paginate(page_filter):
            params = get_limit_offset_params(page_filter)
            return CustomLimitOffsetPage.create([], total=0, params=params)
    except Exception as exception:
        handle_service_exception(
            logger=logger,
            exception=exception,
            service="exception_pagination",
            operation="exception_pagination",
            raise_exception=False,
        )
        return []
    return []


def calculate_offset(
    limit: int, offset: Optional[int] = None, page: Optional[int] = None
) -> int:
    if page is not None:
        page_offset = (page - 1) * limit
        if page_offset < 0:
            return 1
        return page_offset
    return offset or 0


def get_limit_offset_params(
    page_filter: Annotated[FilterPage, Query()] = None,
) -> LimitOffsetParams:
    if page_filter is None:
        return LimitOffsetParams(limit=100, offset=0)
    limit = limit_paginate(page_filter.limit)
    offset = calculate_offset(limit, page_filter.offset, page_filter.page)
    return LimitOffsetParams(limit=limit, offset=offset)
