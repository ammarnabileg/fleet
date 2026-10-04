from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext

import app.models  # noqa: F401
from app.core.db import Base, get_engine, include_name


def test_models_match_the_migrated_schema(database_url):
    with get_engine().connect() as c:
        ctx = MigrationContext.configure(
            c, opts={"include_schemas": True, "include_name": include_name, "compare_type": True}
        )
        diff = compare_metadata(ctx, Base.metadata)
    assert diff == [], diff
