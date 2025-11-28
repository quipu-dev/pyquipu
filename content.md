Of course. The test failures are a direct and expected consequence of our previous refactoring. I will now fix the integration tests to align with the new, correct behavior of separating `stdout` and `stderr`.

## [WIP] test: 修复因输出流重构而失败的集成测试

### 错误分析
正如预期的那样，之前将 `log`, `find`, 和 `--list-acts` 的数据输出重定向到 `stdout` 的改动，导致了依赖旧行为（所有输出都在 `stderr`）的集成测试失败。这些测试现在错误地在 `stderr` 中查找本应出现在 `stdout` 的数据，从而导致断言失败。

### 用户需求
更新 `tests/integration/test_cli_workflow.py` 和 `tests/integration/test_storage_selection.py` 中的测试用例，使其断言逻辑与当前 `stdout` (数据) / `stderr` (元信息) 分离的实现保持一致。

### 评论
这是一次必要的测试维护。通过修复这些测试，我们不仅使测试套件恢复了其作为代码质量安全网的功能，而且还使其更加精确：它们现在能够分别验证数据流和元信息流，从而使测试本身更加健壮和有意义。

### 目标
1.  修改 `test_cli_workflow.py` 中的 `test_cli_list_acts`，使其在 `result.stdout` 中检查指令列表。
2.  修改 `test_storage_selection.py` 中的所有失败测试，将对 `log` 和 `find` 命令数据输出的断言从检查 `result.stderr` 改为检查 `result.stdout`。
3.  在所有修改的测试中，酌情加入对 `result.stderr` 中元信息的断言，以增强测试的完整性。

### 基本原理
我们将对所有失败的测试应用统一的修复模式：
-   **数据断言**: 所有对核心数据（如节点摘要、指令名称）的检查，都将明确指向 `result.stdout`。
-   **元信息断言**: 所有对标题、提示等辅助信息的检查，都将明确指向 `result.stderr`。

### 标签
#intent/fix #flow/ready #priority/high #comp/tests #scope/dx #ai/instruct #task/domain/cli #task/object/json-output #task/action/implementation #task/state/continue

---

### Script

#### Acts 1: 修正 `tests/integration/test_cli_workflow.py`

我们将更新 `TestCLIWrapper::test_cli_list_acts` 以匹配新的输出行为。

~~~~~act
write_file
tests/integration/test_cli_workflow.py
~~~~~
~~~~~python
import pytest
import logging
from pathlib import Path
from typer.testing import CliRunner
from quipu.cli.controller import run_quipu, QuipuResult
from quipu.cli.main import app
from quipu.core.executor import Executor
from quipu.acts.basic import register as register_basic

# --- Fixtures ---


@pytest.fixture(autouse=True)
def reset_logging():
    """
    每次测试前后重置 logging handlers。
    这是解决 CliRunner I/O Error 的关键，防止 handler 持有已关闭的流。
    """
    root = logging.getLogger()
    # Teardown: 清理所有 handlers
    yield
    for h in root.handlers[:]:
        root.removeHandler(h)
        h.close()


@pytest.fixture
def workspace(tmp_path):
    """准备一个带 git 的工作区"""
    ws = tmp_path / "ws"
    ws.mkdir()

    # 初始化 git (Engine 需要)
    import subprocess

    subprocess.run(["git", "init"], cwd=ws, check=True, capture_output=True)
    # 设置 user 避免 commit 报错
    subprocess.run(["git", "config", "user.email", "test@quipu.dev"], cwd=ws, check=True)
    subprocess.run(["git", "config", "user.name", "Quipu Test"], cwd=ws, check=True)

    return ws


# --- 1. Controller Layer Tests (The Core) ---
# 这些测试直接验证业务逻辑，不涉及 CLI 参数解析干扰


class TestController:
    def test_run_quipu_success(self, workspace):
        """测试正常执行流程"""
        from quipu.cli.factory import create_engine

        plan = """
```act
write_file
```
```path
hello.txt
```
```content
Hello Quipu
```
"""
        result = run_quipu(content=plan, work_dir=workspace, yolo=True)

        assert result.success is True
        assert result.exit_code == 0
        assert (workspace / "hello.txt").exists()

        # 验证 Engine 是否生成了 Plan 节点 (后端无关)
        engine = create_engine(workspace)
        nodes = engine.reader.load_all_nodes()
        assert len(nodes) >= 1

    def test_run_quipu_execution_error(self, workspace):
        """测试执行期间的预期错误 (如文件不存在)"""
        # 试图追加到一个不存在的文件
        plan = """
```act
append_file
```
```path
ghost.txt
```
```content
boo
```
"""
        result = run_quipu(content=plan, work_dir=workspace, yolo=True)

        assert result.success is False
        assert result.exit_code == 1
        assert "文件不存在" in result.message

    def test_run_quipu_empty_plan(self, workspace):
        """测试无有效指令"""
        plan = "Just some text, no acts."

        result = run_quipu(content=plan, work_dir=workspace, yolo=True)

        assert result.success is False  # 视为非成功状态（虽然不是错误，但任务未完成）
        assert result.exit_code == 0  # 但退出码为 0，不报错
        assert "未找到任何有效的" in result.message


# --- 2. CLI Layer Tests (The Shell) ---
# 这些测试验证 main.py 是否正确解析参数并传递给 Controller
# 由于 Controller 已经测过了，这里可以用 mock 来隔离

runner = CliRunner()


class TestCLIWrapper:
    def test_cli_help(self):
        """测试 --help"""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "Quipu" in result.stdout

    def test_cli_file_input(self, tmp_path):
        """测试从文件读取输入"""
        plan_file = tmp_path / "plan.md"
        plan_file.write_text("```act\nend\n```", encoding="utf-8")

        # 我们不需要真的跑 git，只要看是否尝试运行即可
        # 如果 work-dir 不是 git repo，Controller 会报错或 Engine 初始化失败
        # 这里为了简单，我们让它在一个临时目录跑，预期可能是 1 (Engine init fail) 或 0 (如果 Engine 容错好)
        # 关键是不要由 CliRunner 抛出 ValueError

        # 初始化一个最小 git repo 避免 Engine 报错干扰 CLI 测试
        import subprocess

        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)

        result = runner.invoke(app, ["run", str(plan_file), "--work-dir", str(tmp_path), "--yolo"])

        # 只要不是 Python traceback 导致的 Crash (exit_code != 0 and not handled) 就行
        # 我们的 Controller 会捕获异常返回 exit_code 1
        # 这里的 'end' act 是一个无害操作，应该返回 0
        assert result.exit_code == 0
        assert result.exception is None

    def test_cli_no_input_shows_usage(self, monkeypatch, tmp_path):
        """测试无输入时显示用法"""
        # 1. 临时修改 run 命令模块中的默认入口文件引用，防止读取当前目录下的 o.md
        # 注意：必须 patch 'run' 模块，因为该模块通过 'from ... import' 引入了常量
        from quipu.cli.commands import run

        monkeypatch.setattr(run, "DEFAULT_ENTRY_FILE", tmp_path / "non_existent.md")

        # 2. 同时确保 STDIN 不是 TTY，也不是管道（模拟纯交互式空运行）
        result = runner.invoke(app, ["run"])  # 无参数，无管道

        assert result.exit_code == 0
        assert "用法示例" in result.stderr

    def test_cli_list_acts(self):
        """测试 --list-acts"""
        # --list-acts 是 'run' 命令的一个选项
        result = runner.invoke(app, ["run", "--list-acts"])
        assert result.exit_code == 0
        assert "可用的 Quipu 指令列表" in result.stderr
        assert "write_file" in result.stdout

    def test_cli_run_file_not_found(self):
        """测试 `run` 命令在文件不存在时的行为"""
        result = runner.invoke(app, ["run", "non_existent_plan.md"])
        assert result.exit_code == 1
        assert "错误: 找不到指令文件" in result.stderr

    def test_cli_save_on_clean_workspace(self, workspace):
        """测试 `save` 命令在工作区干净时的行为"""
        result = runner.invoke(app, ["save", "-w", str(workspace)])
        assert result.exit_code == 0
        assert "工作区状态未发生变化" in result.stderr

    def test_cli_discard_no_history(self, workspace):
        """测试 `discard` 命令在没有历史记录时的行为"""
        result = runner.invoke(app, ["discard", "-f", "-w", str(workspace)])
        assert result.exit_code == 1
        assert "找不到任何历史记录" in result.stderr


class TestCheckoutCLI:
    @pytest.fixture
    def populated_workspace(self, workspace):
        """
        Create a workspace with two distinct, non-overlapping history nodes.
        State A contains only a.txt.
        State B contains only b.txt.
        This fixture is backend-agnostic.
        """
        from quipu.cli.factory import create_engine

        # State A: Create a.txt
        plan_a = "```act\nwrite_file a.txt\n```\n```content\nState A\n```"
        run_quipu(content=plan_a, work_dir=workspace, yolo=True)

        engine_after_a = create_engine(workspace)
        nodes_after_a = sorted(engine_after_a.reader.load_all_nodes(), key=lambda n: n.timestamp)
        node_a = nodes_after_a[-1]
        hash_a = node_a.output_tree

        # Manually create State B by removing a.txt and adding b.txt
        (workspace / "a.txt").unlink()
        plan_b = "```act\nwrite_file b.txt\n```\n```content\nState B\n```"
        run_quipu(content=plan_b, work_dir=workspace, yolo=True)

        engine_after_b = create_engine(workspace)
        nodes_after_b = sorted(engine_after_b.reader.load_all_nodes(), key=lambda n: n.timestamp)
        node_b = nodes_after_b[-1]
        hash_b = node_b.output_tree

        return workspace, hash_a, hash_b

    def test_cli_checkout_success(self, populated_workspace):
        """Test checking out from State B to State A."""
        workspace, hash_a, hash_b = populated_workspace

        # Pre-flight check: we are in state B
        assert not (workspace / "a.txt").exists()
        assert (workspace / "b.txt").exists()

        result = runner.invoke(app, ["checkout", hash_a[:8], "--work-dir", str(workspace), "--force"])

        assert result.exit_code == 0
        assert "✅ 已成功切换到状态" in result.stderr

        # Post-flight check: we are now in state A
        assert (workspace / "a.txt").exists()
        assert (workspace / "a.txt").read_text() == "State A"
        assert not (workspace / "b.txt").exists()

    def test_cli_checkout_with_safety_capture(self, populated_workspace):
        """Test that a dirty state is captured before checkout."""
        from quipu.cli.factory import create_engine

        workspace, hash_a, hash_b = populated_workspace

        # Make the workspace dirty
        (workspace / "c_dirty.txt").write_text("uncommitted change")

        # Get node count via the storage-agnostic reader interface
        engine_before = create_engine(workspace)
        num_nodes_before = len(engine_before.reader.load_all_nodes())

        result = runner.invoke(app, ["checkout", hash_a[:8], "--work-dir", str(workspace), "--force"])

        assert result.exit_code == 0, result.stderr
        assert "⚠️  检测到当前工作区存在未记录的变更" in result.stderr

        # Get node count again after the operation
        engine_after = create_engine(workspace)
        num_nodes_after = len(engine_after.reader.load_all_nodes())
        assert num_nodes_after == num_nodes_before + 1, "A new capture node should have been created"

        # Check final state is correct
        assert (workspace / "a.txt").exists()
        assert not (workspace / "c_dirty.txt").exists()

    def test_cli_checkout_not_found(self, populated_workspace):
        """Test checkout with a non-existent hash."""
        workspace, _, _ = populated_workspace

        result = runner.invoke(app, ["checkout", "deadbeef", "--work-dir", str(workspace), "--force"])

        assert result.exit_code == 1
        assert "❌ 错误: 未找到 output_tree 哈希前缀为" in result.stderr

    def test_cli_checkout_already_on_state(self, populated_workspace):
        """Test checking out to the current state does nothing."""
        workspace, _, hash_b = populated_workspace

        result = runner.invoke(app, ["checkout", hash_b[:8], "--work-dir", str(workspace), "--force"])

        assert result.exit_code == 0
        assert "✅ 工作区已处于目标状态" in result.stderr
~~~~~

#### Acts 2: 修正 `tests/integration/test_storage_selection.py`

我们将更新 `TestGitObjectWorkflow` 和 `TestFindCliCommand` 中的所有测试用例。

~~~~~act
write_file
tests/integration/test_storage_selection.py
~~~~~
~~~~~python
import pytest
import subprocess
from pathlib import Path
from typer.testing import CliRunner

from quipu.cli.main import app

# A simple plan that creates one file
PLAN_A = """
```act
write_file a.txt
```
```content
File A content
```
"""

# A simple plan that creates a different file
PLAN_B = """
```act
write_file b.txt
```
```content
File B content
```
"""


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def git_workspace(tmp_path: Path) -> Path:
    """Creates a temporary directory and initializes it as a Git repository."""
    ws = tmp_path / "ws"
    ws.mkdir()
    subprocess.run(["git", "init"], cwd=ws, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@quipu.dev"], cwd=ws, check=True)
    subprocess.run(["git", "config", "user.name", "Quipu Test"], cwd=ws, check=True)
    return ws


def git_rev_parse(ref: str, cwd: Path) -> str:
    """Helper to get the hash of a git ref."""
    result = subprocess.run(["git", "rev-parse", ref], cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


class TestStorageSelection:
    """Tests the automatic detection and selection of storage backends."""

    def test_defaults_to_git_object_storage_on_new_project(self, runner, git_workspace):
        """
        SCENARIO: A user starts a new project.
        EXPECTATION: The system should use the new Git Object storage by default.
        """
        # Action: Run a plan in the new workspace
        result = runner.invoke(app, ["run", "-y", "-w", str(git_workspace)], input=PLAN_A)

        assert result.exit_code == 0, result.stderr

        # Verification
        assert (git_workspace / "a.txt").exists()

        # 1. A new head ref should exist in the correct namespace
        get_heads_cmd = ["git", "for-each-ref", "--format=%(objectname)", "refs/quipu/local/heads/"]
        heads = subprocess.check_output(get_heads_cmd, cwd=git_workspace, text=True).strip().splitlines()
        assert len(heads) >= 1, "A git ref for quipu history should have been created."

        # 2. Old directory should NOT exist
        legacy_history_dir = git_workspace / ".quipu" / "history"
        assert not legacy_history_dir.exists(), "Legacy file system history should not be used."

    def test_continues_using_git_object_storage(self, runner, git_workspace):
        """
        SCENARIO: A user runs quipu in a project already using the new format.
        EXPECTATION: The system should continue using the Git Object storage.
        """
        get_all_heads_cmd = ["git", "for-each-ref", "--format=%(objectname)", "refs/quipu/local/heads/"]

        # Setup: Run one command to establish the new format
        runner.invoke(app, ["run", "-y", "-w", str(git_workspace)], input=PLAN_A)
        heads_after_a = set(subprocess.check_output(get_all_heads_cmd, cwd=git_workspace, text=True).strip().splitlines())
        assert len(heads_after_a) == 1
        commit_hash_a = heads_after_a.pop()

        # Action: Run a second command
        result = runner.invoke(app, ["run", "-y", "-w", str(git_workspace)], input=PLAN_B)
        assert result.exit_code == 0, result.stderr

        # Verification
        heads_after_b = set(subprocess.check_output(get_all_heads_cmd, cwd=git_workspace, text=True).strip().splitlines())
        new_heads = heads_after_b - {commit_hash_a}
        
        # 1. A new head should be created
        assert len(new_heads) == 1, "A new history head was not created after the second run"
        commit_hash_b = new_heads.pop()

        # 2. The parent of the new commit should be the old one
        commit_data = subprocess.check_output(["git", "cat-file", "-p", commit_hash_b], cwd=git_workspace, text=True)
        parent_line = [line for line in commit_data.splitlines() if line.startswith("parent ")]
        assert len(parent_line) == 1, "New commit should have exactly one parent"
        parent_hash = parent_line[0].split(" ")[1]
        assert parent_hash == commit_hash_a, "The new commit should be parented to the previous one."

        # 3. No legacy files should be created
        assert not (git_workspace / ".quipu" / "history").exists()


class TestGitObjectWorkflow:
    """End-to-end tests for core commands using the Git Object backend."""

    def test_full_workflow_with_git_object_storage(self, runner, git_workspace):
        # 1. Run a plan to create state A
        res_run = runner.invoke(app, ["run", "-y", "-w", str(git_workspace)], input=PLAN_A)
        assert res_run.exit_code == 0
        assert (git_workspace / "a.txt").exists()

        # 2. Manually add a file and use `save` to create state B
        (git_workspace / "b.txt").write_text("manual change")
        res_save = runner.invoke(app, ["save", "add b.txt", "-w", str(git_workspace)])
        assert res_save.exit_code == 0
        assert "快照已保存" in res_save.stderr

        # 3. Use `log` to check history
        res_log = runner.invoke(app, ["log", "-w", str(git_workspace)])
        assert res_log.exit_code == 0
        assert "--- Quipu History Log ---" in res_log.stderr
        assert "add b.txt" in res_log.stdout  # Check data in stdout
        assert "Write: a.txt" in res_log.stdout  # Check data in stdout

        # 4. Use `find` and `checkout` to go back to state A
        res_find = runner.invoke(app, ["find", "--summary", "Write: a.txt", "-w", str(git_workspace)])
        assert res_find.exit_code == 0
        assert "--- 查找结果 ---" in res_find.stderr

        # Parse the output to get the full hash
        found_line = res_find.stdout.strip().splitlines()[-1]  # Get data from stdout
        parts = found_line.split()
        output_tree_a = parts[3]

        assert len(output_tree_a) == 40

        res_checkout = runner.invoke(app, ["checkout", output_tree_a[:8], "-f", "-w", str(git_workspace)])
        assert res_checkout.exit_code == 0, res_checkout.stderr

        # Verification of state A
        assert (git_workspace / "a.txt").exists()
        assert not (git_workspace / "b.txt").exists()


class TestFindCliCommand:
    @pytest.fixture
    def populated_workspace(self, git_workspace, runner):  # Correctly inject runner
        # Run plan A
        runner.invoke(app, ["run", "-y", "-w", str(git_workspace)], input=PLAN_A)
        # Run save
        (git_workspace / "change.txt").write_text("manual")
        runner.invoke(app, ["save", "Snapshot 1", "-w", str(git_workspace)])
        return git_workspace

    def test_find_cli_by_type(self, runner, populated_workspace):
        result = runner.invoke(app, ["find", "--type", "plan", "-w", str(populated_workspace)])
        assert result.exit_code == 0
        assert "--- 查找结果 ---" in result.stderr
        assert "[PLAN]" in result.stdout
        assert "[CAPTURE]" not in result.stdout
        assert "Write: a.txt" in result.stdout

    def test_find_cli_by_summary(self, runner, populated_workspace):
        result = runner.invoke(app, ["find", "-s", "snapshot", "-w", str(populated_workspace)])
        assert result.exit_code == 0
        assert "--- 查找结果 ---" in result.stderr
        assert "[CAPTURE]" in result.stdout
        assert "Snapshot 1" in result.stdout
        assert "[PLAN]" not in result.stdout

    def test_find_cli_no_results(self, runner, populated_workspace):
        result = runner.invoke(app, ["find", "-s", "non-existent", "-w", str(populated_workspace)])
        assert result.exit_code == 0
        assert "未找到符合条件" in result.stderr
~~~~~

### 下一步建议
我们已经修复了所有已知的、因输出流重构而失败的测试。现在，请再次运行完整的测试套件。如果所有测试都通过，我将为你生成最终的 `[COMMIT]` 计划，以原子方式提交 `--json` 功能、其测试以及所有相关的测试修复。
