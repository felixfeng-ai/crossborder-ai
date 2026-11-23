"""生产启动 schema 门禁测试。"""

from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine
import ssl

from app.core import database
from app.core.config import settings


def _engine(path: Path):
    return create_async_engine(
        f"sqlite+aiosqlite:///{path.as_posix()}"
    )


def test_database_connect_args_disable_and_require() -> None:
    assert database._database_connect_args(
        use_sqlite=False,
        ssl_mode="disable",
        ssl_ca_path="",
        ssl_cert_path="",
        ssl_key_path="",
    ) == {}
    assert database._database_connect_args(
        use_sqlite=False,
        ssl_mode="require",
        ssl_ca_path="",
        ssl_cert_path="",
        ssl_key_path="",
    ) == {"ssl": "require"}


def test_database_connect_args_rejects_invalid_mode() -> None:
    with pytest.raises(ValueError, match="DB_SSL_MODE"):
        database._database_connect_args(
            use_sqlite=False,
            ssl_mode="invalid",
            ssl_ca_path="",
            ssl_cert_path="",
            ssl_key_path="",
        )


def test_database_connect_args_builds_verified_tls(monkeypatch) -> None:
    class FakeContext:
        check_hostname = True
        verify_mode = ssl.CERT_REQUIRED

        def load_cert_chain(self, cert_path, key_path):
            self.loaded = (cert_path, key_path)

    context = FakeContext()
    monkeypatch.setattr(
        database.ssl,
        "create_default_context",
        lambda cafile=None: context,
    )

    result = database._database_connect_args(
        use_sqlite=False,
        ssl_mode="verify-full",
        ssl_ca_path="/tmp/ca.pem",
        ssl_cert_path="",
        ssl_key_path="",
    )

    assert result == {"ssl": context}
    assert context.check_hostname is True
    assert context.verify_mode == ssl.CERT_REQUIRED


def test_database_connect_args_requires_cert_and_key_pair(tmp_path) -> None:
    with pytest.raises(ValueError, match="必须同时配置"):
        database._database_connect_args(
            use_sqlite=False,
            ssl_mode="verify-ca",
            ssl_ca_path="",
            ssl_cert_path=str(tmp_path / "client.pem"),
            ssl_key_path="",
        )


def test_database_connect_args_rejects_missing_certificate_file(
    tmp_path,
) -> None:
    with pytest.raises(ValueError, match="凭证文件不存在"):
        database._database_connect_args(
            use_sqlite=False,
            ssl_mode="verify-ca",
            ssl_ca_path="",
            ssl_cert_path=str(tmp_path / "client.pem"),
            ssl_key_path=str(tmp_path / "client.key"),
        )


@pytest.mark.asyncio
async def test_get_db_commits_on_success(monkeypatch) -> None:
    class FakeSession:
        def __init__(self):
            self.committed = False
            self.closed = False

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return False

        async def commit(self):
            self.committed = True

        async def rollback(self):
            raise AssertionError("success path must not rollback")

        async def close(self):
            self.closed = True

    session = FakeSession()
    monkeypatch.setattr(
        database,
        "async_session_factory",
        lambda: session,
    )
    dependency = database.get_db()

    yielded = await anext(dependency)
    assert yielded is session
    with pytest.raises(StopAsyncIteration):
        await anext(dependency)
    assert session.committed is True
    assert session.closed is True


@pytest.mark.asyncio
async def test_get_db_rolls_back_and_reraises(monkeypatch) -> None:
    class FakeSession:
        def __init__(self):
            self.rolled_back = False
            self.closed = False

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return False

        async def commit(self):
            raise AssertionError("failure path must not commit")

        async def rollback(self):
            self.rolled_back = True

        async def close(self):
            self.closed = True

    session = FakeSession()
    monkeypatch.setattr(
        database,
        "async_session_factory",
        lambda: session,
    )
    dependency = database.get_db()
    await anext(dependency)

    with pytest.raises(RuntimeError, match="route failed"):
        await dependency.athrow(RuntimeError("route failed"))

    assert session.rolled_back is True
    assert session.closed is True


@pytest.mark.asyncio
async def test_postgresql_startup_rejects_missing_migration_table(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "USE_SQLITE", False)
    engine = _engine(tmp_path / "missing-migration.db")

    with pytest.raises(
        database.SchemaMigrationError,
        match="alembic_version",
    ):
        await database.init_db(db_engine=engine)

    async with engine.connect() as conn:
        table_names = await conn.run_sync(
            lambda sync_conn: sa.inspect(sync_conn).get_table_names()
        )
    assert "users" not in table_names
    await engine.dispose()


@pytest.mark.asyncio
async def test_postgresql_startup_rejects_stale_revision(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "USE_SQLITE", False)
    engine = _engine(tmp_path / "stale-revision.db")
    expected = database.get_expected_migration_head()
    async with engine.begin() as conn:
        await conn.execute(
            sa.text(
                "CREATE TABLE alembic_version "
                "(version_num VARCHAR(32) PRIMARY KEY)"
            )
        )
        await conn.execute(
            sa.text(
                "INSERT INTO alembic_version(version_num) "
                "VALUES ('072_user_workspace_lifecycle')"
            )
        )

    with pytest.raises(database.SchemaMigrationError) as exc_info:
        await database.init_db(db_engine=engine)

    message = str(exc_info.value)
    assert "072_user_workspace_lifecycle" in message
    assert expected in message
    await engine.dispose()


@pytest.mark.asyncio
async def test_postgresql_startup_accepts_current_head(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "USE_SQLITE", False)
    engine = _engine(tmp_path / "current-revision.db")
    expected = database.get_expected_migration_head()
    async with engine.begin() as conn:
        await conn.execute(
            sa.text(
                "CREATE TABLE alembic_version "
                "(version_num VARCHAR(32) PRIMARY KEY)"
            )
        )
        await conn.execute(
            sa.text(
                "INSERT INTO alembic_version(version_num) "
                "VALUES (:revision)"
            ),
            {"revision": expected},
        )

    result = await database.init_db(db_engine=engine)

    assert result == expected
    await engine.dispose()


@pytest.mark.asyncio
async def test_sqlite_development_startup_still_creates_tables(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "USE_SQLITE", True)
    engine = _engine(tmp_path / "development.db")

    await database.init_db(db_engine=engine)

    async with engine.connect() as conn:
        table_names = await conn.run_sync(
            lambda sync_conn: sa.inspect(sync_conn).get_table_names()
        )
    assert "users" in table_names
    assert "workspaces" in table_names
    await engine.dispose()
