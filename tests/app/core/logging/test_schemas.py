from http import HTTPStatus
from unittest.mock import MagicMock

import pytest

from app.core.logging import LoggingParams


class TestLoggingParams:
    @staticmethod
    def test_accepts_valid_logger():
        """Should create LoggingParams when logger implements info() and exception()"""
        logger = MagicMock()
        params = LoggingParams(logger=logger, service="auth", operation="authenticate")

        assert params.logger is logger
        assert params.service == "auth"
        assert params.operation == "authenticate"

    @staticmethod
    def test_accepts_logger_with_duck_typed_methods():
        """Should accept any object that implements info() and exception()"""

        class CustomLogger:
            def info(self, *args, **kwargs) -> None:
                pass  # comment explaining why the method is empty

            def exception(self, *args, **kwargs) -> None:
                pass  # comment explaining why the method is empty

        params = LoggingParams(
            logger=CustomLogger(),
            service="auth",
            operation="authenticate",
        )

        assert params.logger is not None

    @staticmethod
    def test_raises_when_logger_missing_info_method():
        """Should raise ValueError when logger does not implement info()"""

        class InvalidLogger:
            def exception(self, *args, **kwargs) -> None:
                pass  # comment explaining why the method is empty

        with pytest.raises(
            ValueError, match="logger must implement info\\(\\) and exception\\(\\)"
        ):
            LoggingParams(
                logger=InvalidLogger(),
                service="auth",
                operation="authenticate",
            )

    @staticmethod
    def test_raises_when_logger_missing_exception_method():
        """Should raise ValueError when logger does not implement exception()"""

        class InvalidLogger:
            def info(self, *args, **kwargs) -> None:
                pass  # comment explaining why the method is empty

        with pytest.raises(
            ValueError, match="logger must implement info\\(\\) and exception\\(\\)"
        ):
            LoggingParams(
                logger=InvalidLogger(),
                service="auth",
                operation="authenticate",
            )

    @staticmethod
    def test_raises_when_logger_is_plain_object():
        """Should raise ValueError when logger is an object without required methods"""
        with pytest.raises(
            ValueError, match="logger must implement info\\(\\) and exception\\(\\)"
        ):
            LoggingParams(
                logger=object(),
                service="auth",
                operation="authenticate",
            )

    @staticmethod
    def test_optional_fields_default_to_none():
        """Should set message and status_code to None by default"""
        logger = MagicMock()
        params = LoggingParams(logger=logger, service="auth", operation="authenticate")

        assert params.message is None
        assert params.status_code is None

    @staticmethod
    def test_accepts_status_code_and_message():
        """Should store status_code and message when provided"""
        logger = MagicMock()
        params = LoggingParams(
            logger=logger,
            service="auth",
            operation="authenticate",
            message="User authenticated",
            status_code=HTTPStatus.OK,
        )

        assert params.message == "User authenticated"
        assert params.status_code == HTTPStatus.OK
