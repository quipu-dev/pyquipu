import pytest
import subprocess
from pathlib import Path
from typer.testing import CliRunner

from quipu.core.state_machine import Engine
from quipu.core.file_system_storage import FileSystemHistoryReader, FileSystemHistoryWriter
from quipu.cli.main import app

# --- Fixtures ---

@pytest.fixture
def nav_workspace(tmp_path):
    """
    创建一个包含 Git 仓库和 Engine 实例的测试环境。
    """
    repo_path = tmp_path / "nav_repo"
    repo_path.mkdir()
    subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
    
    history_dir = repo_path / ".quipu" / "history"
    reader = FileSystemHistoryReader(history_dir)
    writer = FileSystemHistoryWriter(history_dir)
    engine = Engine(repo_path, reader=reader, writer=writer)
    
    # Helper to create distinct states
    def create_state(content: str) -> str:
        (repo_path / "file.txt").write_text(content)
        return engine.git_db.get_tree_hash()

    return engine, create_state

@pytest.fixture
def runner():
    return CliRunner()

# --- 1. Unit Tests (Engine Logic) ---

class TestNavigationEngine:

    def test_basic_back_and_forward(self, nav_workspace):
        engine, create_state = nav_workspace
        
        hash_a = create_state("A")
        hash_b = create_state("B")
        
        engine.visit(hash_a)
        engine.visit(hash_b)
        
        # We are at B, go back to A
        engine.back()
        assert (engine.root_dir / "file.txt").read_text() == "A"
        
        # We are at A, go forward to B
        engine.forward()
        assert (engine.root_dir / "file.txt").read_text() == "B"

    def test_boundary_conditions(self, nav_workspace):
        engine, create_state = nav_workspace
        
        hash_a = create_state("A")
        engine.visit(hash_a)
        
        # At the end, forward should do nothing
        assert engine.forward() is None
        assert (engine.root_dir / "file.txt").read_text() == "A"
        
        # At the beginning, back should do nothing
        assert engine.back() is None
        assert (engine.root_dir / "file.txt").read_text() == "A"

    def test_history_truncation_on_new_visit(self, nav_workspace):
        engine, create_state = nav_workspace
        
        hash_a = create_state("A")
        hash_b = create_state("B")
        hash_c = create_state("C")
        hash_d = create_state("D")
        
        engine.visit(hash_a)
        engine.visit(hash_b)
        engine.visit(hash_c)
        
        # History: [A, B, C], ptr at C
        
        # Go back to B
        engine.back()
        # History: [A, B, C], ptr at B
        
        # Now visit a new state D. This should truncate C.
        engine.visit(hash_d)
        # History: [A, B, D], ptr at D
        
        # Verify state
        assert (engine.root_dir / "file.txt").read_text() == "D"
        
        # Verify that forward is now impossible
        assert engine.forward() is None
        
        # Go back twice to verify the new history
        engine.back() # -> B
        assert (engine.root_dir / "file.txt").read_text() == "B"
        engine.back() # -> A
        assert (engine.root_dir / "file.txt").read_text() == "A"
        
    def test_visit_idempotency(self, nav_workspace):
        engine, create_state = nav_workspace
        hash_a = create_state("A")
        
        engine.visit(hash_a)
        engine.visit(hash_a)
        engine.visit(hash_a)
        
        log, _ = engine._read_nav()
        # The log might contain the initial HEAD, so we check the end
        assert log[-1] == hash_a
        assert len([h for h in log if h == hash_a]) <= 1 

# --- 2. Integration Tests (CLI) ---

class TestNavigationCLI:

    @pytest.fixture
    def cli_workspace(self, tmp_path):
        ws = tmp_path / "cli_ws"
        ws.mkdir()
        subprocess.run(["git", "init"], cwd=ws, check=True, capture_output=True)
        # Create some history nodes for checkout
        history_dir = ws / ".quipu" / "history"
        reader = FileSystemHistoryReader(history_dir)
        writer = FileSystemHistoryWriter(history_dir)
        engine = Engine(ws, reader=reader, writer=writer)

        (ws / "a.txt").write_text("A")
        hash_a = engine.git_db.get_tree_hash()
        engine.create_plan_node("_" * 40, hash_a, "State A")

        (ws / "b.txt").write_text("B")
        (ws / "a.txt").unlink()
        hash_b = engine.git_db.get_tree_hash()
        engine.create_plan_node(hash_a, hash_b, "State B")
        
        return ws, hash_a, hash_b

    def test_cli_back_forward_flow(self, runner, cli_workspace):
        workspace, hash_a, hash_b = cli_workspace
        
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

    def test_cli_boundary_messages(self, runner, cli_workspace):
        workspace, hash_a, hash_b = cli_workspace
        
        # Go to a known state
        runner.invoke(app, ["checkout", hash_a[:7], "-w", str(workspace), "-f"])

        # Back until the beginning
        runner.invoke(app, ["back", "-w", str(workspace)]) # to B
        result1 = runner.invoke(app, ["back", "-w", str(workspace)]) # to genesis state if any was recorded
        result2 = runner.invoke(app, ["back", "-w", str(workspace)]) # one more should hit boundary
        
        assert "已到达访问历史的起点" in result2.stderr
        
        # Forward until the end
        runner.invoke(app, ["forward", "-w", str(workspace)]) # to B
        runner.invoke(app, ["forward", "-w", str(workspace)]) # to A
        result3 = runner.invoke(app, ["forward", "-w", str(workspace)]) # should fail
        
        assert "已到达访问历史的终点" in result3.stderr