import pytest
from sqlalchemy import create_engine, inspect

from tests.app.domain.category.conftest import (  # noqa: F401
    category_postgres_container,
    fresh_category_postgres_url,
    run_category_alembic,
)

pytestmark = pytest.mark.integration


def test_unique_index_covers_series_and_occurrence(request):
    database_url = request.getfixturevalue("fresh_category_postgres_url")
    run_alembic = request.getfixturevalue("run_category_alembic")
    run_alembic(database_url, "upgrade", "head")
    engine = create_engine(database_url)

    try:
        unique_indexes = {
            (index["name"], tuple(index["column_names"]))
            for index in inspect(engine).get_indexes("scheduled_transactions")
            if index.get("unique")
        }
    finally:
        engine.dispose()

    assert (
        "uq_scheduled_transactions_series_occurrence",
        ("transaction_series_id", "occurrence_index"),
    ) in unique_indexes


def test_migration_roundtrip_removes_and_restores_the_unique_index(request):
    database_url = request.getfixturevalue("fresh_category_postgres_url")
    run_alembic = request.getfixturevalue("run_category_alembic")
    run_alembic(database_url, "upgrade", "head")
    engine = create_engine(database_url)

    def index_names():
        return {
            index["name"]
            for index in inspect(engine).get_indexes("scheduled_transactions")
        }

    try:
        assert "uq_scheduled_transactions_series_occurrence" in index_names()
        run_alembic(database_url, "downgrade", "9fc4f731e471")
        assert "uq_scheduled_transactions_series_occurrence" not in index_names()
        run_alembic(database_url, "upgrade", "head")
        assert "uq_scheduled_transactions_series_occurrence" in index_names()
    finally:
        engine.dispose()
