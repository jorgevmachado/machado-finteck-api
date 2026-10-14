import logging
import logging.config
import os
import sys
from collections.abc import Mapping
from http import HTTPStatus
from typing import Any

from app.core.context.request_context import request_id_ctx
from app.core.logging.schemas import LoggingParams

DEFAULT_LOG_LEVEL = "INFO"


class HighlightFormatter(logging.Formatter):
    ERROR_STYLE = "\x1b[41;97m"
    WARNING_STYLE = "\x1b[43;97m"
    INFO_STYLE = "\x1b[44;97m"
    RESET_STYLE = "\x1b[0m"
    FIELDS_TO_DISPLAY = {
        "service",
        "operation",
        "status_code",
        "detail",
        "error",
        "method",
        "path",
        "duration",
        "request_id",
        "user_request",
    }

    LEVEL_STYLES = {
        logging.ERROR: ERROR_STYLE,
        logging.WARNING: WARNING_STYLE,
        logging.INFO: INFO_STYLE,
    }

    LOGGER_NAME_MAP = {
        "uvicorn.error": "uvicorn",
        "watchfiles.main": "watchfiles",
    }

    def format(self, record: logging.LogRecord) -> str:
        original_levelname = record.levelname
        original_name = record.name
        record.name = self.LOGGER_NAME_MAP.get(record.name, record.name.split(".")[0])
        style = self.LEVEL_STYLES.get(record.levelno)

        if style:
            record.levelname = f"{style}{original_levelname:^7}{self.RESET_STYLE}"

        try:
            base_format = super().format(record)
            reserved = logging.LogRecord("", 0, "", 0, "", (), None).__dict__.keys()
            extra_fields = {
                k: v
                for k, v in record.__dict__.items()
                if k not in reserved and k in self.FIELDS_TO_DISPLAY
            }
            if extra_fields:
                extra_parts = [f"{k}={v}" for k, v in extra_fields.items()]
                extra_str = " | " + " | ".join(extra_parts)
                return f"{base_format}{extra_str}"
            return base_format
        finally:
            record.levelname = original_levelname
            record.name = original_name


def _extract_base_fields(
    logging_params: "LoggingParams | Mapping[str, Any] | None",
) -> dict[str, Any]:
    if isinstance(logging_params, LoggingParams):
        return {
            "logger": logging_params.logger,
            "service": logging_params.service,
            "operation": logging_params.operation,
            "message": logging_params.message,
            "status_code": logging_params.status_code,
        }
    if isinstance(logging_params, Mapping):
        return dict(logging_params)
    return {}


def build_logger_params(
    logging_params: "LoggingParams | Mapping[str, Any] | None" = None,
    *,
    logger: Any = None,
    service: str | None = None,
    operation: str | None = None,
    message: str | None = None,
    status_code: HTTPStatus | None = None,
    user_request: str | None = None,
    default_status_code: HTTPStatus = HTTPStatus.INTERNAL_SERVER_ERROR,
) -> LoggingParams:
    base = _extract_base_fields(logging_params)

    logger_obj = logger or base.get("logger")
    service_name = service or base.get("service")
    operation_name = operation or base.get("operation")
    final_message = message or base.get("message")
    final_status_code = status_code or base.get("status_code") or default_status_code

    if logger_obj is None or not (
        hasattr(logger_obj, "info") and hasattr(logger_obj, "exception")
    ):
        raise TypeError("logger is required and must implement info() and exception()")

    if not isinstance(service_name, str) or not service_name:
        raise TypeError("service is required")

    if not isinstance(operation_name, str) or not operation_name:
        raise TypeError("operation is required")

    return LoggingParams(
        logger=logger_obj,
        service=service_name,
        operation=operation_name,
        message=final_message or final_status_code.phrase,
        status_code=final_status_code,
        user_request=user_request or "",
    )


def log_service_exception(
    logging_params: "LoggingParams | Mapping[str, Any] | None" = None,
    *,
    logger: Any = None,
    error: str | None = None,
    service: str | None = None,
    operation: str | None = None,
    message: str | None = None,
    status_code: HTTPStatus | None = None,
    user_request: str | None = None,
) -> None:
    params = build_logger_params(
        logging_params,
        logger=logger,
        service=service,
        operation=operation,
        message=message,
        status_code=status_code,
        user_request=user_request,
        default_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
    )

    is_server_error = params.status_code >= HTTPStatus.INTERNAL_SERVER_ERROR
    level = logging.ERROR if is_server_error else logging.WARNING

    params.logger.log(
        level,
        params.message,
        exc_info=is_server_error,
        extra={
            "service": params.service,
            "operation": params.operation,
            "status_code": params.status_code,
            "error": error or params.message,
            "request_id": request_id_ctx.get(),
            "user_request": params.user_request,
        },
    )


def log_service_success(
    logging_params: "LoggingParams | Mapping[str, Any] | None" = None,
    *,
    logger: Any = None,
    service: str | None = None,
    operation: str | None = None,
    message: str | None = None,
    status_code: HTTPStatus | None = None,
    user_request: str | None = None,
) -> None:
    params = build_logger_params(
        logging_params,
        logger=logger,
        service=service,
        operation=operation,
        message=message,
        status_code=status_code,
        user_request=user_request,
        default_status_code=HTTPStatus.OK,
    )

    params.logger.info(
        f"{params.service}.{params.operation}",
        extra={
            "service": params.service,
            "operation": params.operation,
            "status_code": params.status_code,
            "detail": params.message,
            "request_id": request_id_ctx.get(),
            "user_request": params.user_request,
        },
    )


def configure_logging() -> None:
    if getattr(configure_logging, "_configured", False):
        return

    log_level = os.getenv("LOG_LEVEL", DEFAULT_LOG_LEVEL).upper()

    root_logger = logging.getLogger()
    if root_logger.handlers:
        root_logger.handlers.clear()

    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "standard": {
                    "()": HighlightFormatter,
                    "format": "%(levelname)s %(asctime)s:  %(name)s %(message)s ",
                },
            },
            "handlers": {
                "stdout": {
                    "class": "logging.StreamHandler",
                    "stream": sys.stdout,
                    "formatter": "standard",
                },
            },
            "loggers": {
                "app": {
                    "handlers": ["stdout"],
                    "level": log_level,
                    "propagate": False,
                },
                "uvicorn.error": {
                    "handlers": ["stdout"],
                    "level": log_level,
                    "propagate": False,
                },
                "watchfiles": {
                    "handlers": ["stdout"],
                    "level": log_level,
                    "propagate": False,
                },
                "uvicorn.access": {
                    "handlers": [],
                    "level": "CRITICAL",
                    "propagate": False,
                },
            },
            "root": {
                "handlers": ["stdout"],
                "level": log_level,
            },
        }
    )

    setattr(configure_logging, "_configured", True)
