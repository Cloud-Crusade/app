from unittest.mock import AsyncMock, patch

import pytest
from common import dev_bootstrap
from common.dev_bootstrap import initDevSchemaIfEnabled


@pytest.mark.asyncio
@pytest.mark.parametrize("env", ["production", "staging"])
async def test_skipped_when_env_is_not_dev_or_test(env, monkeypatch):
    monkeypatch.setattr(dev_bootstrap.settings, "env", env)
    create_all = AsyncMock()

    with patch.object(dev_bootstrap, "_createAll", create_all):
        await initDevSchemaIfEnabled()

    create_all.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("env", ["development", "test"])
async def test_runs_create_all_when_env_is_dev_or_test(env, monkeypatch):
    monkeypatch.setattr(dev_bootstrap.settings, "env", env)
    create_all = AsyncMock()

    with patch.object(dev_bootstrap, "_createAll", create_all):
        await initDevSchemaIfEnabled()

    # core + reservation 두 베이스에 대해 호출
    assert create_all.await_count == 2
