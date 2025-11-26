# test: 完善测试覆盖率并集成 pytest-cov

## 用户需求
你希望通过集成覆盖率工具 (`pytest-cov`) 并为 CLI 和核心逻辑的边界情况补充测试用例，来提升 `Quipu` 系统的健壮性和可维护性。

## 评论
这是一个非常重要的开发实践。量化测试覆盖率可以清晰地揭示测试薄弱环节，而针对错误路径和边界情况的测试是保证软件稳定性的关键。现有的测试覆盖了一些成功路径，但对用户可能遇到的错误（如文件不存在、状态不匹配）的响应测试不足。本计划将系统性地解决这些问题。

## 目标
1.  在 `pyproject.toml` 中配置 `pytest-cov`，以便在运行测试时自动生成覆盖率报告。
2.  为 `quipu` CLI 的多个命令 (`run`, `save`, `discard`) 补充处理错误输入的测试用例。
3.  增加一个新的测试，验证插件加载机制的容错能力，确保损坏的插件不会导致主程序崩溃。

## 基本原理
通过 `pytest-cov` 和 `CliRunner`，我们可以自动化地验证代码逻辑的覆盖范围和程序在真实调用场景下的行为。本次改进遵循“关键路径优先”的原则，首先加固与用户直接交互的 CLI 层和具有外部依赖（插件）的核心部分，以最小的成本最大化地提升系统可靠性。

## 标签
#intent/tooling #flow/ready #priority/high
#comp/tests #comp/build
#scope/dx
#ai/instruct
#task/domain/testing #task/object/coverage #task/action/improvement
#task/state/begin #task/status/active

---

## Script

### Acts 1: 配置 `pytest-cov`

首先，我们修改 `pyproject.toml` 文件，为 `pytest` 添加覆盖率报告的配置。

~~~~~act
replace pyproject.toml
~~~~~
~~~~~
[tool.pytest.ini_options]
pythonpath = [
  "packages/quipu-interfaces/src",
  "packages/quipu-engine/src",
  "packages/quipu-runtime/src",
  "packages/quipu-cli/src",
]
~~~~~
~~~~~
[tool.pytest.ini_options]
addopts = "-ra -q --cov=src --cov-report=term-missing"
pythonpath = [
  "packages/quipu-interfaces/src",
  "packages/quipu-engine/src",
  "packages/quipu-runtime/src",
  "packages/quipu-cli/src",
]
~~~~~

### Acts 2: 补充 CLI 错误路径测试

接下来，我们扩充 `tests/test_integration_v2.py` 文件，为 `run`，`save` 和 `discard` 命令添加边界情况和错误处理的测试。

~~~~~act
write_file tests/test_integration_v2.py
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
    subprocess.run(["git", "config", "user.name", "Axon Test"], cwd=ws, check=True)

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
        assert "Axon" in result.stdout

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
        # 1. 临时修改 main 模块中的默认入口文件引用，防止读取当前目录下的 o.md
        # 注意：必须 patch 'main' 模块，而不是 'config' 模块，因为 main 采用了 from import
        from quipu.cli import main

        monkeypatch.setattr(main, "DEFAULT_ENTRY_FILE", tmp_path / "non_existent.md")

        # 2. 同时确保 STDIN 不是 TTY，也不是管道（模拟纯交互式空运行）
        # CliRunner 默认就是这种状态，但为了保险起见，我们什么都不输入

        result = runner.invoke(app, ["run"])  # 无参数，无管道

        assert result.exit_code == 0
        assert "用法示例" in result.stderr

    def test_cli_list_acts(self):
        """测试 --list-acts"""
        # --list-acts 是 'run' 命令的一个选项
        result = runner.invoke(app, ["run", "--list-acts"])
        assert result.exit_code == 0
        assert "write_file" in result.stderr

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
        assert "❌ 错误: 未找到哈希前缀" in result.stderr

    def test_cli_checkout_already_on_state(self, populated_workspace):
        """Test checking out to the current state does nothing."""
        workspace, _, hash_b = populated_workspace

        result = runner.invoke(app, ["checkout", hash_b[:8], "--work-dir", str(workspace), "--force"])

        assert result.exit_code == 0
        assert "✅ 工作区已处于目标状态" in result.stderr
~~~~~

### Acts 3: 增加插件加载容错性测试

最后，我们创建一个新的测试文件来验证插件系统的健壮性，确保它能优雅地处理损坏的插件。

~~~~~act
write_file tests/test_plugin_resilience.py
~~~~~
~~~~~python
import pytest
import logging
from pathlib import Path

from quipu.core.executor import Executor
from quipu.cli.plugin_manager import PluginManager


class TestPluginResilience:
    @pytest.fixture
    def executor(self, tmp_path) -> Executor:
        return Executor(root_dir=tmp_path, yolo=True)

    @pytest.fixture
    def plugin_dir(self, tmp_path) -> Path:
        p_dir = tmp_path / "plugins"
        p_dir.mkdir()
        return p_dir

    def test_load_plugin_with_syntax_error(self, executor: Executor, plugin_dir: Path, caplog):
        """验证加载有语法错误的插件不会使程序崩溃。"""
        from quipu.acts.basic import register as register_basic_acts

        # 1. 创建一个有语法错误的插件
        bad_plugin_file = plugin_dir / "bad_syntax.py"
        bad_plugin_file.write_text("def register(executor):\n  print('unbalanced parentheses'", encoding="utf-8")

        # 2. 注册核心 Acts
        register_basic_acts(executor)
        num_acts_before = len(executor.get_registered_acts())

        # 3. 加载插件
        caplog.set_level(logging.ERROR)
        manager = PluginManager()
        manager.load_from_sources(executor, plugin_dir)

        # 4. 验证
        assert "加载插件 bad_syntax.py 失败" in caplog.text
        num_acts_after = len(executor.get_registered_acts())
        assert num_acts_after == num_acts_before, "不应注册任何新 Act"
        assert "write_file" in executor.get_registered_acts(), "核心 Act 应该仍然存在"

    def test_load_plugin_with_registration_error(self, executor: Executor, plugin_dir: Path, caplog):
        """验证插件在 register() 函数中抛出异常不会使程序崩溃。"""
        # 1. 创建一个在注册时会失败的插件
        bad_plugin_file = plugin_dir / "fail_on_register.py"
        plugin_content = """
def register(executor):
    raise ValueError("Something went wrong during registration")
"""
        bad_plugin_file.write_text(plugin_content, encoding="utf-8")

        # 2. 加载插件
        caplog.set_level(logging.ERROR)
        manager = PluginManager()
        manager.load_from_sources(executor, plugin_dir)

        # 3. 验证
        assert "加载插件 fail_on_register.py 失败" in caplog.text
        assert "ValueError: Something went wrong" in caplog.text
        assert len(executor.get_registered_acts()) == 0
~~~~~
