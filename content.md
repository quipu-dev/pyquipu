Of course. It's crucial to validate our implementation with robust tests.

I will first correct a minor oversight in my previous implementation regarding the handling of empty history with the `--json` flag, and then I will add comprehensive tests to `test_query_commands.py`.

## [WIP] fix+test: 添加 JSON 输出功能的测试用例

### 错误分析
我之前为 `--json` 功能编写的实现代码中存在一个边缘情况处理不当的问题：当历史记录为空时，使用 `--json` 标志的命令会直接退出，导致 `stdout` 为空。一个空字符串不是有效的 JSON，这会破坏脚本的健壮性。正确的行为应该是输出一个空的 JSON 数组 (`[]`)。

### 用户需求
1.  修正 `query.py`，使其在历史记录为空时，`--json` 模式能正确输出 `[]`。
2.  为 `test_query_commands.py` 添加新的测试用例，以全面覆盖 `--json` 功能，包括：
    *   验证 JSON 输出的结构和内容是否正确。
    *   验证在 JSON 模式下 `stderr` 是否干净。
    *   验证在历史记录为空时，JSON 输出是否为 `[]`。

### 评论
测试是确保软件质量和未来可维护性的基石。通过为 `--json` 功能添加专门的测试，我们不仅能验证当前实现的正确性，还能防止未来的代码变更无意中破坏这个 API，从而保护了依赖此功能的自动化脚本。

### 目标
1.  使用 `patch_file` 修正 `query.py` 中处理空历史记录的逻辑。
2.  使用 `write_file` 完整更新 `test_query_commands.py`，加入针对 `log --json` 和 `find --json` 的新测试，并覆盖其边缘情况。

### 基本原理
我们将首先修复代码，确保其行为的正确性。然后，在测试文件中，我们将利用 `typer.testing.CliRunner` 来捕获 `stdout` 和 `stderr`。对于 JSON 测试，我们将使用 Python 的 `json` 模块来解析 `stdout` 的内容，并对其数据结构、内容和长度进行断言，从而确保 API 的输出是可靠和可预测的。

### 标签
#intent/tooling #flow/ready #priority/high #comp/cli #comp/tests #concept/ui #scope/api #scope/dx #ai/instruct #task/domain/cli #task/object/json-output #task/action/implementation #task/state/continue

---

### Script

#### Acts 1: 修正 `query.py` 中空历史的 JSON 输出

我们先修正 `log` 和 `find` 命令在历史为空时的行为，确保它们输出一个空的 JSON 数组。

~~~~~act
patch_file
packages/quipu-cli/src/quipu/cli/commands/query.py
~~~~~
~~~~~python
            if not graph:
                if not json_output:
                    typer.secho("📜 历史记录为空。", fg=typer.colors.YELLOW, err=True)
                raise typer.Exit(0)
~~~~~
~~~~~python
            if not graph:
                if json_output:
                    typer.echo("[]")
                else:
                    typer.secho("📜 历史记录为空。", fg=typer.colors.YELLOW, err=True)
                raise typer.Exit(0)
~~~~~

~~~~~act
patch_file
packages/quipu-cli/src/quipu/cli/commands/query.py
~~~~~
~~~~~python
        with engine_context(work_dir) as engine:
            if not engine.history_graph:
                if not json_output:
                    typer.secho("📜 历史记录为空。", fg=typer.colors.YELLOW, err=True)
                ctx.exit(0)

            nodes = engine.find_nodes(summary_regex=summary_regex, node_type=node_type, limit=limit)

            if not nodes:
                if not json_output:
                    typer.secho("🤷 未找到符合条件的历史节点。", fg=typer.colors.YELLOW, err=True)
                ctx.exit(0)
~~~~~
~~~~~python
        with engine_context(work_dir) as engine:
            if not engine.history_graph:
                if json_output:
                    typer.echo("[]")
                else:
                    typer.secho("📜 历史记录为空。", fg=typer.colors.YELLOW, err=True)
                ctx.exit(0)

            nodes = engine.find_nodes(summary_regex=summary_regex, node_type=node_type, limit=limit)

            if not nodes:
                if json_output:
                    typer.echo("[]")
                else:
                    typer.secho("🤷 未找到符合条件的历史节点。", fg=typer.colors.YELLOW, err=True)
                ctx.exit(0)
~~~~~

#### Acts 2: 增强 `test_query_commands.py`

现在我们用新的内容覆盖测试文件，加入对 JSON 功能的完整验证。

~~~~~act
write_file
tests/cli/test_query_commands.py
~~~~~
~~~~~python
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
    engine.create_plan_node(input_tree=hash_v1, output_tree=hash_v2, plan_content="content", summary_override="Implement feature")
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
    assert data[0]["summary"] == "Node 1"
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
    assert data[0]["summary"] == "Bugfix B"


def test_log_json_empty(runner, quipu_workspace):
    work_dir, _, _ = quipu_workspace
    result = runner.invoke(app, ["log", "--json", "-w", str(work_dir)])
    assert result.exit_code == 0
    assert result.stderr.strip() == ""
    assert result.stdout.strip() == "[]"
~~~~~

### 下一步建议
我们已经成功地为 `--json` 功能添加了实现和测试。现在这个宏观任务已经完成，是时候将所有相关的变更提交到版本控制中了。

如果你同意，我将生成一个 `[COMMIT]` 计划来结束这个“实现 JSON 输出”的宏观任务。
