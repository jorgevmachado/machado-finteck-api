import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from testcontainers.community.postgres import PostgresContainer

from app.models import (
    Receipt,
    ReceiptFieldRule,
    ReceiptIdentificationRule,
    ReceiptInterpretationProfile,
    Role,
    User,
)

ROOT = Path(__file__).resolve().parents[5]


@pytest.fixture(scope="session")
def receipt_profile_database_url():
    with PostgresContainer(
        "postgres:16-alpine",
        username="receipt_profile_test",
        password=uuid4().hex,
        dbname="receipt_profile_test",
    ) as container:
        url = (
            make_url(container.get_connection_url())
            .set(drivername="postgresql+psycopg")
            .render_as_string(hide_password=False)
        )
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=ROOT,
            env=os.environ | {"DATABASE_URL": url},
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        yield url


@pytest_asyncio.fixture
async def profile_sessions(receipt_profile_database_url):
    engine = create_async_engine(receipt_profile_database_url, poolclass=NullPool)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as session:
        for model in (
            Receipt,
            ReceiptFieldRule,
            ReceiptIdentificationRule,
            ReceiptInterpretationProfile,
            User,
            Role,
        ):
            await session.execute(delete(model))
        await session.commit()
    yield sessions
    await engine.dispose()


async def create_user(session):
    suffix = uuid4().hex
    role = Role(
        name=f"Profile {suffix}",
        name_code=f"profile_{suffix}",
        description="Receipt profile test",
    )
    user = User(
        role_id=role.id,
        name=f"Profile {suffix}",
        email=f"{suffix}@profile.test",
        username=f"profile-{suffix}",
        date_of_birth=datetime(1990, 1, 1, tzinfo=timezone.utc),
    )
    session.add_all([role, user])
    await session.commit()
    return user
