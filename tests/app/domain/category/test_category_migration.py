import pytest
from sqlalchemy import create_engine, text

pytestmark = pytest.mark.integration


def test_category_migration_upgrade_downgrade_upgrade_roundtrip(
    fresh_category_postgres_url, run_category_alembic
):
    database_url = fresh_category_postgres_url
    run_category_alembic(database_url, "upgrade", "head")
    engine = create_engine(database_url)

    with engine.connect() as connection:
        assert connection.scalar(text("SELECT to_regclass('categories')")) is not None
        assert (
            connection.scalar(text("SELECT to_regclass('subcategories')")) is not None
        )
        generated = connection.execute(
            text(
                "SELECT is_generated FROM information_schema.columns "
                "WHERE table_name = 'subcategories' AND column_name = 'live_order'"
            )
        ).scalar_one()
        deferred_constraint = connection.execute(
            text(
                "SELECT condeferrable AND condeferred "
                "FROM pg_constraint "
                "WHERE conname = 'uq_subcategories_category_live_order'"
            )
        ).scalar_one()
        partial_unique_index = connection.execute(
            text(
                "SELECT indexdef FROM pg_indexes "
                "WHERE indexname = 'uq_categories_owner_name_live'"
            )
        ).scalar_one()

    assert generated == "ALWAYS"
    assert deferred_constraint is True
    assert "WHERE (deleted_at IS NULL)" in partial_unique_index
    run_category_alembic(database_url, "downgrade", "96a6c5c537ee")

    with engine.connect() as connection:
        assert connection.scalar(text("SELECT to_regclass('categories')")) is None
        assert connection.scalar(text("SELECT to_regclass('subcategories')")) is None

    run_category_alembic(database_url, "upgrade", "head")
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT to_regclass('categories')")) is not None
        assert (
            connection.scalar(text("SELECT to_regclass('subcategories')")) is not None
        )

    engine.dispose()
