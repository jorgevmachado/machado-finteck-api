from app.core.context import request_context


def test_request_id_ctx_default():
    assert request_context.request_id_ctx.get() is None


def test_request_id_ctx_set_and_get():
    request_context.request_id_ctx.set("test-id")
    assert request_context.request_id_ctx.get() == "test-id"


def test_request_id_ctx_is_isolated():
    request_context.request_id_ctx.set("id1")
    token = request_context.request_id_ctx.set("id2")
    assert request_context.request_id_ctx.get() == "id2"
    request_context.request_id_ctx.reset(token)
    assert request_context.request_id_ctx.get() == "id1"
