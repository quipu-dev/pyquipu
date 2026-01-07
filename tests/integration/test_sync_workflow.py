import sqlite3

import yaml
from pyquipu.cli.main import app
from pyquipu.common.identity import get_user_id_from_email
from pyquipu.test_utils.helpers import run_git_command
from typer.testing import CliRunner

runner = CliRunner()


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
            user_a_path, ["log", "--all", "--format=%H", "--grep=X-Quipu-Output-Tree"]
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
        # [FIX] Updated assertion to match new, more granular output
        assert "⬇️  正在拉取..." in sync_result.stderr
        assert "🤝 正在调和..." in sync_result.stderr

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
            assert row["owner_id"] == user_a_id, (
                f"Incorrect owner for commit {commit_hash}. Expected {user_a_id}, got {row['owner_id']}"
            )

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
        run_git_command(remote_path, ["for-each-ref", f"refs/quipu/users/{user_a_id}"])
        assert "plan3" in str(run_git_command(user_a_path, ["log", "--all"]))  # Verify creation

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
        runner.invoke(
            app, ["run", str(user_a_device2_path / "device2.md"), "--work-dir", str(user_a_device2_path), "-y"]
        )

        # Get the hash
        d2_commits = run_git_command(
            user_a_device2_path, ["log", "--all", "--format=%H", "--grep=X-Quipu-Output-Tree"]
        ).splitlines()
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
