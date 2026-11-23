import pytest
from sqlalchemy import create_engine, inspect

from tests.app.domain.category.conftest import (  # noqa: F401
    category_postgres_container,
    fresh_category_postgres_url,
    run_category_alembic,
)

pytestmark = pytest.mark.integration


def test_institution_uniqueness_migration_roundtrip(request):
    database_url = request.getfixturevalue("fresh_category_postgres_url")
    run_alembic = request.getfixturevalue("run_category_alembic")
    run_alembic(database_url, "upgrade", "584c97909e82")
    engine = create_engine(database_url)

    def unique_columns():
        return {
            tuple(constraint["column_names"])
            for constraint in inspect(engine).get_unique_constraints("institutions")
        }

    try:
        assert unique_columns() == {("name_code",), ("user_id", "name_code")}
        run_alembic(database_url, "upgrade", "head")
        assert unique_columns() == {("user_id", "name_code")}
        run_alembic(database_url, "downgrade", "584c97909e82")
        assert unique_columns() == {("name_code",), ("user_id", "name_code")}
        run_alembic(database_url, "upgrade", "head")
        assert unique_columns() == {("user_id", "name_code")}
    finally:
        engine.dispose()
