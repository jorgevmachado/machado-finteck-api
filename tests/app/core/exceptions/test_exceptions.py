from http import HTTPStatus
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError

from app.core.exceptions import (
    AppHTTPException,
    UnauthorizedException,
    handle_service_exception,
)


class TestUnauthorizedException:
    @staticmethod
    def test_unauthorized_exception_default_message():
        """Should set unauthorized status code and default message"""
        exception = UnauthorizedException()

        assert exception.status_code == HTTPStatus.UNAUTHORIZED
        assert exception.detail == "Incorrect email or password"


class TestHandleServiceException:
    @staticmethod
    def test_handle_service_exception_returns_context_when_raise_disabled():
        """
        Should return status and message without raising when raise_exception is false
        and log error string
        """
        logger = MagicMock()
        error = HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="Bad request")

        result = handle_service_exception(
            error,
            logger=logger,
            service="auth",
            operation="authenticate",
            raise_exception=False,
            user_request="ash",
        )

        assert result == (HTTPStatus.BAD_REQUEST, "Bad request")
        logger.log.assert_called_once()
        _, log_kwargs = logger.log.call_args
        assert log_kwargs["extra"]["error"] == str(error)
        assert log_kwargs["extra"]["user_request"] == "ash"

    @staticmethod
    def test_handle_service_exception_with_http_exception():
        """Should preserve status code and detail from HTTPException and log error string"""
        logger = MagicMock()
        error = HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="Bad request")

        with pytest.raises(AppHTTPException) as exc_info:
            handle_service_exception(
                error,
                logger=logger,
                service="auth",
                operation="authenticate",
            )

        assert exc_info.value.status_code == HTTPStatus.BAD_REQUEST
        assert exc_info.value.detail == "Bad request"
        logger.log.assert_called_once()
        _, log_kwargs = logger.log.call_args
        assert log_kwargs["extra"]["status_code"] == HTTPStatus.BAD_REQUEST
        assert log_kwargs["extra"]["error"] == str(error)
        assert not log_kwargs["extra"]["user_request"]

    @staticmethod
    def test_handle_service_exception_with_invalid_http_status():
        """
        Should fallback to internal server error when HTTPException status is invalid
        and log error string
        """
        logger = MagicMock()
        error = HTTPException(status_code=999, detail="Invalid")

        with pytest.raises(AppHTTPException) as exc_info:
            handle_service_exception(
                error,
                logger=logger,
                service="auth",
                operation="authenticate",
            )

        _, log_kwargs = logger.log.call_args
        result_status_code = log_kwargs["extra"]["status_code"]
        assert exc_info.value.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
        assert exc_info.value.detail == "Invalid"
        assert result_status_code == HTTPStatus.INTERNAL_SERVER_ERROR
        assert log_kwargs["extra"]["error"] == str(error)
        logger.log.assert_called_once()

    @staticmethod
    def test_handle_service_exception_with_sqlalchemy_error():
        """
        Should return internal server error when SQLAlchemyError occurs
        and log error string
        """
        logger = MagicMock()
        error = SQLAlchemyError("boom")

        with pytest.raises(AppHTTPException) as exc_info:
            handle_service_exception(
                error,
                logger=logger,
                service="auth",
                operation="authenticate",
            )

        assert exc_info.value.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
        assert exc_info.value.detail == "Internal server error"
        logger.log.assert_called_once()
        _, log_kwargs = logger.log.call_args
        assert log_kwargs["extra"]["error"] == str(error)

    @staticmethod
    def test_handle_service_exception_with_unexpected_error():
        """
        Should return internal server error when unexpected error occurs
        and log error string
        """
        logger = MagicMock()
        error = Exception("boom")

        with pytest.raises(AppHTTPException) as exc_info:
            handle_service_exception(
                error,
                logger=logger,
                service="auth",
                operation="authenticate",
            )

        assert exc_info.value.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
        assert exc_info.value.detail == "Internal server error"
        logger.log.assert_called_once()
        _, log_kwargs = logger.log.call_args
        assert log_kwargs["extra"]["error"] == str(error)
