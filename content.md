好的，我们继续。

下一个最明显需要重构的目标是 `tests/cli/test_navigation_commands.py` 和 `tests/cli/test_unfriendly_paths.py`。这两个文件都定义了本地的 fixture (`populated_workspace` 和 `dirty_workspace`) 来创建简单的线性历史记录。这是一种常见的模式，非常适合提取为通用的辅助函数。

我将生成一个计划，创建两个新的、语义化的辅助函数 `create_linear_history` 和 `create_dirty_workspace_history`，并将它们迁移到 `tests/helpers.py` 中。

## [WIP] refactor(tests): 提取线性历史和脏工作区创建逻辑

### 用户需求

继续审查 `tests/cli` 和 `tests/engine` 目录，并将其中用于创建测试数据的重复 fixture 逻辑，提取到 `tests/helpers.py` 中。

### 评论

这次重构的目标是 `populated_workspace` 和 `dirty_workspace` 这两个 fixture。它们代表了两种非常常见的测试场景：“一个简单的 A->B 线性历史”和“一个带有未提交更改的 A->B 历史”。

将这些场景封装成 `tests/helpers.py` 中有明确名称的函数，如 `create_linear_history`，可以极大地提高测试的可读性。测试的设置部分将从一系列命令式的 `write_text`/`capture_drift` 调用，转变为一句声明式的 `create_linear_history(engine)`。这使得任何阅读测试的人都能立刻明白其初始状态，而无需关心实现的细节。

### 目标

1.  在 `tests/helpers.py` 中创建两个新的辅助函数：`create_linear_history` 和 `create_dirty_workspace_history`。
2.  将 `tests/cli/test_navigation_commands.py` 中 `populated_workspace` fixture 的实现逻辑迁移到 `create_linear_history` 中。
3.  将 `tests/cli/test_unfriendly_paths.py` 中 `dirty_workspace` fixture 的实现逻辑迁移到 `create_dirty_workspace_history` 中。
4.  重构这两个测试文件，使其 fixture 调用新的、位于 `tests/helpers.py` 中的辅助函数。

### 基本原理

我们继续将“如何构建”的逻辑从测试文件中分离出去。通过为常见的历史模式（如线性、分支、脏工作区）创建标准化的构建函数，我们正在为测试套件建立一个领域特定语言（DSL）。这将使未来的测试编写变得更快、更不容易出错，并且更易于理解。

### 标签

#intent/refine #flow/ready #priority/high #comp/tests #scope/dx #ai/instruct #task/domain/testing #task/object/helpers #task/action/refactor #task/state/continue

---

### Script

#### Acts 1: 在 `tests/helpers.py` 中添加新的历史场景生成器

我将把 `populated_workspace` 和 `dirty_workspace` 的核心逻辑作为两个新函数添加到 `tests/helpers.py` 中。

~~~~~act
patch_file
tests/helpers.py
~~~~~
~~~~~python.old
    engine.create_plan_node(h3, h4, "plan 4", summary_override="Child_Node")
    return engine
~~~~~
~~~~~python.new
    engine.create_plan_node(h3, h4, "plan 4", summary_override="Child_Node")
    return engine


def create_linear_history(engine: Engine) -> Tuple[Engine, Dict[str, str]]:
    """
    Creates a simple linear history A -> B.
    - State A: a.txt
    - State B: b.txt (a.txt is removed)
    Returns the engine and a dictionary mapping state names ('a', 'b') to their output tree hashes.
    """
    ws = engine.root_dir

    # State A
    (ws / "a.txt").write_text("A")
    hash_a = engine.git_db.get_tree_hash()
    engine.create_plan_node(EMPTY_TREE_HASH, hash_a, "Plan A", summary_override="State A")

    # State B
    (ws / "b.txt").write_text("B")
    (ws / "a.txt").unlink()
    hash_b = engine.git_db.get_tree_hash()
    engine.create_plan_node(hash_a, hash_b, "Plan B", summary_override="State B")

    hashes = {"a": hash_a, "b": hash_b}
    return engine, hashes


def create_dirty_workspace_history(engine: Engine) -> Tuple[Engine, str]:
    """
    Creates a history A -> B, then makes the workspace dirty.
    - State A: file.txt -> "v1"
    - State B (HEAD): file.txt -> "v2"
    - Dirty State: file.txt -> "v3"
    Returns the engine and the hash of state A for checkout tests.
    """
    work_dir = engine.root_dir
    file_path = work_dir / "file.txt"

    # State A
    file_path.write_text("v1")
    hash_a = engine.git_db.get_tree_hash()
    engine.capture_drift(hash_a, message="State A")

    # State B (HEAD)
    file_path.write_text("v2")
    engine.capture_drift(engine.git_db.get_tree_hash(), message="State B")

    # Dirty State
    file_path.write_text("v3")

    return engine, hash_a
~~~~~

#### Acts 2: 重构 `test_navigation_commands.py`

现在，`populated_workspace` fixture 可以被极大地简化，只需调用新的辅助函数即可。

~~~~~act
write_file
tests/cli/test_navigation_commands.py
~~~~~
~~~~~python
from unittest.mock import ANY, MagicMock

import pytest
from pyquipu.cli.main import app

from ..helpers import create_linear_history


@pytest.fixture
def populated_workspace(quipu_workspace):
    ws, _, engine = quipu_workspace
    _, hashes = create_linear_history(engine)
    return ws, hashes["a"], hashes["b"]


def test_cli_back_forward_flow(runner, populated_workspace, monkeypatch):
    workspace, hash_a, hash_b = populated_workspace
    mock_bus_nav = MagicMock()
    mock_bus_helper = MagicMock()
    monkeypatch.setattr("pyquipu.cli.commands.navigation.bus", mock_bus_nav)
    monkeypatch.setattr("pyquipu.cli.commands.helpers.bus", mock_bus_helper)

    # Initial state is B. Let's checkout to A.
    runner.invoke(app, ["checkout", hash_a[:7], "-w", str(workspace), "-f"])
    assert (workspace / "a.txt").exists()
    assert not (workspace / "b.txt").exists()

    # Now we are at A. Let's go back. It should go to the previous state (B).
    result_back = runner.invoke(app, ["back", "-w", str(workspace)])
    assert result_back.exit_code == 0
    mock_bus_nav.success.assert_called_with("navigation.back.success", short_hash=ANY)
    assert (workspace / "b.txt").exists()
    assert not (workspace / "a.txt").exists()

    # Now we are back at B. Let's go forward to A again.
    result_fwd = runner.invoke(app, ["forward", "-w", str(workspace)])
    assert result_fwd.exit_code == 0
    mock_bus_nav.success.assert_called_with("navigation.forward.success", short_hash=ANY)
    assert (workspace / "a.txt").exists()
    assert not (workspace / "b.txt").exists()


def test_cli_boundary_messages(runner, populated_workspace, monkeypatch):
    workspace, hash_a, hash_b = populated_workspace
    mock_bus = MagicMock()
    monkeypatch.setattr("pyquipu.cli.commands.navigation.bus", mock_bus)

    # Go to a known state
    runner.invoke(app, ["checkout", hash_a[:7], "-w", str(workspace), "-f"])

    # Back until the beginning
    runner.invoke(app, ["back", "-w", str(workspace)])  # to B
    runner.invoke(app, ["back", "-w", str(workspace)])
    result2 = runner.invoke(app, ["back", "-w", str(workspace)])  # one more should hit boundary
    assert result2.exit_code == 0
    mock_bus.warning.assert_called_with("navigation.back.atStart")

    # Forward until the end
    runner.invoke(app, ["forward", "-w", str(workspace)])  # to B
    runner.invoke(app, ["forward", "-w", str(workspace)])  # to A
    result3 = runner.invoke(app, ["forward", "-w", str(workspace)])
    assert result3.exit_code == 0
    mock_bus.warning.assert_called_with("navigation.forward.atEnd")


def test_checkout_not_found(runner, populated_workspace, monkeypatch):
    workspace, _, _ = populated_workspace
    mock_bus = MagicMock()
    monkeypatch.setattr("pyquipu.cli.commands.navigation.bus", mock_bus)

    result = runner.invoke(app, ["checkout", "nonexistent", "-w", str(workspace)])
    assert result.exit_code == 1
    mock_bus.error.assert_called_once_with("navigation.checkout.error.notFound", hash_prefix="nonexistent")
~~~~~

#### Acts 3: 重构 `test_unfriendly_paths.py`

同样，`dirty_workspace` fixture 也可以被简化。

~~~~~act
write_file
tests/cli/test_unfriendly_paths.py
~~~~~
~~~~~python
from unittest.mock import ANY, MagicMock, call

import click
import pytest
from pyquipu.cli.main import app
from typer.testing import CliRunner

from ..helpers import create_dirty_workspace_history


@pytest.fixture
def dirty_workspace(quipu_workspace):
    """Provides a workspace with history and uncommitted changes."""
    work_dir, _, engine = quipu_workspace
    _, hash_a = create_dirty_workspace_history(engine)
    return work_dir, engine, hash_a


# --- Tests for `quipu run` ---


def test_run_command_user_cancellation(runner: CliRunner, quipu_workspace, monkeypatch):
    """
    不友好路径测试: 验证当用户输入 'n' 时，`run` 操作会被正确取消。
    """
    work_dir, _, _ = quipu_workspace
    mock_bus = MagicMock()
    monkeypatch.setattr("pyquipu.cli.commands.run.bus", mock_bus)
    output_file = work_dir / "output.txt"
    assert not output_file.exists()

    plan_content = f"""
```act
run_command
```
```text
echo "Should not run" > {output_file.name}
```
"""

    def mock_getchar_n(echo):
        click.echo("n", err=True)
        return "n"

    monkeypatch.setattr(click, "getchar", mock_getchar_n)

    result = runner.invoke(app, ["run", "-w", str(work_dir)], input=plan_content)

    assert result.exit_code == 2
    mock_bus.warning.assert_called_once_with("run.error.cancelled", error=ANY)
    assert not output_file.exists()


def test_run_command_in_non_interactive_env(runner: CliRunner, quipu_workspace, monkeypatch):
    """
    不友好路径测试: 验证在非交互式环境 (无法 getchar) 中，`run` 操作会自动中止。
    """
    work_dir, _, _ = quipu_workspace
    mock_bus = MagicMock()
    monkeypatch.setattr("pyquipu.cli.commands.run.bus", mock_bus)
    output_file = work_dir / "output.txt"
    assert not output_file.exists()

    plan_content = f"""
```act
run_command
```
```text
echo "Should not run" > {output_file.name}
```
"""

    def mock_getchar_fail(echo):
        raise EOFError("Simulating non-interactive environment")

    monkeypatch.setattr(click, "getchar", mock_getchar_fail)
    result = runner.invoke(app, ["run", "-w", str(work_dir)], input=plan_content)

    assert result.exit_code == 2
    mock_bus.warning.assert_called_once_with("run.error.cancelled", error=ANY)
    assert not output_file.exists()


# --- Tests for `quipu discard` ---


def test_discard_user_cancellation(runner: CliRunner, dirty_workspace, monkeypatch):
    """不友好路径测试: 验证 `discard` 操作可以被用户取消。"""
    work_dir, _, _ = dirty_workspace
    mock_bus = MagicMock()
    monkeypatch.setattr("pyquipu.cli.commands.workspace.bus", mock_bus)

    def mock_getchar_n(echo):
        click.echo("n", err=True)
        return "n"

    monkeypatch.setattr(click, "getchar", mock_getchar_n)
    result = runner.invoke(app, ["discard", "-w", str(work_dir)])

    assert result.exit_code == 1  # typer.Abort exits with 1
    mock_bus.warning.assert_called_once_with("common.prompt.cancel")
    assert (work_dir / "file.txt").read_text() == "v3", "File should not be changed."


def test_discard_in_non_interactive_env(runner: CliRunner, dirty_workspace, monkeypatch):
    """不友好路径测试: 验证 `discard` 在非交互式环境中安全中止。"""
    work_dir, _, _ = dirty_workspace
    mock_bus = MagicMock()
    monkeypatch.setattr("pyquipu.cli.commands.workspace.bus", mock_bus)

    def mock_getchar_fail(echo):
        raise EOFError("Simulating non-interactive environment")

    monkeypatch.setattr(click, "getchar", mock_getchar_fail)
    result = runner.invoke(app, ["discard", "-w", str(work_dir)])

    assert result.exit_code == 1  # typer.Abort exits with 1
    mock_bus.warning.assert_called_once_with("common.prompt.cancel")
    assert (work_dir / "file.txt").read_text() == "v3", "File should not be changed."


# --- Tests for `quipu checkout` ---


def test_checkout_user_cancellation(runner: CliRunner, dirty_workspace, monkeypatch):
    """不友好路径测试: 验证 `checkout` 操作可以被用户取消。"""
    work_dir, _, hash_a = dirty_workspace
    mock_bus = MagicMock()
    monkeypatch.setattr("pyquipu.cli.commands.navigation.bus", mock_bus)

    def mock_getchar_n(echo):
        click.echo("n", err=True)
        return "n"

    monkeypatch.setattr(click, "getchar", mock_getchar_n)
    result = runner.invoke(app, ["checkout", hash_a[:7], "-w", str(work_dir)])

    assert result.exit_code == 1
    expected_calls = [
        call("navigation.checkout.info.capturingDrift"),
        call("common.prompt.cancel"),
    ]
    mock_bus.warning.assert_has_calls(expected_calls)
    assert (work_dir / "file.txt").read_text() == "v3", "File should not be changed."


def test_checkout_in_non_interactive_env(runner: CliRunner, dirty_workspace, monkeypatch):
    """不友好路径测试: 验证 `checkout` 在非交互式环境中安全中止。"""
    work_dir, _, hash_a = dirty_workspace
    mock_bus = MagicMock()
    monkeypatch.setattr("pyquipu.cli.commands.navigation.bus", mock_bus)

    def mock_getchar_fail(echo):
        raise EOFError("Simulating non-interactive environment")

    monkeypatch.setattr(click, "getchar", mock_getchar_fail)
    result = runner.invoke(app, ["checkout", hash_a[:7], "-w", str(work_dir)])

    assert result.exit_code == 1
    expected_calls = [
        call("navigation.checkout.info.capturingDrift"),
        call("common.prompt.cancel"),
    ]
    mock_bus.warning.assert_has_calls(expected_calls)
    assert (work_dir / "file.txt").read_text() == "v3", "File should not be changed."
~~~~~

### 下一步建议

我们已经成功地将最常见的几种历史创建模式（分支、线性、脏工作区）抽象成了标准辅助函数。

现在，我们可以转向处理那些在测试函数**内部**直接创建历史记录的用例了。例如，`tests/cli/test_query_commands.py` 中的 `test_log_output` 和 `test_find_command` 函数都包含了手动的 `capture_drift` 调用。将这些调用也替换为对 `tests/helpers.py` 中函数的调用，将是完成本次重构的最后一步。
