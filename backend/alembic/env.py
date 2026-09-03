from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from sqlalchemy.engine import Connection

from alembic import context
from app.core.settings import settings

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", settings.database_url)

# Importing app.models registers every table on Base.metadata for autogenerate.
from app.models import Base  # noqa: E402

target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def _run_migrations(connection: Connection) -> None:
    # SQLite cannot ALTER a table in place, so restructuring one means create-copy-DROP-rename
    # (see migration 0004). `app/core/db.py` turns foreign_keys ON for every connection, and with
    # it on that DROP fails against any database holding child rows — which is every real one.
    #
    # So enforcement is suspended for the duration of a migration run and restored afterwards.
    # It must be toggled here rather than inside a migration: `PRAGMA foreign_keys` is a silent
    # no-op inside a transaction, and alembic's `autocommit_block()` can't be used either because
    # it asserts it owns the transaction, which is false when a connection is injected (below).
    # Each rebuilding migration is responsible for leaving the data referentially sound; the
    # migration test asserts `PRAGMA foreign_key_check` is clean afterwards.
    was_enabled = connection.exec_driver_sql("PRAGMA foreign_keys").scalar()
    connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
    try:
        # render_as_batch lets SQLite ALTER-heavy migrations work.
        context.configure(
            connection=connection, target_metadata=target_metadata, render_as_batch=True
        )
        with context.begin_transaction():
            context.run_migrations()
    finally:
        # Commit before restoring the pragma, for two reasons: reading the pragma above opened a
        # transaction, and SQLite runs DDL non-transactionally, so without this the migrations
        # would be rolled back when the connection closes; and `PRAGMA foreign_keys` is silently
        # ignored while a transaction is open, so the restore would be a no-op.
        connection.commit()
        connection.exec_driver_sql(f"PRAGMA foreign_keys={'ON' if was_enabled else 'OFF'}")


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    Tests inject a live connection via ``config.attributes["connection"]`` (so migrations
    apply to the same in-memory DB the test uses); otherwise an engine is built from config.
    """
    injected = config.attributes.get("connection", None)
    if injected is not None:
        _run_migrations(injected)
        return

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        _run_migrations(connection)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
