好的，我们开始进行代码审核和重构。

你的观察非常敏锐。测试代码中确实存在大量可以被标准化的重复模式，尤其是在测试环境的搭建和历史节点的创建上。将这些公用组件提取到统一的 `tests/helpers.py` 中，是确保测试套件可维护性和可扩展性的关键一步。

我将生成一个计划，首先将最明显的重复逻辑——位于 `tests/integration/` 下的本地 `helpers.py` 和 `test_sync_modes.py` 中的本地辅助函数——提取并合并到顶层的 `tests/helpers.py` 中。

## [WIP] refactor(tests): 提取通用测试组件到 tests/helpers.py

### 用户需求

用户希望重构测试代码，将所有测试文件中重复的、通用的组件（如创建历史节点、设置工作区等）提取到 `tests/helpers.py` 中，为未来将测试拆分到不同包（如 `tests/cli`, `tests/engine`）中做好准备。

### 评论

这是一个非常健康的重构方向。当前的测试代码存在明显的重复——多个测试文件都通过手动操作 `engine` 实例或定义本地辅助函数来创建测试数据。这种做法不仅冗余，而且使得测试的意图不明确，维护成本高。通过将这些逻辑集中到 `tests/helpers.py`，我们可以建立一个统一的、声明式的测试数据创建 API，让测试用例本身更关注于验证行为，而不是环境搭建。

### 目标

1.  将 `tests/integration/helpers.py` 中定义的 `run_git_command` 辅助函数移动到顶层的 `tests/helpers.py` 中。
2.  将 `tests/integration/test_sync_modes.py` 中定义的本地辅助函数 `create_node` 移动到顶层的 `tests/helpers.py`，并重命名为 `create_node_via_cli` 以明确其行为。
3.  删除原有的 `tests/integration/helpers.py` 文件。
4.  更新 `tests/integration/test_sync_modes.py`，使其从顶层的 `tests/helpers.py` 导入并使用这些标准化的辅助函数。

### 基本原理

我们将 `run_git_command` 和 `create_node` (重命名为 `create_node_via_cli`) 作为第一批提取目标。`run_git_command` 是与 Git 交互的基础工具，而 `create_node_via_cli` 封装了通过 CLI Runner 创建节点的完整流程，是集成测试的理想构建块。

将它们集中到 `tests/helpers.py` 中，可以立即消除 `tests/integration` 目录下的重复定义，并为所有其他测试（包括未来的）提供一组可复用的高级辅助工具。现有的 `tests/helpers.py` 已经包含了针对 `engine` 实例的底层辅助函数，这次添加将丰富其功能，使其同时支持单元/组件测试和集成测试的场景。

### 标签

#intent/refine #flow/ready #priority/high #comp/tests #scope/dx #ai/instruct #task/domain/testing #task/object/helpers #task/action/refactor #task/state/begin

---

### Script

#### Acts 1: 增强顶层 `helpers.py`

首先，我们将 `run_git_command` 和 `create_node_via_cli` 函数添加到 `tests/helpers.py` 中，并确保它拥有所需的全部导入。

~~~~~act
patch_file
tests/helpers.py
~~~~~
~~~~~python.old
    def get_node_blobs(self, commit_hash: str) -> Dict[str, bytes]:
        return {}
~~~~~
~~~~~python.new
    def get_node_blobs(self, commit_hash: str) -> Dict[str, bytes]:
        return {}


# --- CLI/Integration Test Helpers ---
import subprocess
from typer.testing import CliRunner
from pyquipu.cli.main import app


def run_git_command(cwd: Path, args: list[str], check: bool = True) -> str:
    """Helper to run a git command and return stdout."""
    result = subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True, check=check)
    return result.stdout.strip()


def get_local_quipu_heads(work_dir: Path) -> set[str]:
    """Helper to get a set of all local quipu head commit hashes."""
    refs_output = run_git_command(
        work_dir, ["for-each-ref", "--format=%(objectname)", "refs/quipu/local/heads"], check=False
    )
    if not refs_output:
        return set()
    return set(refs_output.splitlines())


def create_node_via_cli(runner: CliRunner, work_dir: Path, content: str) -> str:
    """Helper to create a node via the CLI runner and return its commit hash."""
    heads_before = get_local_quipu_heads(work_dir)

    # [FIX] Add an explicit title to the plan to ensure predictable node summary.
    plan_title = f"Plan for {content}"
    plan_file = work_dir / f"{content}.md"
    plan_file.write_text(f"# {plan_title}\n\n~~~~~act\necho '{content}'\n~~~~~")

    result = runner.invoke(app, ["run", str(plan_file), "--work-dir", str(work_dir), "-y"])
    assert result.exit_code == 0

    heads_after = get_local_quipu_heads(work_dir)
    new_heads = heads_after - heads_before

    if not new_heads:
        raise AssertionError("No new Quipu nodes created.")

    # If only 1 node created, return it.
    if len(new_heads) == 1:
        return new_heads.pop()

    # If 2 nodes created (Capture + Plan), identify the Plan node by checking if
    # the explicit title is present in the commit message.
    for head in new_heads:
        msg = run_git_command(work_dir, ["log", "-1", "--format=%B", head])
        if plan_title in msg:
            return head

    raise AssertionError(f"Could not identify Plan node among {len(new_heads)} new heads: {new_heads}")
~~~~~

#### Acts 2: 删除冗余的本地辅助文件

现在，旧的 `tests/integration/helpers.py` 文件已经没有存在的必要了。

~~~~~act
delete_file
tests/integration/helpers.py
~~~~~

#### Acts 3: 重构集成测试以使用新辅助函数

最后，我们重写 `test_sync_modes.py`，删除其本地的 `get_local_quipu_heads` 和 `create_node` 函数，并从 `tests/helpers.py` 导入和使用新的标准化版本。

~~~~~act
write_file
tests/integration/test_sync_modes.py
~~~~~
~~~~~python
from pathlib import Path

from pyquipu.cli.main import app
from pyquipu.common.identity import get_user_id_from_email
from typer.testing import CliRunner

from ..helpers import create_node_via_cli, run_git_command

runner = CliRunner()


class TestSyncModes:
    def test_push_only_mode(self, sync_test_environment):
        """User A pushes, but does not pull User B's changes."""
        remote_path, user_a_path, user_b_path = sync_test_environment
        user_a_id = get_user_id_from_email("user.a@example.com")
        user_b_id = get_user_id_from_email("user.b@example.com")

        # User B creates a node and pushes it
        node_b = create_node_via_cli(runner, user_b_path, "node_from_b")
        runner.invoke(app, ["sync", "--work-dir", str(user_b_path)])

        # User A creates a node
        node_a = create_node_via_cli(runner, user_a_path, "node_from_a")

        # User A syncs with push-only
        sync_result = runner.invoke(app, ["sync", "--work-dir", str(user_a_path), "--mode", "push-only"])
        assert sync_result.exit_code == 0
        assert "⬆️  正在推送..." in sync_result.stderr
        assert "⬇️" not in sync_result.stderr  # Should not fetch

        # Verify remote has User A's node
        remote_refs = run_git_command(remote_path, ["for-each-ref"])
        assert f"refs/quipu/users/{user_a_id}/heads/{node_a}" in remote_refs

        # Verify User A's local repo DOES NOT have User B's node
        local_refs_a = run_git_command(user_a_path, ["for-each-ref"])
        assert f"refs/quipu/remotes/origin/{user_b_id}/heads/{node_b}" not in local_refs_a

    def test_pull_only_mode(self, sync_test_environment):
        """User B pulls User A's changes, but does not push its own."""
        remote_path, user_a_path, user_b_path = sync_test_environment
        user_a_id = get_user_id_from_email("user.a@example.com")
        import yaml

        # User A creates a node and pushes
        node_a = create_node_via_cli(runner, user_a_path, "node_from_a_for_pull")
        runner.invoke(app, ["sync", "--work-dir", str(user_a_path)])

        # [FIX] User B must subscribe to User A to be able to pull their changes.
        # Onboard B first (before creating local nodes to avoid accidental push)
        runner.invoke(app, ["sync", "--work-dir", str(user_b_path)])

        # User B creates a node but doesn't push
        node_b = create_node_via_cli(runner, user_b_path, "node_from_b_local")

        config_path_b = user_b_path / ".quipu" / "config.yml"
        with open(config_path_b, "r") as f:
            config_b = yaml.safe_load(f)
        config_b["sync"]["subscriptions"] = [user_a_id]
        with open(config_path_b, "w") as f:
            yaml.dump(config_b, f)

        # User B syncs with pull-only
        sync_result = runner.invoke(app, ["sync", "--work-dir", str(user_b_path), "--mode", "pull-only"])
        assert sync_result.exit_code == 0
        assert "⬇️  正在拉取..." in sync_result.stderr
        assert "⬆️" not in sync_result.stderr  # Should not push

        # Verify User B's local repo HAS User A's node (in remotes ONLY)
        local_refs_b = run_git_command(user_b_path, ["for-each-ref"])
        assert f"refs/quipu/remotes/origin/{user_a_id}/heads/{node_a}" in local_refs_b
        # Crucial: Foreign nodes should NOT pollute local/heads to prevent re-pushing them as own
        assert f"refs/quipu/local/heads/{node_a}" not in local_refs_b

        # Verify remote DOES NOT have User B's node
        remote_refs = run_git_command(remote_path, ["for-each-ref"])
        assert f"{node_b}" not in remote_refs

    def test_push_force_mode(self, sync_test_environment):
        """User A force-pushes, deleting a stale ref on the remote."""
        remote_path, user_a_path, _ = sync_test_environment

        # User A creates two nodes and pushes
        node1 = create_node_via_cli(runner, user_a_path, "node_to_keep")
        node2_stale = create_node_via_cli(runner, user_a_path, "node_to_delete")
        runner.invoke(app, ["sync", "--work-dir", str(user_a_path)])

        # Verify both exist on remote
        remote_refs = run_git_command(remote_path, ["for-each-ref"])
        assert node1 in remote_refs
        assert node2_stale in remote_refs

        # User A deletes one ref locally
        run_git_command(user_a_path, ["update-ref", "-d", f"refs/quipu/local/heads/{node2_stale}"])

        # User A syncs with push-force
        sync_result = runner.invoke(app, ["sync", "--work-dir", str(user_a_path), "--mode", "push-force"])
        assert sync_result.exit_code == 0
        assert "⬆️  正在强制推送..." in sync_result.stderr

        # Verify stale node is GONE from remote, but keep node is still there
        remote_refs_after = run_git_command(remote_path, ["for-each-ref"])
        assert node1 in remote_refs_after
        assert node2_stale not in remote_refs_after

    def test_pull_prune_mode(self, sync_test_environment):
        """User B has a stale local ref that should be pruned after pulling."""
        remote_path, user_a_path, user_b_path = sync_test_environment
        user_b_id = get_user_id_from_email("user.b@example.com")

        # User B creates two nodes and pushes
        node1_b = create_node_via_cli(runner, user_b_path, "b_node_to_keep")
        node2_b_stale = create_node_via_cli(runner, user_b_path, "b_node_to_delete")
        runner.invoke(app, ["sync", "--work-dir", str(user_b_path)])

        # Now, on another device (simulated by remote), the stale ref is deleted
        run_git_command(remote_path, ["update-ref", "-d", f"refs/quipu/users/{user_b_id}/heads/{node2_b_stale}"])

        # User B syncs with pull-prune
        sync_result = runner.invoke(app, ["sync", "--work-dir", str(user_b_path), "--mode", "pull-prune"])
        assert sync_result.exit_code == 0
        assert "🗑️  正在修剪本地..." in sync_result.stderr

        # Verify stale node is GONE from User B's local heads, but keep node is still there
        local_refs_b = run_git_command(user_b_path, ["for-each-ref", "refs/quipu/local/heads"])
        assert node1_b in local_refs_b
        assert node2_b_stale not in local_refs_b
~~~~~

### 下一步建议

我们已经成功地将第一批高阶辅助函数提取出来，并清理了 `tests/integration` 目录。

下一步，我们应该系统性地审查 `tests/cli` 和 `tests/engine` 目录下的其他测试文件，将其中手写的历史创建逻辑（例如在 `test_export_command.py` 的 `populated_history` fixture 中）替换为对 `tests/helpers.py` 中 `create_plan_node_with_change` 和 `create_capture_node_with_change` 的调用。

这将使我们的测试套件更加 DRY (Don't Repeat Yourself)，并显著提高其可读性和可维护性。
