from http import HTTPStatus
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, field_validator


class LoggingParams(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    logger: Any
    service: str
    operation: str
    message: Optional[str] = None
    status_code: Optional[HTTPStatus] = None
    user_request: Optional[str] = None

    @field_validator("logger")
    @classmethod
    def validate_logger(cls, value: Any) -> Any:
        if not (hasattr(value, "info") and hasattr(value, "exception")):
            raise ValueError("logger must implement info() and exception()")
        return value
