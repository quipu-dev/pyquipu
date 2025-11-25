# test: 为时序性导航添加单元和集成测试

## 用户需求
新实现的时序性导航 (`back`/`forward`) 功能目前缺少测试覆盖。需要编写一套完整的测试用例来保证其功能的正确性、健壮性，并防止未来发生功能退化。

## 评论
这是确保新功能质量和长期可维护性的标准步骤。测试用例尤其需要覆盖边界条件和历史分叉等关键逻辑。

## 目标
1.  为 `Engine` 类中的导航逻辑 (`_read_nav`, `_write_nav`, `_append_nav`, `back`, `forward`, `visit`) 编写单元测试。
2.  为 `quipu back` 和 `quipu forward` 命令编写集成测试。
3.  确保所有会改变工作区状态的命令都被正确集成到导航历史记录中。

## 基本原理
创建一个新的测试文件 `tests/test_navigation.py`。
*   在 `TestNavigationEngine` 类中，使用 `pytest` fixtures 模拟 `.quipu` 目录下的 `nav_log` 和 `nav_ptr` 文件，直接测试 `Engine` 实例的方法。
*   在 `TestNavigationCLI` 类中，使用 `CliRunner` 调用 `quipu back`/`forward` 等命令，并检查文件系统的最终状态和命令的输出。

## 标签
#test #navigation #engine #cli

---

## Script

### Acts 1: 创建导航功能测试文件

创建一个新的测试文件 `tests/test_navigation.py`，并填充覆盖核心场景的测试用例。

~~~~~act
write_file
~~~~~

~~~~~path
tests/test_navigation.py
~~~~~

~~~~~python
import pytest
import subprocess
from pathlib import Path
from typer.testing import CliRunner

from quipu.core.state_machine import Engine
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
    
    engine = Engine(repo_path)
    
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
        assert len([h for h in log if h == hash_a]) == 1 # A should appear only once

# --- 2. Integration Tests (CLI) ---

class TestNavigationCLI:

    @pytest.fixture
    def cli_workspace(self, tmp_path):
        ws = tmp_path / "cli_ws"
        ws.mkdir()
        subprocess.run(["git", "init"], cwd=ws, check=True, capture_output=True)
        # Create some history nodes for checkout
        engine = Engine(ws)
        (ws / "a.txt").write_text("A")
        hash_a = engine.git_db.get_tree_hash()
        engine.create_plan_node("root", hash_a, "State A")

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
        result1 = runner.invoke(app, ["back", "-w", str(workspace)]) # to genesis
        result2 = runner.invoke(app, ["back", "-w", str(workspace)]) # should fail
        
        assert "已到达访问历史的起点" in result2.stderr
        
        # Forward until the end
        runner.invoke(app, ["forward", "-w", str(workspace)]) # to B
        runner.invoke(app, ["forward", "-w", str(workspace)]) # to A
        result3 = runner.invoke(app, ["forward", "-w", str(workspace)]) # should fail
        
        assert "已到达访问历史的终点" in result3.stderr
~~~~~