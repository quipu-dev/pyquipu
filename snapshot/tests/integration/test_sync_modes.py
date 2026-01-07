from pyquipu.cli.main import app
from pyquipu.common.identity import get_user_id_from_email
from typer.testing import CliRunner

from pyquipu.test_utils.helpers import create_node_via_cli, run_git_command

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
