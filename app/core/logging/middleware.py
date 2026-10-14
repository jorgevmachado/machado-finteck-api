import logging
import time
import uuid
from typing import Callable

from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.context.request_context import request_id_ctx

logger = logging.getLogger("app")


async def logging_middleware(request: Request, call_next: Callable):
    request_id = str(uuid.uuid4())
    request_id_ctx.set(request_id)

    start_time = time.time()
    try:
        response = await call_next(request)
    except Exception as e:
        duration = round((time.time() - start_time) * 1000)
        logger.error(
            f"Request {request_id} failed in {duration}ms",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": e.status_code if isinstance(e, JSONResponse) else 500,
                "duration": duration,
            },
        )
        raise e

    duration = round((time.time() - start_time) * 1000)
    logger.info(
        f"Request {request_id} completed in {duration}ms",
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration": duration,
        },
    )

    return response
