import json
from unittest.mock import MagicMock

from pyquipu.cli.main import app


def test_log_empty(runner, quipu_workspace, monkeypatch):
    work_dir, _, _ = quipu_workspace
    mock_bus = MagicMock()
    monkeypatch.setattr("pyquipu.cli.commands.query.bus", mock_bus)

    result = runner.invoke(app, ["log", "-w", str(work_dir)])
    assert result.exit_code == 0
    mock_bus.info.assert_called_once_with("query.info.emptyHistory")


def test_log_output(runner, quipu_workspace, monkeypatch):
    work_dir, _, engine = quipu_workspace
    mock_bus = MagicMock()
    monkeypatch.setattr("pyquipu.cli.commands.query.bus", mock_bus)

    (work_dir / "f1").touch()
    engine.capture_drift(engine.git_db.get_tree_hash(), message="Node 1")
    (work_dir / "f2").touch()
    engine.capture_drift(engine.git_db.get_tree_hash(), message="Node 2")

    result = runner.invoke(app, ["log", "-w", str(work_dir)])
    assert result.exit_code == 0
    mock_bus.info.assert_called_once_with("query.log.ui.header")
    # The log is in reverse chronological order, so Node 2 comes first.
    assert "Node 2" in mock_bus.data.call_args_list[0].args[0]
    assert "Node 1" in mock_bus.data.call_args_list[1].args[0]


def test_find_command(runner, quipu_workspace, monkeypatch):
    work_dir, _, engine = quipu_workspace
    mock_bus = MagicMock()
    monkeypatch.setattr("pyquipu.cli.commands.query.bus", mock_bus)

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
    monkeypatch.setattr("pyquipu.cli.commands.query.bus", mock_bus)

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
    monkeypatch.setattr("pyquipu.cli.commands.query.bus", mock_bus)

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
    monkeypatch.setattr("pyquipu.cli.commands.query.bus", mock_bus)

    result = runner.invoke(app, ["log", "--json", "-w", str(work_dir)])
    assert result.exit_code == 0
    mock_bus.data.assert_called_once_with("[]")


def test_log_filtering(runner, quipu_workspace, monkeypatch):
    """Test limit and time filtering logic for log command."""
    work_dir, _, engine = quipu_workspace
    mock_bus = MagicMock()
    monkeypatch.setattr("pyquipu.cli.commands.query.bus", mock_bus)

    # Create 3 nodes
    (work_dir / "f1").touch()
    engine.capture_drift(engine.git_db.get_tree_hash(), message="Node 1")
    (work_dir / "f2").touch()
    engine.capture_drift(engine.git_db.get_tree_hash(), message="Node 2")
    (work_dir / "f3").touch()
    engine.capture_drift(engine.git_db.get_tree_hash(), message="Node 3")

    # 1. Test Limit
    result = runner.invoke(app, ["log", "-n", "1", "-w", str(work_dir)])
    assert result.exit_code == 0
    # Should only print header + 1 node
    assert mock_bus.data.call_count == 1
    assert "Node 3" in mock_bus.data.call_args_list[0].args[0]  # Newest

    # 2. Test Filtering Result Empty
    mock_bus.reset_mock()
    # Using a future date
    result = runner.invoke(app, ["log", "--since", "2099-01-01 00:00", "-w", str(work_dir)])
    assert result.exit_code == 0
    mock_bus.info.assert_called_with("query.info.noResults")


def test_log_reachable_only(runner, quipu_workspace, monkeypatch):
    """Test --reachable-only filtering for the log command."""
    work_dir, _, engine = quipu_workspace
    mock_bus = MagicMock()
    monkeypatch.setattr("pyquipu.cli.commands.query.bus", mock_bus)

    # History: root -> A -> B (HEAD)
    #               \\-> C (unreachable)
    (work_dir / "f_a").touch()
    h_a = engine.git_db.get_tree_hash()
    node_a = engine.capture_drift(h_a, "Node A")

    (work_dir / "f_b").touch()
    h_b = engine.git_db.get_tree_hash()
    engine.capture_drift(h_b, "Node B")

    engine.visit(node_a.output_tree)
    (work_dir / "f_c").touch()
    h_c = engine.git_db.get_tree_hash()
    engine.capture_drift(h_c, "Node C")

    # Checkout back to B to set it as current HEAD
    engine.visit(h_b)

    result = runner.invoke(app, ["log", "--reachable-only", "-w", str(work_dir)])
    assert result.exit_code == 0

    output = "".join(call.args[0] for call in mock_bus.data.call_args_list)
    assert "Node B" in output  # HEAD is reachable
    assert "Node A" in output  # Ancestor is reachable
    assert "Node C" not in output  # Unrelated branch is not reachable
