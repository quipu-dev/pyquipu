from unittest.mock import ANY, MagicMock

import pytest
from pyquipu.cli.main import app

from pyquipu.test_utils.helpers import create_linear_history


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
