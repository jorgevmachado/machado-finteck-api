from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import create_engine, delete
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from testcontainers.community.postgres import PostgresContainer

from app.domain.category.schema import SubcategoryReconcileSchema
from app.models import Category, Role, Subcategory, User

PROJECT_ROOT = Path(__file__).resolve().parents[4]


def _async_postgres_url(container: PostgresContainer) -> str:
    from sqlalchemy.engine import make_url

    return (
        make_url(container.get_connection_url())
        .set(drivername="postgresql+psycopg")
        .render_as_string(hide_password=False)
    )


def _run_alembic(database_url: str, *arguments: str) -> None:
    environment = os.environ | {"DATABASE_URL": database_url}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *arguments],
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
        check=False,
        text=True,
    )
    if result.returncode:
        pytest.fail(
            f"Alembic {' '.join(arguments)} failed:\n{result.stdout}\n{result.stderr}"
        )


@pytest.fixture
def run_category_alembic():
    return _run_alembic


@pytest.fixture(scope="session")
def category_postgres_container():
    with PostgresContainer(
        "postgres:16-alpine",
        username="category_test",
        password="category_test",
        dbname="category_test",
    ) as container:
        yield container


@pytest.fixture(scope="session")
def migrated_category_database_url(category_postgres_container):
    database_url = _async_postgres_url(category_postgres_container)
    _run_alembic(database_url, "upgrade", "head")
    return database_url


@pytest.fixture
def fresh_category_postgres_url(category_postgres_container):
    base_url = make_url(_async_postgres_url(category_postgres_container))
    database_name = f"category_migration_{uuid4().hex}"
    engine = create_engine(base_url, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql(f'CREATE DATABASE "{database_name}"')
        yield base_url.set(database=database_name).render_as_string(hide_password=False)
    finally:
        with engine.connect() as connection:
            connection.exec_driver_sql(f'DROP DATABASE "{database_name}"')
        engine.dispose()


@pytest_asyncio.fixture
async def category_session_factory(migrated_category_database_url):
    engine = create_async_engine(migrated_category_database_url, poolclass=NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        await session.execute(delete(Subcategory))
        await session.execute(delete(Category))
        await session.execute(delete(User))
        await session.execute(delete(Role))
        await session.commit()

    yield session_factory
    await engine.dispose()


@pytest.fixture
def category_entity(user):
    return Category(
        user_id=user.id,
        name="Casa",
        icon=None,
        color=None,
        is_active=True,
    )


@pytest.fixture
def subcategory_entity():
    return Subcategory(name="Mercado", order=1)


@pytest.fixture
def category_reconciliation_payload():
    return [
        SubcategoryReconcileSchema(name="Mercado atualizado", order=2),
        SubcategoryReconcileSchema(name="Restaurantes", order=1),
    ]


@pytest.fixture
def new_user_values():
    suffix = uuid4().hex
    return {
        "name": f"Category test {suffix}",
        "email": f"{suffix}@category.test",
        "username": f"category-{suffix}",
    }
