import logging
from unittest.mock import ANY

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
            mock_bus.error.assert_called_with("workspace.discard.error.noHistory")


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
        run_quipu(content=plan_a, work_dir=workspace, yolo=True, confirmation_handler=lambda *a: True)

        engine_after_a = create_engine(workspace)
        nodes_after_a = sorted(engine_after_a.reader.load_all_nodes(), key=lambda n: n.timestamp)
        node_a = nodes_after_a[-1]
        hash_a = node_a.output_tree

        # Manually create State B by removing a.txt and adding b.txt
        (workspace / "a.txt").unlink()
        plan_b = "```act\nwrite_file b.txt\n```\n```content\nState B\n```"
        run_quipu(content=plan_b, work_dir=workspace, yolo=True, confirmation_handler=lambda *a: True)

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
            mock_bus.success.assert_called_with("navigation.checkout.info.noAction", short_hash=ANY)
