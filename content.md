好的，我们继续扩展测试覆盖。

根据你的指示，我们将把为 `quipu run` 建立的健壮性测试模式，应用到另外两个关键的交互式命令：`quipu discard` 和 `quipu checkout`。这将确保整个工具链在面对用户取消或在非交互式环境中运行时，行为一致且安全。

我将直接在现有的 `test_unfriendly_paths.py` 文件中追加新的测试用例，并为其创建一个共享的 `pytest` fixture，以准备一个包含历史和未提交变更的通用测试环境。

## [WIP] test: 扩展“不友好路径”测试以覆盖 discard 和 checkout

### 用户需求
将 `quipu run` 命令的“不友好路径”测试模式（用户取消和非交互式环境）扩展到 `quipu discard` 和 `quipu checkout` 命令，以确保它们在这些场景下也能安全地中止操作。

### 评论
这是一个系统性的健壮性增强。通过确保所有具有潜在破坏性的交互式命令都遵循相同的安全中止逻辑，我们极大地提升了 Quipu CLI 的可靠性和用户信任度。

### 目标
1.  在 `tests/cli/test_unfriendly_paths.py` 文件中，创建一个新的 `pytest` fixture，用于构建一个包含两个历史节点和一些未提交变更的测试工作区。
2.  为 `quipu discard` 命令添加两个测试用例：一个模拟用户输入 `n` 取消操作，另一个模拟在非交互式环境中自动中止。
3.  为 `quipu checkout` 命令添加两个类似的测试用例。
4.  验证在所有这些场景下，命令都正确中止，并且文件系统状态未被修改。

### 基本原理
我们将利用 `pytest` 的 fixture 机制来创建一个可复用的、包含多阶段历史的工作区，从而避免在每个测试用例中重复设置代码。然后，我们将复用 `monkeypatch` 技术来精确模拟 `click.getchar()` 在用户取消 (`return 'n'`) 和非交互式环境 (`raise EOFError`) 下的行为。断言将检查命令的退出码、`stderr` 中的提示信息以及工作区文件的内容，以确保操作被完全、干净地中止了。

### 标签
#intent/tooling #flow/ready #priority/high #comp/cli #comp/tests #concept/navigation #scope/dx #ai/instruct #task/domain/testing #task/object/unfriendly-paths #task/action/implementation #task/state/continue

---

### Script

#### Acts 1: 扩展 `test_unfriendly_paths.py`

我们将使用 `write_file` 全量更新此文件，在原有内容的基础上增加新的 fixture 和四个测试用例。

~~~~~act
write_file
tests/cli/test_unfriendly_paths.py
~~~~~
~~~~~python
import pytest
import click
from typer.testing import CliRunner
from quipu.cli.main import app
from quipu.engine.state_machine import Engine


@pytest.fixture
def dirty_workspace(quipu_workspace):
    """
    提供一个包含历史记录和未提交变更的工作区。
    - State A: file.txt -> "v1"
    - State B (HEAD): file.txt -> "v2"
    - Dirty State: file.txt -> "v3"
    """
    work_dir, _, engine = quipu_workspace
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

    return work_dir, engine, hash_a


# --- Tests for `quipu run` ---


def test_run_command_user_cancellation(runner: CliRunner, quipu_workspace, monkeypatch):
    """
    不友好路径测试: 验证当用户输入 'n' 时，`run` 操作会被正确取消。
    """
    work_dir, _, _ = quipu_workspace
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

    assert result.exit_code == 2, f"CLI command should have been cancelled. Stderr:\n{result.stderr}"
    assert "操作已取消" in result.stderr
    assert not output_file.exists()


def test_run_command_in_non_interactive_env(runner: CliRunner, quipu_workspace, monkeypatch):
    """
    不友好路径测试: 验证在非交互式环境 (无法 getchar) 中，`run` 操作会自动中止。
    """
    work_dir, _, _ = quipu_workspace
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
    assert "操作已取消" in result.stderr
    assert "(non-interactive)" in result.stderr
    assert not output_file.exists()


# --- Tests for `quipu discard` ---


def test_discard_user_cancellation(runner: CliRunner, dirty_workspace, monkeypatch):
    """不友好路径测试: 验证 `discard` 操作可以被用户取消。"""
    work_dir, _, _ = dirty_workspace

    def mock_getchar_n(echo):
        click.echo("n", err=True)
        return "n"

    monkeypatch.setattr(click, "getchar", mock_getchar_n)
    result = runner.invoke(app, ["discard", "-w", str(work_dir)])

    assert result.exit_code == 1  # typer.Abort exits with 1
    assert "操作已取消" in result.stderr
    assert (work_dir / "file.txt").read_text() == "v3", "File should not be changed."


def test_discard_in_non_interactive_env(runner: CliRunner, dirty_workspace, monkeypatch):
    """不友好路径测试: 验证 `discard` 在非交互式环境中安全中止。"""
    work_dir, _, _ = dirty_workspace

    def mock_getchar_fail(echo):
        raise EOFError("Simulating non-interactive environment")

    monkeypatch.setattr(click, "getchar", mock_getchar_fail)
    result = runner.invoke(app, ["discard", "-w", str(work_dir)])

    assert result.exit_code == 1
    assert "(non-interactive)" in result.stderr
    assert (work_dir / "file.txt").read_text() == "v3", "File should not be changed."


# --- Tests for `quipu checkout` ---


def test_checkout_user_cancellation(runner: CliRunner, dirty_workspace, monkeypatch):
    """不友好路径测试: 验证 `checkout` 操作可以被用户取消。"""
    work_dir, _, hash_a = dirty_workspace

    def mock_getchar_n(echo):
        click.echo("n", err=True)
        return "n"

    monkeypatch.setattr(click, "getchar", mock_getchar_n)
    result = runner.invoke(app, ["checkout", hash_a[:7], "-w", str(work_dir)])

    assert result.exit_code == 1
    assert "操作已取消" in result.stderr
    assert (work_dir / "file.txt").read_text() == "v3", "File should not be changed."


def test_checkout_in_non_interactive_env(runner: CliRunner, dirty_workspace, monkeypatch):
    """不友好路径测试: 验证 `checkout` 在非交互式环境中安全中止。"""
    work_dir, _, hash_a = dirty_workspace

    def mock_getchar_fail(echo):
        raise EOFError("Simulating non-interactive environment")

    monkeypatch.setattr(click, "getchar", mock_getchar_fail)
    result = runner.invoke(app, ["checkout", hash_a[:7], "-w", str(work_dir)])

    assert result.exit_code == 1
    assert "(non-interactive)" in result.stderr
    assert (work_dir / "file.txt").read_text() == "v3", "File should not be changed."
~~~~~

### 下一步建议
我们已经成功地将健壮性测试覆盖到了 `run`, `discard`, 和 `checkout` 三个核心交互命令。请运行完整的测试套件以确认所有改动都按预期工作。

测试通过后，我们可以将这些测试的变更进行提交。
