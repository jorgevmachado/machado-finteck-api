from unittest.mock import patch

import pytest
from fastapi_pagination import LimitOffsetParams
from pydantic import ValidationError

from app.core.pagination import exception_pagination, is_paginate, limit_paginate
from app.core.pagination.pagination import calculate_offset, get_limit_offset_params
from app.shared.schemas import FilterPage


class TestPaginationLimitPaginate:
    @staticmethod
    def test_limit_paginate_no_limit():
        limit = 100
        result = limit_paginate()
        assert result == limit

    @staticmethod
    def test_limit_paginate_with_limit():
        limit = 50
        result = limit_paginate(limit=limit)
        assert result == limit

    @staticmethod
    def test_limit_paginate_with_limit_and_max_limit():
        max_limit = 50
        limit = 60

        result = limit_paginate(limit=limit, max_limit=max_limit)
        assert result == max_limit


class TestPaginationIsPaginate:
    @staticmethod
    def test_is_paginate_no_page_filter():
        result = is_paginate()
        assert not result

    @staticmethod
    def test_is_paginate_with_page_filter():
        result = is_paginate(FilterPage(offset=1, limit=10))
        assert result


class TestPaginationExceptionPagination:
    @staticmethod
    def test_exception_pagination_not_paginate():
        """Should return empty list when no pagination params are provided"""
        result = exception_pagination()
        assert result == []
        assert isinstance(result, list)

    @staticmethod
    def test_exception_pagination_paginate_valid():
        """Should return paginated page when FilterPage is valid"""
        result = exception_pagination(FilterPage(offset=0, limit=10))
        assert hasattr(result, "items")
        assert hasattr(result, "meta")
        assert len(result.items) == 0
        assert result.meta.total == 0

    @staticmethod
    def test_exception_pagination_with_exception_invalid_offset():
        """Should raise ValidationError when offset is negative"""
        with pytest.raises(ValidationError):
            FilterPage(offset=-1, limit=10)

    @staticmethod
    def test_exception_pagination_with_exception_invalid_limit():
        """Should raise ValidationError when limit is zero"""
        with pytest.raises(ValidationError):
            FilterPage(offset=0, limit=0)

    @staticmethod
    def test_exception_pagination_with_high_offset():
        """Should return paginated page with high offset value"""
        limit = 10
        offset = 1000
        result = exception_pagination(FilterPage(offset=offset, limit=limit))

        assert hasattr(result, "items")
        assert isinstance(result.items, list)
        assert len(result.items) == 0
        assert hasattr(result, "meta")
        assert result.meta.total == 0
        assert result.meta.offset == offset
        assert result.meta.limit == limit

    @staticmethod
    def test_exception_pagination_with_max_limit():
        """Should return paginated page with maximum limit value"""
        limit = 100
        result = exception_pagination(FilterPage(offset=0, limit=limit))

        assert hasattr(result, "items")
        assert len(result.items) == 0
        assert hasattr(result, "meta")
        assert result.meta.total == 0
        assert result.meta.limit == limit

    @staticmethod
    def test_exception_pagination_only_offset_no_limit():
        """Should return empty list when only offset is provided"""
        result = exception_pagination(FilterPage(offset=10, limit=None))

        assert result == []
        assert isinstance(result, list)

    @staticmethod
    def test_exception_pagination_only_limit_no_offset():
        """Should return empty list when only limit is provided"""
        result = exception_pagination(FilterPage(offset=None, limit=10))

        assert result == []
        assert isinstance(result, list)

    @staticmethod
    def test_exception_pagination_with_page_and_limit_without_offset():
        """Should build paginated response when page is provided without explicit offset"""
        result = exception_pagination(FilterPage(page=2, offset=None, limit=10))

        assert hasattr(result, "items")
        assert hasattr(result, "meta")
        assert result.meta.limit == 10
        assert result.meta.offset == 10

    @staticmethod
    def test_exception_pagination_catch_exception():
        """Should catch exception and return empty list when LimitOffsetParams raises error"""
        with patch(
            "app.core.pagination.pagination.is_paginate",
            side_effect=Exception("Test error"),
        ):
            result = exception_pagination(FilterPage(offset=0, limit=10))

            # Should return empty list due to exception handling
            assert result == []
            assert isinstance(result, list)

    @staticmethod
    def test_exception_pagination_catch_exception_limit_offset_params():
        """Should catch exception when LimitOffsetParams creation fails"""
        with (
            patch("app.core.pagination.pagination.is_paginate", return_value=True),
            patch(
                "app.core.pagination.pagination.LimitOffsetParams",
                side_effect=ValueError("Invalid params"),
            ),
        ):
            result = exception_pagination(FilterPage(offset=0, limit=10))

            assert result == []
            assert isinstance(result, list)


class TestPaginationCalculateOffset:
    @staticmethod
    def test_calculate_offset_without_page_filter():
        limit = 10
        offset = 0
        page = None
        result = calculate_offset(limit, offset, page)
        assert result == offset

    @staticmethod
    def test_calculate_offset_with_valid_page_filter():
        result_offset = 10
        limit = 10
        offset = 0
        page = 2
        result = calculate_offset(limit, offset, page)
        assert result == result_offset

    @staticmethod
    def test_calculate_offset_with_invalid_page_filter():
        result_offset = 1
        limit = 10
        offset = 0
        page = 0
        result = calculate_offset(limit, offset, page)
        assert result == result_offset

    @staticmethod
    def test_calculate_offset_with_offset_none():
        result_offset = 0
        limit = 10
        offset = None
        page = None
        result = calculate_offset(limit, offset, page)
        assert result == result_offset


class TestPaginationGetLimitOffsetParams:
    @staticmethod
    def test_pagination_get_limit_offset_params_page_filter_is_none():
        result_params = LimitOffsetParams(limit=100, offset=0)
        result = get_limit_offset_params(page_filter=None)
        assert result == result_params

    @staticmethod
    def test_pagination_get_limit_offset_page_params_with_page_filter():
        result_params = LimitOffsetParams(limit=10, offset=10)
        result = get_limit_offset_params(page_filter=FilterPage(offset=10, limit=10))
        assert result == result_params
