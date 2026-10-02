"""Alembic environment for AI-CRMS.

The engine comes from ``app.database`` so migrations always target the same
database as the application (``DATABASE_URL``). Callers that already hold a
connection (the application start-up path and the test-suite) pass it in via
``config.attributes["connection"]`` so in-memory SQLite databases work.
"""
from logging.config import fileConfig

from alembic import context

from app.database import Base, engine
from app import models  # noqa: F401  (registers all tables on Base.metadata)

config = context.config
if config.config_file_name is not None and not config.attributes.get("skip_logging_config"):
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _configure(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        # SQLite cannot ALTER most constraints in place; batch mode rebuilds tables.
        render_as_batch=connection.dialect.name == "sqlite",
        compare_type=True,
    )


def run_migrations_offline() -> None:
    context.configure(
        url=str(engine.url),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=engine.dialect.name == "sqlite",
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        _configure(connection)
        with context.begin_transaction():
            context.run_migrations()
        return
    with engine.connect() as conn:
        _configure(conn)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
