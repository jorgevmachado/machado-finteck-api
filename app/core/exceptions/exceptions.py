import logging
from http import HTTPStatus

import httpx
from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError

from app.core.logging import log_service_exception

STATUS_MESSAGE_MAP: dict[HTTPStatus, str] = {
    HTTPStatus.UNAUTHORIZED: "Incorrect email or password",
    HTTPStatus.INTERNAL_SERVER_ERROR: "Internal server error",
    HTTPStatus.SERVICE_UNAVAILABLE: "Failed to execute external request",
}


class AppHTTPException(HTTPException):
    def __init__(self, status_code: HTTPStatus, detail: str):
        super().__init__(status_code=status_code, detail=detail)


class UnauthorizedException(AppHTTPException):
    def __init__(self, message: str = STATUS_MESSAGE_MAP[HTTPStatus.UNAUTHORIZED]):
        super().__init__(status_code=HTTPStatus.UNAUTHORIZED, detail=message)


def _resolve_status_code(exception: Exception) -> HTTPStatus:
    if isinstance(exception, HTTPException):
        try:
            return HTTPStatus(exception.status_code)
        except ValueError:
            return HTTPStatus.INTERNAL_SERVER_ERROR

    if isinstance(exception, SQLAlchemyError):
        return HTTPStatus.INTERNAL_SERVER_ERROR

    if isinstance(exception, httpx.HTTPError):
        return HTTPStatus.SERVICE_UNAVAILABLE

    return HTTPStatus.INTERNAL_SERVER_ERROR


def _build_error_message(exception: Exception, status_code: HTTPStatus) -> str:
    if isinstance(exception, HTTPException):
        detail = exception.detail
        if isinstance(detail, str) and detail:
            return detail

    return STATUS_MESSAGE_MAP.get(status_code, status_code.phrase)


def handle_service_exception(
    exception: Exception,
    *,
    logger: logging.Logger,
    service: str,
    operation: str,
    raise_exception: bool = True,
    user_request: str | None = None,
) -> tuple[HTTPStatus, str] | None:

    status_code = _resolve_status_code(exception)
    error_message = _build_error_message(exception, status_code)

    log_service_exception(
        logger=logger,
        error=str(exception),
        service=service,
        operation=operation,
        status_code=status_code,
        message=error_message,
        user_request=user_request,
    )

    if not raise_exception:
        return status_code, error_message

    raise AppHTTPException(
        status_code=status_code,
        detail=error_message,
    ) from exception
