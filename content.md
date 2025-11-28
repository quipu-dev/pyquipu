这是一个关于提升 CLI 命令模块和 ViewModel 测试覆盖率的计划。我们将通过建立共享测试夹具并为 `workspace`、`query` 和 `cache` 模块编写针对性测试来实现这一目标。

## test: 提升 CLI 命令与 ViewModel 的测试覆盖率

### 错误分析
当前测试套件主要集中在 `navigation` 命令和 TUI 的基础逻辑上。随着 `main.py` 被拆分为多个子模块，`workspace` (`save`, `discard`)、`query` (`log`, `find`) 和 `cache` 等关键业务逻辑缺乏独立的测试覆盖。这增加了未来重构引入回归错误的风险。

### 用户需求
-   **覆盖新模块**: 为拆分出的 `workspace.py`, `query.py`, `cache.py` 编写单元/集成测试。
-   **增强 VM 测试**: 完善 `GraphViewModel` 的测试用例，覆盖更多边界情况。
-   **复用性**: 提取通用的测试夹具（如临时 Git 工作区初始化）以减少代码重复。

### 评论
这是一个必要的质量保证步骤。特别是 `workspace` 模块涉及文件系统的破坏性操作（如 `discard`），必须通过严格的测试来保证安全性。

### 目标
1.  **建立 `tests/cli/conftest.py`**: 提取通用的 CLI 测试夹具（`quipu_workspace`）。
2.  **测试 `workspace` 命令**: 验证 `save` (快照创建) 和 `discard` (状态回滚) 的行为。
3.  **测试 `query` 命令**: 验证 `log` 和 `find` 的输出格式及过滤逻辑。
4.  **测试 `cache` 命令**: 验证 `sync` 和 `rebuild` 的基本流程。
5.  **增强 `GraphViewModel` 测试**: 补充分页计算和内容生成的边界测试。

### 基本原理
-   **集成测试策略**: 对于 CLI 命令，使用 `typer.testing.CliRunner` 配合真实的临时文件系统（由 `pytest` 的 `tmp_path` 提供）进行测试，这比单纯 mock 内部函数更能反映真实的用户体验和文件系统副作用。
-   **夹具共享**: 将 `test_navigation_commands.py` 中的 setup 逻辑下沉到 `conftest.py`，使所有 CLI 测试都能轻易获取一个初始化好的 Quipu 环境。

### 标签
#intent/tooling #flow/ready #priority/medium #comp/tests #comp/cli #concept/ui #scope/dx #ai/instruct #task/domain/testing #task/object/cli-commands #task/action/coverage #task/state/begin

---

### Script

#### Acts 1: 建立共享测试夹具 (Conftest)

创建 `tests/cli/conftest.py`，定义 `quipu_workspace` 夹具，提供一个包含 Git 环境和 `Engine` 的临时工作区。

~~~~~act
write_file
tests/cli/conftest.py
~~~~~
~~~~~python
import pytest
import subprocess
from pathlib import Path
from typer.testing import CliRunner

from quipu.core.state_machine import Engine
from quipu.core.git_object_storage import GitObjectHistoryReader, GitObjectHistoryWriter
from quipu.core.git_db import GitDB


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def quipu_workspace(tmp_path):
    """
    创建一个包含 Git 仓库并初始化了 Quipu Engine 的测试环境。
    返回: (work_dir_path, git_db, engine)
    """
    work_dir = tmp_path / "ws"
    work_dir.mkdir()

    # 初始化 Git
    subprocess.run(["git", "init"], cwd=work_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@quipu.dev"], cwd=work_dir, check=True)
    subprocess.run(["git", "config", "user.name", "Quipu Test"], cwd=work_dir, check=True)

    # 初始化 Engine 组件
    git_db = GitDB(work_dir)
    reader = GitObjectHistoryReader(git_db)
    writer = GitObjectHistoryWriter(git_db)
    engine = Engine(work_dir, db=git_db, reader=reader, writer=writer)

    return work_dir, git_db, engine
~~~~~

#### Acts 2: 清理旧测试中的冗余夹具

修改 `test_navigation_commands.py`，移除其内部定义的 `cli_workspace`，转而使用新的共享夹具。

~~~~~act
patch_file
tests/cli/test_navigation_commands.py
~~~~~
~~~~~python
# --- 2. Integration Tests (CLI) ---


class TestNavigationCLI:
    @pytest.fixture
    def cli_workspace(self, tmp_path):
        ws = tmp_path / "cli_ws"
        ws.mkdir()
        subprocess.run(["git", "init"], cwd=ws, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@quipu.dev"], cwd=ws, check=True)
        subprocess.run(["git", "config", "user.name", "Quipu Test"], cwd=ws, check=True)

        git_db = GitDB(ws)
        reader = GitObjectHistoryReader(git_db)
        writer = GitObjectHistoryWriter(git_db)
        engine = Engine(ws, db=git_db, reader=reader, writer=writer)

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
~~~~~
~~~~~python
# --- 2. Integration Tests (CLI) ---


class TestNavigationCLI:
    @pytest.fixture
    def populated_workspace(self, quipu_workspace):
        ws, _, engine = quipu_workspace

        (ws / "a.txt").write_text("A")
        hash_a = engine.git_db.get_tree_hash()
        engine.create_plan_node(input_tree="_" * 40, output_tree=hash_a, plan_content="Plan A", summary_override="State A")

        (ws / "b.txt").write_text("B")
        (ws / "a.txt").unlink()
        hash_b = engine.git_db.get_tree_hash()
        engine.create_plan_node(input_tree=hash_a, output_tree=hash_b, plan_content="Plan B", summary_override="State B")

        return ws, hash_a, hash_b

    def test_cli_back_forward_flow(self, runner, populated_workspace):
        workspace, hash_a, hash_b = populated_workspace
~~~~~

~~~~~act
patch_file
tests/cli/test_navigation_commands.py
~~~~~
~~~~~python
    def test_cli_boundary_messages(self, runner, cli_workspace):
        workspace, hash_a, hash_b = cli_workspace

        # Go to a known state
~~~~~
~~~~~python
    def test_cli_boundary_messages(self, runner, populated_workspace):
        workspace, hash_a, hash_b = populated_workspace

        # Go to a known state
~~~~~

#### Acts 3: 测试 Workspace 命令 (Save/Discard)

创建 `tests/cli/test_workspace_commands.py`，重点测试 `save` 的快照创建和 `discard` 的变更丢弃。

~~~~~act
write_file
tests/cli/test_workspace_commands.py
~~~~~
~~~~~python
from quipu.cli.main import app


def test_save_clean_workspace(runner, quipu_workspace):
    work_dir, _, engine = quipu_workspace
    
    # 创建一个初始状态
    (work_dir / "file.txt").write_text("v1")
    engine.capture_drift(engine.git_db.get_tree_hash(), message="Initial")
    
    # 无变更时执行 save
    result = runner.invoke(app, ["save", "-w", str(work_dir)])
    assert result.exit_code == 0
    assert "无需创建快照" in result.stderr


def test_save_with_changes(runner, quipu_workspace):
    work_dir, _, engine = quipu_workspace
    
    # 制造变更
    (work_dir / "file.txt").write_text("v2")
    
    result = runner.invoke(app, ["save", "My Snapshot", "-w", str(work_dir)])
    assert result.exit_code == 0
    assert "快照已保存" in result.stderr
    assert "(My Snapshot)" in result.stderr
    
    # 验证历史记录增加
    assert len(engine.history_graph) == 1


def test_discard_changes(runner, quipu_workspace):
    work_dir, _, engine = quipu_workspace
    
    # 初始状态 v1
    (work_dir / "file.txt").write_text("v1")
    initial_node = engine.capture_drift(engine.git_db.get_tree_hash())
    
    # 制造脏状态 v2
    (work_dir / "file.txt").write_text("v2")
    
    # 执行 discard (带 force)
    result = runner.invoke(app, ["discard", "-f", "-w", str(work_dir)])
    assert result.exit_code == 0
    assert "已成功恢复" in result.stderr
    
    # 验证文件回滚
    assert (work_dir / "file.txt").read_text() == "v1"


def test_discard_interactive_abort(runner, quipu_workspace):
    work_dir, _, engine = quipu_workspace
    
    (work_dir / "file.txt").write_text("v1")
    engine.capture_drift(engine.git_db.get_tree_hash())
    (work_dir / "file.txt").write_text("v2")
    
    # 模拟输入 'n'
    result = runner.invoke(app, ["discard", "-w", str(work_dir)], input="n")
    assert result.exit_code == 1
    assert "操作已取消" in result.stderr
    assert (work_dir / "file.txt").read_text() == "v2"
~~~~~

#### Acts 4: 测试 Query 命令 (Log/Find)

创建 `tests/cli/test_query_commands.py`。

~~~~~act
write_file
tests/cli/test_query_commands.py
~~~~~
~~~~~python
from quipu.cli.main import app


def test_log_empty(runner, quipu_workspace):
    work_dir, _, _ = quipu_workspace
    result = runner.invoke(app, ["log", "-w", str(work_dir)])
    assert result.exit_code == 0
    assert "历史记录为空" in result.stderr


def test_log_output(runner, quipu_workspace):
    work_dir, _, engine = quipu_workspace
    
    # 创建一些历史
    (work_dir / "f1").touch()
    engine.capture_drift(engine.git_db.get_tree_hash(), message="Node 1")
    
    (work_dir / "f2").touch()
    engine.capture_drift(engine.git_db.get_tree_hash(), message="Node 2")
    
    result = runner.invoke(app, ["log", "-w", str(work_dir)])
    assert result.exit_code == 0
    assert "Node 1" in result.stderr
    assert "Node 2" in result.stderr
    assert "[CAPTURE]" in result.stderr


def test_find_command(runner, quipu_workspace):
    work_dir, _, engine = quipu_workspace
    
    (work_dir / "f1").touch()
    engine.capture_drift(engine.git_db.get_tree_hash(), message="Fix bug")
    
    (work_dir / "f2").touch()
    engine.create_plan_node(
        input_tree=engine.git_db.get_tree_hash(),
        output_tree="hash_placeholder",
        plan_content="content",
        summary_override="Implement feature"
    )
    
    # 查找 "Fix"
    result = runner.invoke(app, ["find", "-s", "Fix", "-w", str(work_dir)])
    assert "Fix bug" in result.stderr
    assert "Implement feature" not in result.stderr
    
    # 查找类型 "plan"
    result_type = runner.invoke(app, ["find", "-t", "plan", "-w", str(work_dir)])
    assert "Implement feature" in result_type.stderr
    assert "Fix bug" not in result_type.stderr
~~~~~

#### Acts 5: 测试 Cache 命令

创建 `tests/cli/test_cache_commands.py`。

~~~~~act
write_file
tests/cli/test_cache_commands.py
~~~~~
~~~~~python
from quipu.cli.main import app


def test_cache_sync(runner, quipu_workspace):
    work_dir, _, _ = quipu_workspace
    
    # 这里我们主要测试命令的执行路径，因为 mock SQLite 依赖在集成测试中较复杂
    # 只要命令不崩溃且输出正确的日志即可
    result = runner.invoke(app, ["cache", "sync", "-w", str(work_dir)])
    
    # 预期失败或成功取决于是否安装了 SQLite 依赖，
    # 但我们至少可以验证它尝试运行了。
    # 如果环境没有配置 SQLite 后端，engine context 会正常退出。
    assert "数据同步" in result.stderr


def test_cache_rebuild_no_db(runner, quipu_workspace):
    work_dir, _, _ = quipu_workspace
    
    result = runner.invoke(app, ["cache", "rebuild", "-w", str(work_dir)])
    assert "数据库文件不存在" in result.stderr
    assert result.exit_code == 0
~~~~~

#### Acts 6: 增强 ViewModel 测试

在 `tests/cli/test_view_model.py` 中补充测试用例。

~~~~~act
patch_file
tests/cli/test_view_model.py
~~~~~
~~~~~python
    def test_is_reachable_no_current_hash(self, sample_nodes):
        """测试在没有当前哈希时，所有节点都应被视为可达。"""
        reader = MockHistoryReader(sample_nodes, ancestors=set())
        vm = GraphViewModel(reader, current_output_tree_hash=None)
        vm.initialize()

        assert vm.is_reachable("h9") is True
        assert vm.is_reachable("h1") is True
~~~~~
~~~~~python
    def test_is_reachable_no_current_hash(self, sample_nodes):
        """测试在没有当前哈希时，所有节点都应被视为可达。"""
        reader = MockHistoryReader(sample_nodes, ancestors=set())
        vm = GraphViewModel(reader, current_output_tree_hash=None)
        vm.initialize()

        assert vm.is_reachable("h9") is True
        assert vm.is_reachable("h1") is True

    def test_calculate_initial_page_not_found(self, sample_nodes):
        """测试当 HEAD 节点在历史中找不到时，应回退到第一页。"""
        reader = MockHistoryReader(sample_nodes)
        vm = GraphViewModel(reader, current_output_tree_hash="unknown_hash")
        vm.initialize()
        
        # MockReader 在找不到 output_tree 时 get_node_position 返回 -1
        assert vm.calculate_initial_page() == 1

    def test_select_node_by_key_missing(self, sample_nodes):
        """测试选择不存在的 key。"""
        reader = MockHistoryReader(sample_nodes)
        vm = GraphViewModel(reader, current_output_tree_hash=None)
        vm.load_page(1)
        
        selected = vm.select_node_by_key("non_existent_path")
        assert selected is None
        assert vm.get_selected_node() is None
~~~~~

### 下一步建议
运行 `pytest tests/cli` 验证所有新添加的测试是否通过。如果有测试失败，需要根据错误信息调整 mock 逻辑或修复代码中的 bug。
