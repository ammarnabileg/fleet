from alembic import context
from sqlalchemy import create_engine

import app.models  # noqa: F401  (fills Base.metadata)
from app.core.config import get_settings
from app.core.db import Base, include_name


def run() -> None:
    url = context.config.get_main_option("sqlalchemy.url") or get_settings().database_url
    engine = create_engine(url)
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=Base.metadata,
            include_schemas=True,
            include_name=include_name,
            version_table_schema="public",
        )
        with context.begin_transaction():
            context.run_migrations()


run()
