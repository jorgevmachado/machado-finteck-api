from __future__ import annotations

from http import HTTPStatus
from unittest.mock import AsyncMock
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi_pagination import LimitOffsetParams
from fastapi.testclient import TestClient
import pytest

from app.core.pagination import CustomLimitOffsetPage
from app.core.security import get_current_user
from app.domain.category.route import (
    category_filter,
    category_service,
    create,
    delete,
    find_one,
    list_categories,
    router,
    seed,
    update,
)
from app.domain.category.schema import (
    CategoryCreateSchema,
    CategorySeedSchema,
    CategoryUpdateSchema,
)
from app.domain.category.service import CategoryService
from app.models import Category
from app.shared.schemas import FilterPage, Message


def build_client(user, service):
    app = FastAPI()
    app.include_router(router, prefix="/categories")
    app.dependency_overrides[category_service] = lambda: service
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def valid_create_payload():
    return {
        "name": "Casa",
        "subcategories": [
            {"name": "Mercado", "order": 1},
            {"name": "Restaurantes", "order": 2},
        ],
    }


def test_category_service_builds_from_session():
    assert isinstance(category_service(AsyncMock()), CategoryService)


def test_category_filter_builds_name_and_pagination_filter():
    page_filter = category_filter(page=2, name="Casa", limit=4)

    assert page_filter.page == 2
    assert page_filter.name == "Casa"
    assert page_filter.limit == 4


@pytest.mark.asyncio
async def test_category_routes_delegate_with_authenticated_owner(
    user, category_entity, category_reconciliation_payload
):
    service = AsyncMock()
    payload = CategoryCreateSchema.model_validate(valid_create_payload())
    update_payload = CategoryUpdateSchema(subcategories=category_reconciliation_payload)
    category_id = uuid4()
    page_filter = FilterPage.build(name="Casa")

    await create(service, user, payload)
    await list_categories(service, user, page_filter)
    await find_one(category_id, service, user)
    await update(category_id, service, user, update_payload)
    await delete(category_id, service, user)
    await seed(service, user)

    service.create.assert_awaited_once_with(user=user, payload=payload)
    service.list_all.assert_awaited_once_with(page_filter=page_filter, user=user)
    service.find_by.assert_awaited_once_with(
        filters={"id": category_id},
        user=user,
    )
    service.update.assert_awaited_once_with(
        identifier=category_id,
        payload=update_payload,
        user=user,
    )
    service.delete.assert_awaited_once_with(user=user, identifier=category_id)
    service.seed_defaults.assert_awaited_once_with(user=user)


def test_router_exposes_five_crud_operations_and_seed():
    operations = {
        (method, route.path) for route in router.routes for method in route.methods
    }

    assert operations == {
        ("POST", ""),
        ("GET", ""),
        ("GET", "/{category_id}"),
        ("PUT", "/{category_id}"),
        ("DELETE", "/{category_id}"),
        ("POST", "/seed"),
    }


def test_category_router_registered_in_application_openapi():
    from app.main import app

    paths = app.openapi()["paths"]
    assert {
        (method.upper(), path)
        for path, path_item in paths.items()
        if path.startswith("/categories")
        for method in path_item
    } == {
        ("POST", "/categories"),
        ("GET", "/categories"),
        ("GET", "/categories/{category_id}"),
        ("PUT", "/categories/{category_id}"),
        ("DELETE", "/categories/{category_id}"),
        ("POST", "/categories/seed"),
    }


class TestCategoryHTTPRoutes:
    @staticmethod
    def test_seed_uses_authenticated_user_and_returns_counts(user):
        service = AsyncMock()
        service.seed_defaults.return_value = CategorySeedSchema(created=14, skipped=0)

        with build_client(user, service) as client:
            response = client.post("/categories/seed")

        assert response.status_code == HTTPStatus.OK
        assert response.json() == {"created": 14, "skipped": 0}
        service.seed_defaults.assert_awaited_once_with(user=user)

    @staticmethod
    def test_create_returns_complete_category_and_created_status(user):
        service = AsyncMock()
        category = Category(
            user_id=user.id,
            name="Casa",
            icon=None,
            color=None,
            is_active=True,
        )
        service.create.return_value = category

        with build_client(user, service) as client:
            response = client.post("/categories", json=valid_create_payload())

        assert response.status_code == HTTPStatus.CREATED
        body = response.json()
        assert body["name"] == "Casa"
        assert body["is_active"] is True
        assert body["icon"] is None
        assert body["color"] is None
        assert body["subcategories"] == []
        assert "user_id" not in body
        service.create.assert_awaited_once()

    @staticmethod
    @pytest.mark.parametrize(
        "payload",
        [
            {"name": "Casa", "user_id": str(uuid4())},
            {"name": "Casa", "id": str(uuid4())},
            {"name": "Casa", "created_at": "2026-01-01T00:00:00Z"},
            {"name": "Casa", "subcategories": None},
            {"name": "Casa", "is_active": None},
            {
                "name": "Casa",
                "subcategories": [
                    {"name": "One", "order": 1, "category_id": str(uuid4())}
                ],
            },
        ],
    )
    def test_create_rejects_client_managed_and_invalid_fields(user, payload):
        service = AsyncMock()

        with build_client(user, service) as client:
            response = client.post("/categories", json=payload)

        assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        service.create.assert_not_awaited()

    @staticmethod
    def test_create_rejects_invalid_name_color_and_child_order(user):
        service = AsyncMock()
        invalid_payloads = [
            {"name": "  "},
            {"name": "Casa", "color": "#FFF"},
            {"name": "Casa", "subcategories": [{"name": "Bad", "order": True}]},
            {"name": "Casa", "subcategories": [{"name": "Bad", "order": "1"}]},
            {
                "name": "Casa",
                "subcategories": [
                    {"name": "One", "order": 1},
                    {"name": "Two", "order": 1},
                ],
            },
        ]

        with build_client(user, service) as client:
            for payload in invalid_payloads:
                response = client.post("/categories", json=payload)
                assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY

        service.create.assert_not_awaited()

    @staticmethod
    def test_list_returns_list_or_pagination_envelope(user, category_entity):
        service = AsyncMock()

        async def list_response(*, page_filter, user):
            if page_filter.page is not None or page_filter.offset is not None:
                return CustomLimitOffsetPage.create(
                    items=[category_entity],
                    total=1,
                    params=LimitOffsetParams(
                        limit=page_filter.limit or 12,
                        offset=0,
                    ),
                )
            return [category_entity]

        service.list_all.side_effect = list_response

        with build_client(user, service) as client:
            plain = client.get("/categories")
            paginated = client.get("/categories?page=1&limit=10")

        assert plain.status_code == HTTPStatus.OK
        assert isinstance(plain.json(), list)
        assert paginated.status_code == HTTPStatus.OK
        assert isinstance(paginated.json(), dict)
        assert "items" in paginated.json()
        assert "meta" in paginated.json()
        assert service.list_all.await_count == 2
        assert service.list_all.await_args_list[0].kwargs["user"] == user
        assert service.list_all.await_args_list[1].kwargs["page_filter"].page == 1

    @staticmethod
    def test_get_returns_owner_scoped_category_and_invalid_uuid_is_422(
        user, category_entity
    ):
        service = AsyncMock()
        service.find_by.return_value = category_entity

        with build_client(user, service) as client:
            response = client.get(f"/categories/{category_entity.id}")
            invalid = client.get("/categories/not-a-uuid")

        assert response.status_code == HTTPStatus.OK
        assert response.json()["name"] == category_entity.name
        assert "user_id" not in response.json()
        assert invalid.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        service.find_by.assert_awaited_once_with(
            filters={"id": category_entity.id},
            user=user,
        )

    @staticmethod
    @pytest.mark.parametrize(
        ("operation", "method", "status_code"),
        [
            ("find_by", "get", HTTPStatus.NOT_FOUND),
            ("update", "put", HTTPStatus.NOT_FOUND),
            ("update", "put", HTTPStatus.CONFLICT),
            ("update", "put", HTTPStatus.UNPROCESSABLE_ENTITY),
            ("delete", "delete", HTTPStatus.NOT_FOUND),
        ],
    )
    def test_get_update_delete_preserve_service_errors(
        user, operation, method, status_code
    ):
        service = AsyncMock()
        service_method = getattr(service, operation)
        service_method.side_effect = HTTPException(
            status_code=status_code, detail="Category operation failed"
        )
        category_id = uuid4()

        with build_client(user, service) as client:
            if method == "get":
                response = client.get(f"/categories/{category_id}")
            elif method == "put":
                response = client.put(
                    f"/categories/{category_id}",
                    json={"subcategories": []},
                )
            else:
                response = client.delete(f"/categories/{category_id}")

        assert response.status_code == status_code
        assert response.json() == {"detail": "Category operation failed"}
        service_method.assert_awaited_once()

    @staticmethod
    def test_update_rejects_null_child_list_and_managed_fields(user):
        service = AsyncMock()
        category_id = uuid4()
        invalid_payloads = [
            {"name": "New name", "subcategories": None},
            {"name": "New name", "id": str(uuid4()), "subcategories": []},
            {"name": None, "subcategories": []},
            {"is_active": None, "subcategories": []},
            {"subcategories": [{"id": None, "name": "New", "order": 1}]},
            {
                "subcategories": [
                    {"name": "New", "order": 1, "category_id": str(uuid4())}
                ]
            },
        ]

        with build_client(user, service) as client:
            responses = [
                client.put(f"/categories/{category_id}", json=payload)
                for payload in invalid_payloads
            ]

        assert all(
            response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
            for response in responses
        )
        service.update.assert_not_awaited()

    @staticmethod
    def test_update_name_without_child_list_delegates_without_reconciliation(user):
        service = AsyncMock()
        service.update.return_value = Message(message="Updated")
        category_id = uuid4()

        with build_client(user, service) as client:
            response = client.put(
                f"/categories/{category_id}", json={"name": "Novo nome"}
            )

        assert response.status_code == HTTPStatus.OK
        payload = service.update.await_args.kwargs["payload"]
        assert payload.model_dump(exclude_unset=True) == {"name": "Novo nome"}
        assert payload.subcategories is None

    @staticmethod
    def test_update_reconciles_mixed_children_and_empty_list(user):
        service = AsyncMock()
        service.update.return_value = Message(message="Updated")
        category_id = uuid4()
        existing_child_id = uuid4()
        mixed_payload = {
            "icon": None,
            "subcategories": [
                {
                    "id": str(existing_child_id),
                    "name": "Retained",
                    "order": 2,
                    "is_active": False,
                },
                {"name": "New child", "order": 1},
            ],
        }

        with build_client(user, service) as client:
            mixed = client.put(
                f"/categories/{category_id}",
                json=mixed_payload,
            )
            empty = client.put(
                f"/categories/{category_id}",
                json={"subcategories": []},
            )

        assert mixed.status_code == HTTPStatus.OK
        assert mixed.json() == {"message": "Updated"}
        assert empty.status_code == HTTPStatus.OK
        assert service.update.await_count == 2
        sent = service.update.await_args_list[0].kwargs["payload"]
        assert sent.icon is None
        assert sent.subcategories[0].id == existing_child_id
        assert sent.subcategories[0].is_active is False
        assert sent.subcategories[1].id is None
        assert service.update.await_args_list[1].kwargs["payload"].subcategories == []

    @staticmethod
    def test_all_category_operations_require_authentication():
        app = FastAPI()
        app.include_router(router, prefix="/categories")
        service = AsyncMock()
        app.dependency_overrides[category_service] = lambda: service

        with TestClient(app) as client:
            responses = [
                client.post("/categories", json={"name": "Casa"}),
                client.get("/categories"),
                client.get(f"/categories/{uuid4()}"),
                client.put(
                    f"/categories/{uuid4()}",
                    json={"subcategories": []},
                ),
                client.delete(f"/categories/{uuid4()}"),
                client.post("/categories/seed"),
            ]

        assert [response.status_code for response in responses] == [
            HTTPStatus.UNAUTHORIZED
        ] * 6
        service.create.assert_not_awaited()
        service.list_all.assert_not_awaited()
        service.find_by.assert_not_awaited()
        service.update.assert_not_awaited()
        service.delete.assert_not_awaited()
        service.seed_defaults.assert_not_awaited()
