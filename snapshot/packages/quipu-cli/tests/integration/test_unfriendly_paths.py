from unittest.mock import ANY, MagicMock, call

import click
import pytest
from pyquipu.cli.main import app
from typer.testing import CliRunner

from pyquipu.test_utils.helpers import create_dirty_workspace_history


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
