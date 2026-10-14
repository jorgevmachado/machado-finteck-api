import logging
import re
from http import HTTPStatus

import pytest
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.datastructures import Headers

from app.core.context.request_context import request_id_ctx
from app.core.logging.middleware import logging_middleware


def get_logged_record(caplog, levelname, logger_name="app"):
    for record in caplog.records:
        if record.levelname == levelname and record.name == logger_name:
            return record
    return None


def build_request(path: str) -> Request:
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "headers": Headers().raw,
            "client": ("testclient", 50000),
            "server": ("testserver", 80),
        }
    )


@pytest.mark.asyncio
async def test_logging_middleware_success(caplog):
    request = build_request("/ok")

    async def call_next(_: Request):
        return JSONResponse({"msg": "ok"}, status_code=HTTPStatus.OK)

    # Set up app logger to propagate to root so caplog can capture
    app_logger = logging.getLogger("app")
    app_logger.propagate = True

    with caplog.at_level(logging.INFO, logger="app"):
        response = await logging_middleware(request, call_next)
    assert response.status_code == HTTPStatus.OK
    # Print all log records for debugging
    print("Captured log records:")
    for r in caplog.records:
        print(f"LOG: {r.levelname} {r.name} {r.getMessage()}")
    record = get_logged_record(caplog, "INFO")
    assert record is not None
    assert "completed in" in record.getMessage()
    assert record.request_id is not None
    assert record.method == "GET"
    assert record.path == "/ok"
    assert record.status_code == HTTPStatus.OK
    assert isinstance(record.duration, int)


@pytest.mark.asyncio
async def test_logging_middleware_exception(caplog):
    request = build_request("/fail")

    async def call_next(_: Request):
        raise ValueError("fail!")

    # Set up app logger to propagate to root so caplog can capture
    app_logger = logging.getLogger("app")
    app_logger.propagate = True

    with caplog.at_level(logging.ERROR, logger="app"):
        with pytest.raises(ValueError, match="fail!"):
            await logging_middleware(request, call_next)
    print("Captured log records:")
    for r in caplog.records:
        print(f"LOG: {r.levelname} {r.name} {r.getMessage()}")
    record = get_logged_record(caplog, "ERROR")
    assert record is not None
    assert "failed in" in record.getMessage()
    assert record.request_id is not None
    assert record.method == "GET"
    assert record.path == "/fail"
    assert record.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
    assert isinstance(record.duration, int)


@pytest.mark.asyncio
async def test_request_id_ctx_set_in_middleware():
    request_ids = []
    request = build_request("/id")

    async def inner_call_next(_: Request):
        return JSONResponse({"ok": True})

    async def call_next(request: Request):
        await logging_middleware(request, inner_call_next)
        request_ids.append(request_id_ctx.get())
        return JSONResponse({"ok": True})

    await call_next(request)
    assert request_ids[0] is not None
    assert re.match(r"^[0-9a-f\-]{36}$", request_ids[0])
