import json
from unittest.mock import MagicMock, call
from quipu.cli.main import app


def test_log_empty(runner, quipu_workspace, monkeypatch):
    work_dir, _, _ = quipu_workspace
    mock_bus = MagicMock()
    monkeypatch.setattr("quipu.cli.commands.query.bus", mock_bus)

    result = runner.invoke(app, ["log", "-w", str(work_dir)])
    assert result.exit_code == 0
    mock_bus.info.assert_called_once_with("query.info.emptyHistory")


def test_log_output(runner, quipu_workspace, monkeypatch):
    work_dir, _, engine = quipu_workspace
    mock_bus = MagicMock()
    monkeypatch.setattr("quipu.cli.commands.query.bus", mock_bus)

    (work_dir / "f1").touch()
    node1 = engine.capture_drift(engine.git_db.get_tree_hash(), message="Node 1")
    (work_dir / "f2").touch()
    node2 = engine.capture_drift(engine.git_db.get_tree_hash(), message="Node 2")

    result = runner.invoke(app, ["log", "-w", str(work_dir)])
    assert result.exit_code == 0
    mock_bus.info.assert_called_once_with("query.log.ui.header")
    # The log is in reverse chronological order, so Node 2 comes first.
    assert "Node 2" in mock_bus.data.call_args_list[0].args[0]
    assert "Node 1" in mock_bus.data.call_args_list[1].args[0]


def test_find_command(runner, quipu_workspace, monkeypatch):
    work_dir, _, engine = quipu_workspace
    mock_bus = MagicMock()
    monkeypatch.setattr("quipu.cli.commands.query.bus", mock_bus)

    (work_dir / "f1").touch()
    hash_v1 = engine.git_db.get_tree_hash()
    engine.capture_drift(hash_v1, message="Fix bug")
    (work_dir / "f2").touch()
    hash_v2 = engine.git_db.get_tree_hash()
    engine.create_plan_node(
        input_tree=hash_v1, output_tree=hash_v2, plan_content="content", summary_override="Implement feature"
    )

    result = runner.invoke(app, ["find", "-s", "Fix", "-w", str(work_dir)])
    assert result.exit_code == 0
    mock_bus.info.assert_called_once_with("query.find.ui.header")
    mock_bus.data.assert_called_once()
    assert "Fix bug" in mock_bus.data.call_args.args[0]


def test_log_json_output(runner, quipu_workspace, monkeypatch):
    work_dir, _, engine = quipu_workspace
    mock_bus = MagicMock()
    monkeypatch.setattr("quipu.cli.commands.query.bus", mock_bus)

    (work_dir / "f1").touch()
    engine.capture_drift(engine.git_db.get_tree_hash(), message="Node 1")

    result = runner.invoke(app, ["log", "--json", "-w", str(work_dir)])
    assert result.exit_code == 0
    mock_bus.data.assert_called_once()

    # Verify the data passed to bus.data is valid JSON with expected content
    json_data = json.loads(mock_bus.data.call_args.args[0])
    assert isinstance(json_data, list)
    assert len(json_data) == 1
    assert "Node 1" in json_data[0]["summary"]


def test_find_json_output(runner, quipu_workspace, monkeypatch):
    work_dir, _, engine = quipu_workspace
    mock_bus = MagicMock()
    monkeypatch.setattr("quipu.cli.commands.query.bus", mock_bus)

    (work_dir / "f1").touch()
    engine.capture_drift(engine.git_db.get_tree_hash(), message="Feature A")
    (work_dir / "f2").touch()
    engine.capture_drift(engine.git_db.get_tree_hash(), message="Bugfix B")

    result = runner.invoke(app, ["find", "--summary", "Bugfix", "--json", "-w", str(work_dir)])
    assert result.exit_code == 0
    mock_bus.data.assert_called_once()

    json_data = json.loads(mock_bus.data.call_args.args[0])
    assert isinstance(json_data, list)
    assert len(json_data) == 1
    assert "Bugfix B" in json_data[0]["summary"]


def test_log_json_empty(runner, quipu_workspace, monkeypatch):
    work_dir, _, _ = quipu_workspace
    mock_bus = MagicMock()
    monkeypatch.setattr("quipu.cli.commands.query.bus", mock_bus)

    result = runner.invoke(app, ["log", "--json", "-w", str(work_dir)])
    assert result.exit_code == 0
    mock_bus.data.assert_called_once_with("[]")
