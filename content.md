好的，我将生成更新测试用例的计划。

## [WIP] test: 更新查询命令测试以验证 stdout 和 stderr 分离

### 用户需求
根据上一步的代码修改，需要更新 `tests/cli/test_query_commands.py` 文件中的测试用例。新的测试必须能够区分标准输出 (`stdout`) 和标准错误 (`stderr`)，以验证 `log` 和 `find` 命令现在是否将数据正确输出到 `stdout`，同时将元信息保留在 `stderr`。

### 评论
更新测试是确保软件质量的关键步骤。这些修改将使我们的测试套件更加精确和健壮，能够捕获与输出流相关的回归错误，并正式确认 CLI 工具的行为符合预期。

### 目标
1.  重写 `tests/cli/test_query_commands.py` 文件。
2.  在 `test_log_output` 中，断言元信息在 `stderr` 中，而节点数据在 `stdout` 中。
3.  在 `test_find_command` 中，同样断言元信息在 `stderr` 中，而匹配到的节点数据在 `stdout` 中。

### 基本原理
通过使用 `typer.testing.CliRunner`，我们可以检查 `result.stdout` 和 `result.stderr` 属性。我们将修改测试断言，从之前只检查 `result.stderr` 改为分别检查这两个输出流，从而精确验证命令的输出行为是否符合 Unix 管道规范。

### 标签
#intent/tooling #flow/ready #priority/high #comp/tests #concept/ui #scope/dx #ai/instruct #task/state/continue

---

### Script

#### Acts 1: 重写查询命令的测试文件

我们将用包含新断言逻辑的完整内容覆盖现有的测试文件，以确保测试的准确性。

~~~~~act
write_file
tests/cli/test_query_commands.py
~~~~~
~~~~~python
from quipu.cli.main import app


def test_log_empty(runner, quipu_workspace):
    work_dir, _, _ = quipu_workspace
    result = runner.invoke(app, ["log", "-w", str(work_dir)])
    assert result.exit_code == 0
    assert "历史记录为空" in result.stderr


def test_log_output(runner, quipu_workspace):
    work_dir, _, engine = quipu_workspace

    # 创建一些历史
    (work_dir / "f1").touch()
    engine.capture_drift(engine.git_db.get_tree_hash(), message="Node 1")

    (work_dir / "f2").touch()
    engine.capture_drift(engine.git_db.get_tree_hash(), message="Node 2")

    result = runner.invoke(app, ["log", "-w", str(work_dir)])
    assert result.exit_code == 0

    # 验证元数据在 stderr
    assert "--- Quipu History Log ---" in result.stderr

    # 验证数据在 stdout
    assert "Node 1" in result.stdout
    assert "Node 2" in result.stdout
    assert "[CAPTURE]" in result.stdout

    # 验证数据不在 stderr
    assert "Node 1" not in result.stderr


def test_find_command(runner, quipu_workspace):
    work_dir, _, engine = quipu_workspace

    (work_dir / "f1").touch()
    capture_node = engine.capture_drift(engine.git_db.get_tree_hash(), message="Fix bug")
    hash_v1 = capture_node.output_tree

    (work_dir / "f2").touch()
    hash_v2 = engine.git_db.get_tree_hash()
    engine.create_plan_node(
        input_tree=hash_v1,
        output_tree=hash_v2,
        plan_content="content",
        summary_override="Implement feature",
    )

    # 查找 "Fix"
    result = runner.invoke(app, ["find", "-s", "Fix", "-w", str(work_dir)])
    assert "--- 查找结果 ---" in result.stderr
    assert "Fix bug" in result.stdout
    assert "Implement feature" not in result.stdout
    assert "Fix bug" not in result.stderr

    # 查找类型 "plan"
    result_type = runner.invoke(app, ["find", "-t", "plan", "-w", str(work_dir)])
    assert "--- 查找结果 ---" in result_type.stderr
    assert "Implement feature" in result_type.stdout
    assert "Fix bug" not in result_type.stdout
    assert "Implement feature" not in result_type.stderr
~~~~~

### 下一步建议
我们已经成功地：
1.  修复了 `query.py` 中的输出流问题。
2.  更新了测试用例以验证该修复。

现在，这个逻辑单元已经完整，是时候将其作为一个 `[COMMIT]` 提交到版本控制中了。如果你同意，我将生成一个包含 `git add` 和 `git commit` 指令的最终计划。
