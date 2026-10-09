"""Migration test: `alembic upgrade head` then `downgrade base` on a scratch database.

Guards the most expensive drift in this project: the models and the migration hand-written for
them (autogenerate is not available in the sandbox — see the migration's docstring). If a model
gains a column without a matching revision, or a revision drops something a model still expects,
this is where it surfaces.

Skipped unless `RUN_INTEGRATION=1`, because it needs a real Postgres instance: SQLite accepts
schema that Postgres rejects, so a SQLite-only check would prove nothing about the migration's
target dialect.
"""

from __future__ import annotations

import os
import pathlib
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import Engine

pytestmark = pytest.mark.integration

_HERE = pathlib.Path(__file__).resolve().parent
_ALEMBIC_DIR = _HERE.parent / "alembic"


@pytest.fixture(scope="module")
def scratch_engine() -> Iterator[Engine]:
    """A throwaway Postgres database for one upgrade/downgrade cycle."""
    database_url = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not database_url:
        pytest.skip("no DATABASE_URL for the migration test")

    scratch_url = database_url.rstrip("/") + "_migrations"
    server_engine = create_engine(database_url, pool_pre_ping=True, future=True)
    with server_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.exec_driver_sql(f"DROP DATABASE IF EXISTS {scratch_url.rsplit('/', 1)[-1]}")
        connection.exec_driver_sql(f"CREATE DATABASE {scratch_url.rsplit('/', 1)[-1]}")

    engine = create_engine(scratch_url, pool_pre_ping=True, future=True)
    try:
        yield engine
    finally:
        engine.dispose()
        with server_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.exec_driver_sql(f"DROP DATABASE IF EXISTS {scratch_url.rsplit('/', 1)[-1]}")
        server_engine.dispose()


@pytest.fixture(scope="module")
def alembic_config(scratch_engine: Engine) -> str:
    from alembic.config import Config

    config = Config(str(_ALEMBIC_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(_ALEMBIC_DIR))
    config.set_main_option(
        "sqlalchemy.url", scratch_engine.url.render_as_string(hide_password=False)
    )
    return config


def _run_alembic(config_path: str, *args: str) -> None:
    from alembic.config import CommandLine, Config

    config = Config(config_path)
    CommandLine().main(argv=list(args), prog="alembic", config=config)


class TestMigrationRoundTrip:
    def test_upgrade_then_downgrade(self, alembic_config: str, scratch_engine: Engine) -> None:
        _run_alembic(alembic_config, "upgrade", "head")

        inspector = inspect(scratch_engine)
        tables = set(inspector.get_table_names())
        for expected in (
            "repositories",
            "contributors",
            "pull_requests",
            "pull_request_reviews",
            "issues",
            "commits",
            "releases",
            "file_changes",
            "ingestion_jobs",
        ):
            assert expected in tables, f"{expected} missing after upgrade head"

        # The ingestion tables are Phase 2; the baseline revision owns nothing but alembic_version.
        _run_alembic(alembic_config, "downgrade", "base")
        remaining = set(inspect(scratch_engine).get_table_names())
        assert remaining <= {
            "alembic_version"
        }, f"unexpected tables after downgrade base: {remaining}"

    def test_head_matches_the_models(self, alembic_config: str, scratch_engine: Engine) -> None:
        """Every mapped table and column must exist after `upgrade head`."""
        from app.models import Base

        _run_alembic(alembic_config, "upgrade", "head")
        inspector = inspect(scratch_engine)

        for table, mapper in Base.metadata.tables.items():
            assert table in inspector.get_table_names()
            columns = {column["name"] for column in inspector.get_columns(table)}
            for column in mapper.columns:
                assert column.name in columns, f"{table}.{column.name} missing from the migration"
