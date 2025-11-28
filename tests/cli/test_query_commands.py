import json
from quipu.cli.main import app


def test_log_empty(runner, quipu_workspace):
    work_dir, _, _ = quipu_workspace
    result = runner.invoke(app, ["log", "-w", str(work_dir)])
    assert result.exit_code == 0
    assert "历史记录为空" in result.stderr


def test_log_output(runner, quipu_workspace):
    work_dir, _, engine = quipu_workspace
    (work_dir / "f1").touch()
    engine.capture_drift(engine.git_db.get_tree_hash(), message="Node 1")
    (work_dir / "f2").touch()
    engine.capture_drift(engine.git_db.get_tree_hash(), message="Node 2")
    result = runner.invoke(app, ["log", "-w", str(work_dir)])
    assert result.exit_code == 0
    assert "--- Quipu History Log ---" in result.stderr
    assert "Node 1" in result.stdout
    assert "Node 2" in result.stdout
    assert "Node 1" not in result.stderr


def test_find_command(runner, quipu_workspace):
    work_dir, _, engine = quipu_workspace
    (work_dir / "f1").touch()
    hash_v1 = engine.git_db.get_tree_hash()
    engine.capture_drift(hash_v1, message="Fix bug")
    (work_dir / "f2").touch()
    hash_v2 = engine.git_db.get_tree_hash()
    engine.create_plan_node(
        input_tree=hash_v1, output_tree=hash_v2, plan_content="content", summary_override="Implement feature"
    )
    result = runner.invoke(app, ["find", "-s", "Fix", "-w", str(work_dir)])
    assert "--- 查找结果 ---" in result.stderr
    assert "Fix bug" in result.stdout
    assert "Implement feature" not in result.stdout
    assert "Fix bug" not in result.stderr


def test_log_json_output(runner, quipu_workspace):
    work_dir, _, engine = quipu_workspace
    (work_dir / "f1").touch()
    engine.capture_drift(engine.git_db.get_tree_hash(), message="Node 1")
    result = runner.invoke(app, ["log", "--json", "-w", str(work_dir)])
    assert result.exit_code == 0
    assert result.stderr.strip() == ""
    data = json.loads(result.stdout)
    assert isinstance(data, list)
    assert len(data) == 1
    assert "Node 1" in data[0]["summary"]  # Use 'in' for robust check
    assert "output_tree" in data[0]
    assert "short_hash" in data[0]
    assert "parent" not in data[0]  # Check for excluded field


def test_find_json_output(runner, quipu_workspace):
    work_dir, _, engine = quipu_workspace
    (work_dir / "f1").touch()
    engine.capture_drift(engine.git_db.get_tree_hash(), message="Feature A")
    (work_dir / "f2").touch()
    engine.capture_drift(engine.git_db.get_tree_hash(), message="Bugfix B")
    result = runner.invoke(app, ["find", "--summary", "Bugfix", "--json", "-w", str(work_dir)])
    assert result.exit_code == 0
    assert result.stderr.strip() == ""
    data = json.loads(result.stdout)
    assert isinstance(data, list)
    assert len(data) == 1
    assert "Bugfix B" in data[0]["summary"]  # Use 'in' for robust check


def test_log_json_empty(runner, quipu_workspace):
    work_dir, _, _ = quipu_workspace
    result = runner.invoke(app, ["log", "--json", "-w", str(work_dir)])
    assert result.exit_code == 0
    assert result.stderr.strip() == ""
    assert result.stdout.strip() == "[]"
