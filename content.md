这是一个非常完善的测试套件，覆盖了用户引导、协作订阅、以及幂等性。

不过，请注意：**原稿中的 `test_pruning_on_push` 测试用例与我们刚刚实施的“非破坏性同步”策略冲突**。如果不修改，它将在 `assert num_refs_after == num_refs_before - 1` 处失败，因为我们已经移除了 `--prune`。

我将为你创建这个测试文件，但会对 `test_pruning_on_push` 进行**逻辑反转**，将其重命名为 `test_push_safety_no_prune`，以验证“本地删除不会导致远程数据丢失”。

此外，为了完整验证我们刚刚添加的 `reconcile` 逻辑，我还会补充一个 `test_multi_device_reconciliation` 用例，模拟同一个用户在两台设备上工作的场景。

## [WIP] test: 添加 Sync 工作流集成测试

### 用户需求
验证重构后的 `sync` 命令是否正确实现了非破坏性的双向同步，并确保多用户协作和多设备同步场景下的数据完整性。

### 评论
测试代码基于用户提供的草稿进行了必要的调整，以匹配当前的业务逻辑（移除 Prune，增加 Reconcile）。

### 目标
创建 `tests/integration/test_sync_workflow.py`，包含以下测试用例：
1.  `test_onboarding_and_first_push`: 验证首次使用和身份绑定。
2.  `test_collaboration_subscribe_and_fetch`: 验证跨用户协作。
3.  `test_sync_is_idempotent`: 验证幂等性。
4.  `test_push_safety_no_prune`: **(修改版)** 验证本地删除不传播到远程。
5.  `test_multi_device_reconciliation`: **(新增)** 验证多设备间的 Fetch -> Reconcile 流程。

### 标签
#intent/tooling #flow/ready #priority/high #comp/tests #concept/sync #scope/core #ai/refine #task/domain/sync #task/object/multi-device #task/action/test #task/state/continue

---

### Script

#### Acts 1: 创建集成测试文件

~~~~~act
write_file
tests/integration/test_sync_workflow.py
~~~~~
~~~~~python
import pytest
import subprocess
from pathlib import Path
from typer.testing import CliRunner
import yaml
import sqlite3

from quipu.cli.main import app
from quipu.common.identity import get_user_id_from_email

runner = CliRunner()


def run_git_command(cwd: Path, args: list[str], check: bool = True) -> str:
    """Helper to run a git command and return stdout."""
    result = subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True, check=check)
    return result.stdout.strip()


@pytest.fixture(scope="module")
def sync_test_environment(tmp_path_factory):
    """
    Sets up a full sync test environment:
    1. A bare remote repository.
    2. Two user workspaces cloned from the remote.
    """
    base_dir = tmp_path_factory.mktemp("sync_tests")
    remote_path = base_dir / "remote.git"
    user_a_path = base_dir / "user_a"
    user_b_path = base_dir / "user_b"

    # 1. Create bare remote
    run_git_command(base_dir, ["init", "--bare", str(remote_path)])

    # 2. Clone for User A
    run_git_command(base_dir, ["clone", str(remote_path), str(user_a_path)])
    run_git_command(user_a_path, ["config", "user.name", "User A"])
    run_git_command(user_a_path, ["config", "user.email", "user.a@example.com"])

    # 3. Clone for User B
    run_git_command(base_dir, ["clone", str(remote_path), str(user_b_path)])
    run_git_command(user_b_path, ["config", "user.name", "User B"])
    run_git_command(user_b_path, ["config", "user.email", "user.b@example.com"])

    # Add a dummy file to avoid issues with initial empty commits
    (user_a_path / "README.md").write_text("Initial commit")
    run_git_command(user_a_path, ["add", "README.md"])
    run_git_command(user_a_path, ["commit", "-m", "Initial commit"])
    run_git_command(user_a_path, ["push", "origin", "master"])
    run_git_command(user_b_path, ["pull"])

    return remote_path, user_a_path, user_b_path


class TestSyncWorkflow:
    def test_onboarding_and_first_push(self, sync_test_environment):
        """
        Tests the onboarding flow (user_id creation) and the first push of Quipu refs.
        """
        remote_path, user_a_path, _ = sync_test_environment
        user_a_id = get_user_id_from_email("user.a@example.com")

        # Create a Quipu node for User A
        (user_a_path / "plan.md").write_text("~~~~~act\necho 'hello'\n~~~~~")
        result = runner.invoke(app, ["run", str(user_a_path / "plan.md"), "--work-dir", str(user_a_path), "-y"])
        assert result.exit_code == 0

        # Run sync for the first time
        sync_result = runner.invoke(app, ["sync", "--work-dir", str(user_a_path), "--remote", "origin"])
        assert sync_result.exit_code == 0
        assert "首次使用 sync 功能" in sync_result.stderr
        assert f"生成并保存用户 ID: {user_a_id}" in sync_result.stderr

        # Verify config file
        config_path = user_a_path / ".quipu" / "config.yml"
        assert config_path.exists()
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)
        assert config["sync"]["user_id"] == user_a_id

        # Verify remote refs
        remote_refs = run_git_command(remote_path, ["for-each-ref", "--format=%(refname)"])
        assert f"refs/quipu/users/{user_a_id}/heads/" in remote_refs

    def test_collaboration_subscribe_and_fetch(self, sync_test_environment):
        """
        Tests that User B can subscribe to and fetch User A's history.
        AND verifies that ownership is correctly propagated to all ancestor nodes during hydration.
        """
        remote_path, user_a_path, user_b_path = sync_test_environment
        user_a_id = get_user_id_from_email("user.a@example.com")
        
        # --- Step 1: User A creates more history (Node 2) ---
        (user_a_path / "plan2.md").write_text("~~~~~act\necho 'world'\n~~~~~")
        runner.invoke(app, ["run", str(user_a_path / "plan2.md"), "--work-dir", str(user_a_path), "-y"])
        
        # Capture User A's commit hashes for verification later
        user_a_commits = run_git_command(
            user_a_path,
            ["log", "--all", "--format=%H", "--grep=X-Quipu-Output-Tree"]
        ).splitlines()
        assert len(user_a_commits) >= 2, "User A should have at least 2 Quipu nodes"

        # User A pushes again
        runner.invoke(app, ["sync", "--work-dir", str(user_a_path), "--remote", "origin"])

        # --- Step 2: User B setup ---
        # User B onboards
        runner.invoke(app, ["sync", "--work-dir", str(user_b_path), "--remote", "origin"])

        # User B subscribes to User A
        config_path_b = user_b_path / ".quipu" / "config.yml"
        with open(config_path_b, "r") as f:
            config_b = yaml.safe_load(f)
        config_b["sync"]["subscriptions"] = [user_a_id]
        if "storage" not in config_b:
            config_b["storage"] = {}
        config_b["storage"]["type"] = "sqlite"
        with open(config_path_b, "w") as f:
            yaml.dump(config_b, f)

        # --- Step 3: User B Syncs (Fetch) ---
        sync_result = runner.invoke(app, ["sync", "--work-dir", str(user_b_path), "--remote", "origin"])
        assert sync_result.exit_code == 0
        # Should pull self + User A
        assert f"拉取 2 个用户的历史" in sync_result.stderr

        # Verify local mirror ref in User B's repo
        local_refs_b = run_git_command(user_b_path, ["for-each-ref", "--format=%(refname)"])
        assert f"refs/quipu/remotes/origin/{user_a_id}/heads/" in local_refs_b

        # --- Step 4: Verify Hydration Integrity ---
        # Run cache sync to populate SQLite
        cache_sync_result = runner.invoke(app, ["cache", "sync", "--work-dir", str(user_b_path)])
        assert cache_sync_result.exit_code == 0

        db_path_b = user_b_path / ".quipu" / "history.sqlite"
        assert db_path_b.exists()
        
        conn = sqlite3.connect(db_path_b)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        for commit_hash in user_a_commits:
            cursor.execute("SELECT owner_id FROM nodes WHERE commit_hash = ?", (commit_hash,))
            row = cursor.fetchone()
            assert row is not None, f"Commit {commit_hash} not found in DB"
            assert row["owner_id"] == user_a_id, \
                f"Incorrect owner for commit {commit_hash}. Expected {user_a_id}, got {row['owner_id']}"
        
        conn.close()

    def test_sync_is_idempotent(self, sync_test_environment):
        """
        Tests that running sync multiple times doesn't change state or cause errors.
        """
        _, user_a_path, _ = sync_test_environment
        result1 = runner.invoke(app, ["sync", "--work-dir", str(user_a_path), "--remote", "origin"])
        assert result1.exit_code == 0
        refs_after_1 = run_git_command(user_a_path, ["for-each-ref"])

        result2 = runner.invoke(app, ["sync", "--work-dir", str(user_a_path), "--remote", "origin"])
        assert result2.exit_code == 0
        refs_after_2 = run_git_command(user_a_path, ["for-each-ref"])

        assert refs_after_1 == refs_after_2

    def test_push_safety_no_prune(self, sync_test_environment):
        """
        Tests that deleting a local head and syncing DOES NOT prune the remote ref.
        This validates the non-destructive behavior of the new sync protocol.
        """
        remote_path, user_a_path, _ = sync_test_environment
        user_a_id = get_user_id_from_email("user.a@example.com")

        # Create two new nodes
        (user_a_path / "plan3.md").write_text("~~~~~act\necho 'plan3'\n~~~~~")
        runner.invoke(app, ["run", str(user_a_path / "plan3.md"), "--work-dir", str(user_a_path), "-y"])
        
        # Sync to ensure remote has it
        runner.invoke(app, ["sync", "--work-dir", str(user_a_path), "--remote", "origin"])
        remote_refs_before = run_git_command(remote_path, ["for-each-ref", f"refs/quipu/users/{user_a_id}"])
        assert "plan3" in str(run_git_command(user_a_path, ["log", "--all"])) # Verify creation
        
        # Identify a ref to delete locally
        local_quipu_refs = run_git_command(
            user_a_path, ["for-each-ref", "--format=%(refname)", "refs/quipu/local/heads"]
        ).splitlines()
        ref_to_delete = local_quipu_refs[0]
        ref_hash = ref_to_delete.split("/")[-1]

        # Delete it locally
        run_git_command(user_a_path, ["update-ref", "-d", ref_to_delete])

        # Sync again
        sync_result = runner.invoke(app, ["sync", "--work-dir", str(user_a_path), "--remote", "origin"])
        assert sync_result.exit_code == 0

        # Verify it is STILL present on remote (Safety Check)
        remote_refs_after = run_git_command(remote_path, ["for-each-ref", f"refs/quipu/users/{user_a_id}"])
        
        # With prune enabled, this assertion would fail.
        # With prune disabled, this must pass.
        assert ref_hash in remote_refs_after

    def test_multi_device_reconciliation(self, sync_test_environment):
        """
        Tests the "Fetch -> Reconcile -> Push" flow.
        Simulates User A working on two devices.
        Device 2 creates Node X.
        Device 1 syncs -> Should fetch Node X and promote it to local head.
        """
        remote_path, user_a_path, _ = sync_test_environment
        
        # 1. Setup Device 2 for User A
        base_dir = user_a_path.parent
        user_a_device2_path = base_dir / "user_a_device2"
        run_git_command(base_dir, ["clone", str(remote_path), str(user_a_device2_path)])
        run_git_command(user_a_device2_path, ["config", "user.name", "User A"])
        run_git_command(user_a_device2_path, ["config", "user.email", "user.a@example.com"])

        # Onboard Device 2
        runner.invoke(app, ["sync", "--work-dir", str(user_a_device2_path), "--remote", "origin"])

        # 2. Device 2 creates a unique node
        (user_a_device2_path / "device2.md").write_text("~~~~~act\necho 'from device 2'\n~~~~~")
        runner.invoke(app, ["run", str(user_a_device2_path / "device2.md"), "--work-dir", str(user_a_device2_path), "-y"])
        
        # Get the hash
        d2_commits = run_git_command(user_a_device2_path, ["log", "--all", "--format=%H", "--grep=X-Quipu-Output-Tree"]).splitlines()
        d2_new_hash = d2_commits[0]

        # Device 2 Pushes
        runner.invoke(app, ["sync", "--work-dir", str(user_a_device2_path), "--remote", "origin"])

        # 3. Device 1 Syncs
        # Expectation: Device 1 should pull Device 2's work and show it in local heads
        sync_result = runner.invoke(app, ["sync", "--work-dir", str(user_a_path), "--remote", "origin"])
        assert sync_result.exit_code == 0
        
        # Verify Device 1 has the commit in LOCAL heads
        d1_local_refs = run_git_command(user_a_path, ["for-each-ref", "refs/quipu/local/heads"])
        assert d2_new_hash in d1_local_refs
~~~~~
