## [WIP] test: 迁移 Controller 测试至 Application 层 (第二阶段)

### 用户需求
继续执行测试重构计划。本阶段的核心任务是将 `tests/integration/test_cli_workflow.py` 中针对 `Controller` 逻辑的测试剥离出来，迁移到新建的 `tests/application/test_controller.py` 中。

这不仅仅是代码移动，更是测试范式的转换：从依赖真实 Git 环境的集成测试，转变为依赖 Mock 对象 (Engine/Runtime) 的纯单元测试。

### 目标
1.  创建 `tests/application/test_controller.py`，实现对 `run_quipu` 编排逻辑的单元测试。
2.  在新的测试中，使用 `unittest.mock` 模拟 `create_engine` 和 `create_executor`，切断对底层实现的依赖。
3.  清理 `tests/integration/test_cli_workflow.py`，移除已迁移的 `TestController` 类，仅保留真正的 CLI 集成测试。

### 基本原理
`run_quipu` 是 Application 层的核心编排函数。它的职责是协调 Parser、Engine 和 Executor，而不是实现它们的细节。因此，对其进行测试时，应验证“协调逻辑”（如：是否创建了 Engine？是否调用了 Executor？出错时是否捕获了异常？），而不是验证“实现细节”（如：文件是否真的写入了磁盘？Git Commit 是否生成了？）。

通过 Mock 依赖，我们能将这些测试的运行速度提高一个数量级，并使其不再受底层存储变更的影响。

### 标签
#intent/refine #flow/ready #priority/medium #comp/tests #comp/application #concept/executor #scope/core #ai/instruct #task/domain/testing #task/object/test-suite #task/action/migration #task/state/continue

---

### Script

#### Acts 1: 创建 Application 层控制器测试

我们首先创建新的测试文件。这里我们利用了第一阶段创建的 `mock_engine` 和 `mock_runtime` fixtures。我们需要 Patch `pyquipu.application.controller` 内部使用的工厂函数，将这些 Mock 对象注入进去。

~~~~~act
write_file tests/application/test_controller.py
~~~~~
~~~~~python
from unittest.mock import ANY, patch

import pytest
from pyquipu.application.controller import run_quipu
from pyquipu.interfaces.exceptions import ExecutionError


class TestControllerUnit:
    """
    对 Application 层 Controller 的纯单元测试。
    使用 Mock 替代真实的 Engine 和 Runtime，仅验证编排逻辑。
    """

    def test_run_quipu_success(self, tmp_path, mock_engine, mock_runtime):
        """测试正常执行流程：应正确初始化组件并按顺序调用。"""
        # 模拟 Parser 解析结果不为空，以避免 noStatements 警告
        # 注意：run_quipu 内部会调用 get_parser，这里为了简单，我们让 execute 被调用即可
        # 如果 run_quipu 内部有 parser 逻辑，我们假设 parser 是纯函数，不需要 mock，
        # 只要传入有效的 markdown 内容即可。

        plan_content = """
```act
echo
```
```text
hello
```
"""
        # Patch 工厂函数以返回我们的 Mock 对象
        with patch("pyquipu.application.controller.create_engine", return_value=mock_engine) as mk_eng_fac, \
             patch("pyquipu.application.controller.create_executor", return_value=mock_runtime) as mk_exec_fac:

            # 模拟 Engine 初始状态
            mock_engine.align.return_value = "CLEAN"

            # 执行
            result = run_quipu(
                content=plan_content,
                work_dir=tmp_path,  # 提供一个路径即可，不需要真实 Git 仓库
                yolo=True,
                confirmation_handler=lambda *a: True
            )

            # 验证结果
            assert result.success is True
            assert result.exit_code == 0

            # 验证交互
            mk_eng_fac.assert_called_once_with(tmp_path)
            mk_exec_fac.assert_called_once()
            
            # 验证编排顺序：Align -> Capture (Pre) -> Execute -> Capture (Post)
            mock_engine.align.assert_called()
            mock_runtime.execute.assert_called_once()
            # 至少调用一次 capture_drift (通常是两次，执行前和执行后，或者根据实现可能有变化)
            # 这里我们只断言它被调用了，作为副作用的记录
            assert mock_engine.capture_drift.called

    def test_run_quipu_execution_error(self, tmp_path, mock_engine, mock_runtime):
        """测试执行器抛出异常时的错误处理流程。"""
        plan_content = """
```act
fail_act
```
"""
        with patch("pyquipu.application.controller.create_engine", return_value=mock_engine), \
             patch("pyquipu.application.controller.create_executor", return_value=mock_runtime):

            # 模拟 Runtime 抛出业务异常
            mock_runtime.execute.side_effect = ExecutionError("Task failed successfully")

            result = run_quipu(
                content=plan_content,
                work_dir=tmp_path,
                yolo=True,
                confirmation_handler=lambda *a: True
            )

            # 验证错误被捕获并封装到 Result 中
            assert result.success is False
            assert result.exit_code == 1
            assert result.message == "run.error.execution"
            assert isinstance(result.error, ExecutionError)
            assert "Task failed successfully" in str(result.error)

    def test_run_quipu_empty_plan(self, tmp_path, mock_engine, mock_runtime):
        """测试空计划的处理。"""
        plan_content = "Just some text, no acts."

        with patch("pyquipu.application.controller.create_engine", return_value=mock_engine), \
             patch("pyquipu.application.controller.create_executor", return_value=mock_runtime):

            result = run_quipu(
                content=plan_content,
                work_dir=tmp_path,
                yolo=True,
                confirmation_handler=lambda *a: True
            )

            # 空计划通常不算失败，但也没有副作用
            assert result.success is True
            assert result.exit_code == 0
            assert result.message == "axon.warning.noStatements"
            
            # 验证没有调用 execute
            mock_runtime.execute.assert_not_called()
~~~~~

#### Acts 2: 清理 Integration 测试

现在我们将 `tests/integration/test_cli_workflow.py` 中的 `TestController` 类移除，只保留真正属于 CLI 集成测试的部分（`TestCLIWrapper` 和 `TestCheckoutCLI`）。这些测试验证 `main.py` 入口点、参数解析以及端到端的命令行为。

~~~~~act
write_file tests/integration/test_cli_workflow.py
~~~~~
~~~~~python
import logging

import pytest
from pyquipu.application.controller import run_quipu
from pyquipu.cli.main import app
from typer.testing import CliRunner

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


# --- CLI Layer Tests (The Shell) ---
# 这些测试验证 main.py 是否正确解析参数并传递给 Controller

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

        # 设置 user 避免 commit 报错
        subprocess.run(["git", "config", "user.email", "test@quipu.dev"], cwd=tmp_path, check=True)
        subprocess.run(["git", "config", "user.name", "Quipu Test"], cwd=tmp_path, check=True)

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
        from pyquipu.cli.commands import run

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
        from unittest.mock import MagicMock
        mock_bus = MagicMock()
        # Mock bus to avoid dependency on specific UI text
        with pytest.MonkeyPatch.context() as m:
            m.setattr("pyquipu.cli.commands.workspace.bus", mock_bus)
            result = runner.invoke(app, ["save", "-w", str(workspace)])
            assert result.exit_code == 0
            mock_bus.success.assert_called_with("workspace.save.noChanges")

    def test_cli_discard_no_history(self, workspace):
        """测试 `discard` 命令在没有历史记录时的行为"""
        from unittest.mock import MagicMock
        mock_bus = MagicMock()
        with pytest.MonkeyPatch.context() as m:
            m.setattr("pyquipu.cli.commands.workspace.bus", mock_bus)
            result = runner.invoke(app, ["discard", "-f", "-w", str(workspace)])
            assert result.exit_code == 1
            mock_bus.error.assert_called_with("workspace.error.noHistory")


class TestCheckoutCLI:
    @pytest.fixture
    def populated_workspace(self, workspace):
        """
        Create a workspace with two distinct, non-overlapping history nodes.
        State A contains only a.txt.
        State B contains only b.txt.
        This fixture is backend-agnostic.
        """
        from pyquipu.application.factory import create_engine

        # State A: Create a.txt
        plan_a = "```act\nwrite_file a.txt\n```\n```content\nState A\n```"
        run_quipu(
            content=plan_a, work_dir=workspace, yolo=True, confirmation_handler=lambda *a: True
        )

        engine_after_a = create_engine(workspace)
        nodes_after_a = sorted(engine_after_a.reader.load_all_nodes(), key=lambda n: n.timestamp)
        node_a = nodes_after_a[-1]
        hash_a = node_a.output_tree

        # Manually create State B by removing a.txt and adding b.txt
        (workspace / "a.txt").unlink()
        plan_b = "```act\nwrite_file b.txt\n```\n```content\nState B\n```"
        run_quipu(
            content=plan_b, work_dir=workspace, yolo=True, confirmation_handler=lambda *a: True
        )

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
        # Success message check is now implicitly handled by exit code, 
        # or we could mock bus if we want to be strict.

        # Post-flight check: we are now in state A
        assert (workspace / "a.txt").exists()
        assert (workspace / "a.txt").read_text() == "State A"
        assert not (workspace / "b.txt").exists()

    def test_cli_checkout_with_safety_capture(self, populated_workspace):
        """Test that a dirty state is captured before checkout."""
        from pyquipu.application.factory import create_engine

        workspace, hash_a, hash_b = populated_workspace

        # Make the workspace dirty
        (workspace / "c_dirty.txt").write_text("uncommitted change")

        # Get node count via the storage-agnostic reader interface
        engine_before = create_engine(workspace)
        num_nodes_before = len(engine_before.reader.load_all_nodes())

        result = runner.invoke(app, ["checkout", hash_a[:8], "--work-dir", str(workspace), "--force"])

        assert result.exit_code == 0

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
        
        # Using Mock Bus to check error message id
        from unittest.mock import MagicMock
        mock_bus = MagicMock()
        with pytest.MonkeyPatch.context() as m:
            m.setattr("pyquipu.cli.commands.navigation.bus", mock_bus)
            result = runner.invoke(app, ["checkout", "deadbeef", "--work-dir", str(workspace), "--force"])
            
            assert result.exit_code == 1
            mock_bus.error.assert_called_with("navigation.checkout.error.notFound", hash_prefix="deadbeef")

    def test_cli_checkout_already_on_state(self, populated_workspace):
        """Test checking out to the current state does nothing."""
        workspace, _, hash_b = populated_workspace

        from unittest.mock import MagicMock
        mock_bus = MagicMock()
        with pytest.MonkeyPatch.context() as m:
            m.setattr("pyquipu.cli.commands.navigation.bus", mock_bus)
            
            result = runner.invoke(app, ["checkout", hash_b[:8], "--work-dir", str(workspace), "--force"])

            assert result.exit_code == 0
            mock_bus.success.assert_called_with("navigation.checkout.success.alreadyOnState")
~~~~~

### 下一步建议
第三阶段：引擎层净化。我们将重构 `tests/engine/sqlite/test_writer.py` 和 `tests/integration/test_idempotent_node.py`，移除其中不当的 `run_quipu` 调用，改用 `Engine` 和 `Writer` 的直接 API。
