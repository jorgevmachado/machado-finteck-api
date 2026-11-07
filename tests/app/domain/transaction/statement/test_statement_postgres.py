from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.database import get_session
from app.core.security import get_current_user
from app.domain.account.schema import AccountCreateSchema
from app.domain.account.service import AccountService
from app.domain.transaction.route import router
from app.domain.transaction.series.schema import TransactionSeriesCreateSchema
from app.models import Role, ScheduledTransaction, TransactionSeries, User
from tests.app.domain.category.conftest import (  # noqa: F401
    category_postgres_container,
    fresh_category_postgres_url,
    run_category_alembic,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_statement_with_real_postgres_and_moved_occurrence(request):
    database_url = request.getfixturevalue("fresh_category_postgres_url")
    request.getfixturevalue("run_category_alembic")(database_url, "upgrade", "head")
    engine = create_async_engine(database_url)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            suffix = uuid4().hex
            role = Role(name="User", name_code=suffix, description="Statement test")
            user = User(
                role_id=role.id,
                name="Statement test",
                email=f"{suffix}@statement.test",
                username=suffix,
                date_of_birth=datetime(1990, 1, 1, tzinfo=timezone.utc),
            )
            session.add_all([role, user])
            await session.commit()
            account = await AccountService.from_session(session).create(
                user, AccountCreateSchema(name="Main", type="CHECKING")
            )
            series = TransactionSeries(
                user_id=user.id,
                **TransactionSeriesCreateSchema(
                    kind="CLOSED",
                    name="Notebook",
                    value="250.50",
                    direction="OUT",
                    account_id=account.id,
                    start_date="2026-09-15",
                    frequency_unit="MONTH",
                    frequency_interval=1,
                    day_of_month=10,
                    installments=12,
                ).model_dump(),
            )
            session.add(series)
            await session.commit()
            app = FastAPI()
            app.include_router(router, prefix="/transactions")
            app.dependency_overrides[get_session] = lambda: session
            app.dependency_overrides[get_current_user] = lambda: user
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                october = await client.get(
                    "/transactions/statement",
                    params={
                        "start_date": "2026-10-01",
                        "end_date": "2026-10-31",
                        "page": 1,
                    },
                )
                assert october.status_code == 200
                entry = october.json()["items"][0]
                assert entry["source"] == "PROJECTED"
                assert entry["occurrence_index"] == 1
                assert entry["expected_on"] == "2026-10-10"
                assert entry["value"] == "250.50"
                assert (
                    await session.scalar(
                        select(func.count()).select_from(ScheduledTransaction)
                    )
                    == 0
                )
                moved = ScheduledTransaction(
                    user_id=user.id,
                    account_id=account.id,
                    transaction_series_id=series.id,
                    subcategory_id=None,
                    credit_card_id=None,
                    name="Notebook",
                    direction="OUT",
                    status="SETTLED",
                    expected_on=date(2026, 12, 5),
                    settled_on=date(2026, 12, 5),
                    note=None,
                    occurrence_on=date(2026, 11, 10),
                    occurrence_index=2,
                    value=Decimal("300.00"),
                )
                session.add(moved)
                await session.commit()
                november = await client.get(
                    "/transactions/statement",
                    params={
                        "start_date": "2026-11-01",
                        "end_date": "2026-11-30",
                        "page": 1,
                    },
                )
                assert november.status_code == 200
                assert november.json()["items"] == []
                assert november.json()["meta"]["total"] == 0
                december = await client.get(
                    "/transactions/statement",
                    params={
                        "start_date": "2026-12-01",
                        "end_date": "2026-12-31",
                        "page": 1,
                    },
                )
                assert december.status_code == 200
                assert december.json()["meta"]["total"] == 2
                assert [
                    (entry["source"], entry["occurrence_index"])
                    for entry in december.json()["items"]
                ] == [
                    ("PROJECTED", 3),
                    ("SCHEDULED", 2),
                ]
                assert december.json()["items"][1]["value"] == "300.00"
                assert (
                    await session.scalar(
                        select(func.count()).select_from(ScheduledTransaction)
                    )
                    == 1
                )
    finally:
        await engine.dispose()
