from quipu.cli.main import app


def test_save_clean_workspace(runner, quipu_workspace):
    work_dir, _, engine = quipu_workspace

    # 创建一个初始状态
    (work_dir / "file.txt").write_text("v1")
    engine.capture_drift(engine.git_db.get_tree_hash(), message="Initial")

    # 无变更时执行 save
    result = runner.invoke(app, ["save", "-w", str(work_dir)])
    assert result.exit_code == 0
    assert "无需创建快照" in result.stderr


def test_save_with_changes(runner, quipu_workspace):
    work_dir, _, _ = quipu_workspace

    # 制造变更
    (work_dir / "file.txt").write_text("v2")

    result = runner.invoke(app, ["save", "My Snapshot", "-w", str(work_dir)])
    assert result.exit_code == 0, f"Save command failed with stderr: {result.stderr}"
    assert "快照已保存" in result.stderr
    assert "(My Snapshot)" in result.stderr

    # 验证历史记录已增加，通过 log 命令
    log_result = runner.invoke(app, ["log", "-w", str(work_dir)])
    assert log_result.exit_code == 0
    # 验证元信息在 stderr
    assert "--- Quipu History Log ---" in log_result.stderr
    # 验证数据在 stdout
    assert "My Snapshot" in log_result.stdout


def test_discard_changes(runner, quipu_workspace):
    work_dir, _, engine = quipu_workspace

    # 初始状态 v1
    (work_dir / "file.txt").write_text("v1")
    initial_node = engine.capture_drift(engine.git_db.get_tree_hash())

    # 制造脏状态 v2
    (work_dir / "file.txt").write_text("v2")

    # 执行 discard (带 force)
    result = runner.invoke(app, ["discard", "-f", "-w", str(work_dir)])
    assert result.exit_code == 0
    assert "已成功恢复" in result.stderr

    # 验证文件回滚
    assert (work_dir / "file.txt").read_text() == "v1"


def test_discard_interactive_abort(runner, quipu_workspace):
    work_dir, _, engine = quipu_workspace

    (work_dir / "file.txt").write_text("v1")
    engine.capture_drift(engine.git_db.get_tree_hash())
    (work_dir / "file.txt").write_text("v2")

    # 模拟输入 'n'
    result = runner.invoke(app, ["discard", "-w", str(work_dir)], input="n")
    assert result.exit_code == 1
    assert "操作已取消" in result.stderr
    assert (work_dir / "file.txt").read_text() == "v2"
