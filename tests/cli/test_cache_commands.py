from unittest.mock import MagicMock
from pyquipu.cli.main import app


def test_cache_sync(runner, quipu_workspace, monkeypatch):
    work_dir, _, _ = quipu_workspace
    mock_bus = MagicMock()
    monkeypatch.setattr("pyquipu.cli.commands.cache.bus", mock_bus)

    result = runner.invoke(app, ["cache", "sync", "-w", str(work_dir)])

    assert result.exit_code == 0
    mock_bus.info.assert_called_once_with("cache.sync.info.hydrating")
    mock_bus.success.assert_called_once_with("cache.sync.success")


def test_cache_rebuild_no_db(runner, quipu_workspace, monkeypatch):
    work_dir, _, _ = quipu_workspace
    mock_bus = MagicMock()
    monkeypatch.setattr("pyquipu.cli.commands.cache.bus", mock_bus)

    result = runner.invoke(app, ["cache", "rebuild", "-w", str(work_dir)])

    assert result.exit_code == 0
    mock_bus.warning.assert_called_once_with("cache.rebuild.info.dbNotFound")
    mock_bus.info.assert_called_once_with("cache.sync.info.hydrating")
    mock_bus.success.assert_called_once_with("cache.sync.success")
