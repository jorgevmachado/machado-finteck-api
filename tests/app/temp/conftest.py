from datetime import date, datetime
from fnmatch import fnmatchcase
import logging
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from pydantic import BaseModel, ConfigDict
from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
    selectinload,
)

from app.temp.repository import BaseRepository, RangeFilter, RelationFilter
from app.temp.service import BaseService
from app.core.logging import LoggingParams
from app.core.cache.manager import CacheManager
from tests.conftest import FakeRedis


class TestTables(DeclarativeBase):
    pass


class Item(TestTables):
    __tablename__ = "experimental_items"
    __table_args__ = (UniqueConstraint("user_id", "name_code"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID]
    name: Mapped[str]
    name_code: Mapped[str | None] = mapped_column(default=None)
    description: Mapped[str | None] = mapped_column(default=None)
    occurred_on: Mapped[date] = mapped_column(default=date(2026, 1, 1))
    deleted_at: Mapped[datetime | None] = mapped_column(default=None)
    children: Mapped[list["Child"]] = relationship(back_populates="item")


class Child(TestTables):
    __tablename__ = "experimental_children"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    item_id: Mapped[UUID] = mapped_column(ForeignKey(Item.id))
    user_id: Mapped[UUID] = mapped_column(default=uuid4)
    label: Mapped[str] = mapped_column(default="matching")
    item: Mapped[Item] = relationship(back_populates="children")


class ItemRepository(BaseRepository[Item]):
    model = Item
    filter_fields = ("id", "name", "name_code")
    order_fields = ("id", "name")
    default_order_by = "name"
    relations = (selectinload(Item.children),)
    relation_filters = {"child_label": RelationFilter("children", "label")}
    range_filters = {
        "start_date": RangeFilter("occurred_on", "gte"),
        "end_date": RangeFilter("occurred_on", "lte"),
    }


class ItemCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    description: str | None = None


class ItemUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = "unused default"
    description: str | None = None


class ItemSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    description: str | None


class ItemService(BaseService[Item, ItemCreate, ItemUpdate, ItemSchema]):
    def _build_entity(self, user_id, data):
        return Item(user_id=user_id, **data)

    async def specialized(self, user, target_id, *, fail=False):
        async with self._operation("specialized", user.username, target_id):
            if fail:
                raise RuntimeError("specialized failure")
            return "done"


@pytest.fixture
def logging_params():
    return LoggingParams(
        logger=logging.getLogger("experimental-tests"),
        service="ItemService",
        operation="item",
    )


@pytest.fixture
def service(repository, logging_params):
    return ItemService(repository, alias="Item", logger_params=logging_params)


class ExperimentalRedis(FakeRedis):
    def __init__(self):
        super().__init__()
        self.ttls = {}

    async def setex(self, key, ttl, value):
        self.ttls[key] = ttl
        return await super().setex(key, ttl, value)

    async def delete(self, key):
        return int(self._data.pop(key, None) is not None)

    async def scan_iter(self, *, match):
        for key in list(self._data):
            if fnmatchcase(key, match):
                yield key


@pytest.fixture
def cache_redis(monkeypatch):
    redis = ExperimentalRedis()
    manager = CacheManager(redis_client=redis)
    monkeypatch.setattr("app.core.cache.service.CacheManager", lambda: manager)
    return redis


@pytest.fixture
def cached_service(repository, logging_params, cache_redis):
    return ItemService(
        repository,
        alias="Item",
        logger_params=logging_params,
        schema_class=ItemSchema,
        cache_prefix="items",
        parents_alias=("dashboard",),
        default_ttl=120,
    )


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(TestTables.metadata.create_all)
    async with AsyncSession(engine, expire_on_commit=False) as session:
        yield session
    await engine.dispose()


@pytest.fixture
def repository(session):
    return ItemRepository(session)


@pytest_asyncio.fixture
async def records(session, user):
    items = [
        Item(user_id=user.id, name="Same"),
        Item(user_id=user.id, name="Same"),
        Item(user_id=uuid4(), name="Same"),
    ]
    session.add_all(items)
    await session.flush()
    session.add_all([Child(item_id=items[0].id), Child(item_id=items[0].id)])
    await session.commit()
    return items
