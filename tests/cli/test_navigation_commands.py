import pytest
from quipu.cli.main import app


class TestNavigationCLI:
    @pytest.fixture
    def populated_workspace(self, quipu_workspace):
        ws, _, engine = quipu_workspace

        (ws / "a.txt").write_text("A")
        hash_a = engine.git_db.get_tree_hash()
        engine.create_plan_node(
            input_tree="_" * 40, output_tree=hash_a, plan_content="Plan A", summary_override="State A"
        )

        (ws / "b.txt").write_text("B")
        (ws / "a.txt").unlink()
        hash_b = engine.git_db.get_tree_hash()
        engine.create_plan_node(
            input_tree=hash_a, output_tree=hash_b, plan_content="Plan B", summary_override="State B"
        )

        return ws, hash_a, hash_b

    def test_cli_back_forward_flow(self, runner, populated_workspace):
        workspace, hash_a, hash_b = populated_workspace

        # Initial state is B. Let's checkout to A.
        runner.invoke(app, ["checkout", hash_a[:7], "-w", str(workspace), "-f"])
        assert (workspace / "a.txt").exists()
        assert not (workspace / "b.txt").exists()

        # Now we are at A. Let's go back. It should go to the previous state (B).
        result_back = runner.invoke(app, ["back", "-w", str(workspace)])
        assert result_back.exit_code == 0
        assert "✅ 已后退到状态" in result_back.stderr
        assert (workspace / "b.txt").exists()
        assert not (workspace / "a.txt").exists()

        # Now we are back at B. Let's go forward to A again.
        result_fwd = runner.invoke(app, ["forward", "-w", str(workspace)])
        assert result_fwd.exit_code == 0
        assert "✅ 已前进到状态" in result_fwd.stderr
        assert (workspace / "a.txt").exists()
        assert not (workspace / "b.txt").exists()

    def test_cli_boundary_messages(self, runner, populated_workspace):
        workspace, hash_a, hash_b = populated_workspace

        # Go to a known state
        runner.invoke(app, ["checkout", hash_a[:7], "-w", str(workspace), "-f"])

        # Back until the beginning
        runner.invoke(app, ["back", "-w", str(workspace)])  # to B
        runner.invoke(app, ["back", "-w", str(workspace)])  # to genesis state if any was recorded
        result2 = runner.invoke(app, ["back", "-w", str(workspace)])  # one more should hit boundary

        assert "已到达访问历史的起点" in result2.stderr

        # Forward until the end
        runner.invoke(app, ["forward", "-w", str(workspace)])  # to B
        runner.invoke(app, ["forward", "-w", str(workspace)])  # to A
        result3 = runner.invoke(app, ["forward", "-w", str(workspace)])  # should fail

        assert "已到达访问历史的终点" in result3.stderr
