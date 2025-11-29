好的，我们来执行这项重构任务。

这个任务的目标是将 `tests/cli/test_navigation_commands.py` 文件中负责测试 `Engine` 核心导航逻辑的单元测试类 `TestNavigationEngine`，迁移到一个更合适的位置：`tests/engine/` 目录。这能让我们的测试结构与代码结构保持一致，职责更清晰。

我将分两步完成此操作：
1.  创建一个新的测试文件 `tests/engine/test_navigation.py`，并将 `TestNavigationEngine` 类及其依赖的 `nav_workspace` Fixture 移动到其中。
2.  清理原始的 `tests/cli/test_navigation_commands.py` 文件，使其只保留与 CLI 交互相关的集成测试。

## [WIP] refactor: 将 Engine 导航单元测试迁移到 tests/engine

### 用户需求
根据之前的分析，需要将 `tests/cli/test_navigation_commands.py` 中属于 `engine` 单元测试的 `TestNavigationEngine` 类，迁移到 `tests/engine/` 目录下，以改善测试代码的组织结构。

### 评论
这是一个清晰的重构步骤，遵循了“测试代码应与其所测试的源代码结构相对应”的最佳实践。将 `Engine` 层的单元测试从 `CLI` 层的集成测试中分离出来，可以显著提高测试代码库的可读性和可维护性。

### 目标
1.  在 `tests/engine/` 目录下创建一个新的 `test_navigation.py` 文件。
2.  将 `TestNavigationEngine` 类及其相关的 Fixture 从 `tests/cli/test_navigation_commands.py` 移动到新文件中。
3.  更新 `tests/cli/test_navigation_commands.py`，移除已迁移的代码和不再需要的导入。

### 基本原理
通过文件操作 (`write_file`) 来创建新文件并重写旧文件，以实现代码的迁移。这是一种原子化且可追溯的重构方式。`engine_instance` 这个根级 Fixture 的存在使得这种迁移变得非常简单，因为测试逻辑的依赖关系已经解耦。

### 标签
#intent/refine #flow/ready #priority/medium #comp/tests #concept/history #concept/navigation #scope/dx #ai/instruct #task/domain/testing #task/object/test-structure #task/action/refactor #task/state/begin

---

### Script

#### Acts 1: 创建新的 Engine 导航测试文件

我们将创建 `tests/engine/test_navigation.py` 文件，并填入从原文件中提取的单元测试代码。

~~~~~act
write_file tests/engine/test_navigation.py
~~~~~
~~~~~python
import pytest
from pathlib import Path
from quipu.engine.state_machine import Engine


@pytest.fixture
def nav_workspace(engine_instance: Engine):
    """
    创建一个包含 Git 仓库和 Engine 实例的测试环境。
    """
    engine = engine_instance
    repo_path = engine.root_dir

    # Helper to create distinct states
    def create_state(content: str) -> str:
        (repo_path / "file.txt").write_text(content)
        return engine.git_db.get_tree_hash()

    return engine, create_state


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
        engine.back()  # -> B
        assert (engine.root_dir / "file.txt").read_text() == "B"
        engine.back()  # -> A
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
~~~~~

#### Acts 2: 清理原始的 CLI 测试文件

现在，我们将重写 `tests/cli/test_navigation_commands.py`，移除单元测试部分，使其专注于 CLI 集成测试。

~~~~~act
write_file tests/cli/test_navigation_commands.py
~~~~~
~~~~~python
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
~~~~~

### 下一步建议
重构已完成。现在可以运行测试套件，以验证所有测试（包括新旧文件中的测试）是否都能正常通过。

你可以运行 `pytest tests/engine/test_navigation.py` 和 `pytest tests/cli/test_navigation_commands.py` 来分别验证，或直接运行 `pytest` 来执行完整的测试。
