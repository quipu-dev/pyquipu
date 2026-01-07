from unittest import mock
from unittest.mock import MagicMock

from pyquipu.cli.main import app


def test_save_clean_workspace(runner, quipu_workspace, monkeypatch):
    work_dir, _, engine = quipu_workspace
    mock_bus = MagicMock()
    monkeypatch.setattr("pyquipu.cli.commands.workspace.bus", mock_bus)

    (work_dir / "file.txt").write_text("v1")
    engine.capture_drift(engine.git_db.get_tree_hash(), message="Initial")

    result = runner.invoke(app, ["save", "-w", str(work_dir)])
    assert result.exit_code == 0
    mock_bus.success.assert_called_once_with("workspace.save.noChanges")


def test_save_with_changes(runner, quipu_workspace, monkeypatch):
    work_dir, _, _ = quipu_workspace
    mock_bus = MagicMock()
    monkeypatch.setattr("pyquipu.cli.commands.workspace.bus", mock_bus)

    (work_dir / "file.txt").write_text("v2")

    result = runner.invoke(app, ["save", "My Snapshot", "-w", str(work_dir)])
    assert result.exit_code == 0
    mock_bus.success.assert_called_once_with("workspace.save.success", short_hash=mock.ANY, msg_suffix=" (My Snapshot)")


def test_discard_changes(runner, quipu_workspace, monkeypatch):
    work_dir, _, engine = quipu_workspace
    mock_bus = MagicMock()
    monkeypatch.setattr("pyquipu.cli.commands.workspace.bus", mock_bus)

    (work_dir / "file.txt").write_text("v1")
    initial_node = engine.capture_drift(engine.git_db.get_tree_hash())
    (work_dir / "file.txt").write_text("v2")

    result = runner.invoke(app, ["discard", "-f", "-w", str(work_dir)])
    assert result.exit_code == 0
    mock_bus.success.assert_called_once_with("workspace.discard.success", short_hash=initial_node.short_hash)
    assert (work_dir / "file.txt").read_text() == "v1"


def test_discard_interactive_abort(runner, quipu_workspace, monkeypatch):
    work_dir, _, engine = quipu_workspace
    mock_bus = MagicMock()
    monkeypatch.setattr("pyquipu.cli.commands.workspace.bus", mock_bus)

    (work_dir / "file.txt").write_text("v1")
    engine.capture_drift(engine.git_db.get_tree_hash())
    (work_dir / "file.txt").write_text("v2")

    result = runner.invoke(app, ["discard", "-w", str(work_dir)], input="n")

    assert result.exit_code == 1
    mock_bus.warning.assert_called_once_with("common.prompt.cancel")
    assert (work_dir / "file.txt").read_text() == "v2"
