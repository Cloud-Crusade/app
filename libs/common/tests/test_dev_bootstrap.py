import pytest
from common import dev_bootstrap
from common.dev_bootstrap import initDevSchemaIfEnabled
from sqlalchemy import Column, Integer, MetaData, Table, inspect
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "env, should_create",
    [
        ("production", False),
        ("staging", False),
        ("development", True),
        ("test", True),
    ],
)
async def test_init_dev_schema_only_in_dev_or_test(env, should_create, monkeypatch):
    monkeypatch.setattr(dev_bootstrap.settings, "env", env)
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    metadata = MetaData()
    Table("smoke_t", metadata, Column("id", Integer, primary_key=True))

    await initDevSchemaIfEnabled(metadata, engine)

    async with engine.connect() as conn:
        names = await conn.run_sync(lambda c: inspect(c).get_table_names())
    await engine.dispose()
    assert ("smoke_t" in names) is should_create
