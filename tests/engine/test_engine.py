import pytest
import subprocess
from pathlib import Path
from datetime import datetime
from quipu.core.state_machine import Engine
from quipu.core.git_db import GitDB
from quipu.core.git_object_storage import GitObjectHistoryReader, GitObjectHistoryWriter


@pytest.fixture
def engine_setup(tmp_path):
    """
    创建一个包含 Git 仓库和 Engine 实例的测试环境。
    默认使用新的 GitObject 存储后端。
    """
    repo_path = tmp_path / "test_repo"
    repo_path.mkdir()
    subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@quipu.dev"], cwd=repo_path, check=True)
    subprocess.run(["git", "config", "user.name", "Quipu Test"], cwd=repo_path, check=True)

    git_db = GitDB(repo_path)
    reader = GitObjectHistoryReader(git_db)
    writer = GitObjectHistoryWriter(git_db)
    engine = Engine(repo_path, db=git_db, reader=reader, writer=writer)

    return engine, repo_path


def test_align_orphan_state(engine_setup):
    """
    测试场景：在一个没有历史记录的项目中运行时，
    引擎应能正确识别为 "ORPHAN" 状态 (适用于两种后端)。
    """
    engine, repo_path = engine_setup

    (repo_path / "main.py").write_text("print('new project')", "utf-8")

    status = engine.align()

    assert status == "ORPHAN"
    assert engine.current_node is None


def test_capture_drift_git_object(engine_setup):
    """
    测试场景 (GitObject Backend)：当工作区处于 DIRTY 状态时，引擎应能成功捕获变化，
    创建一个新的 Capture 节点，并更新 Git 引用。
    """
    engine, repo_path = engine_setup

    (repo_path / "main.py").write_text("version = 1", "utf-8")
    initial_hash = engine.git_db.get_tree_hash()

    # Manually create an initial commit to act as parent
    initial_commit = engine.git_db.commit_tree(initial_hash, parent_hashes=None, message="Initial")
    engine.git_db.update_ref("refs/quipu/history", initial_commit)

    # Create the first node using the writer to simulate a full flow
    engine.writer.create_node("plan", "_" * 40, initial_hash, "Initial content")
    initial_commit = engine.git_db._run(["rev-parse", "refs/quipu/history"]).stdout.strip()

    # Re-align to load the node we just created
    engine.align()

    (repo_path / "main.py").write_text("version = 2", "utf-8")
    dirty_hash = engine.git_db.get_tree_hash()
    assert initial_hash != dirty_hash

    # --- The Action ---
    capture_node = engine.capture_drift(dirty_hash)

    # --- Assertions ---
    assert len(engine.history_graph) == 2, "历史图谱中应有两个节点"
    assert engine.current_node is not None
    assert engine.current_node.output_tree == dirty_hash
    assert capture_node.node_type == "capture"
    assert capture_node.input_tree == initial_hash

    # Key Assertion: Verify the Git ref was updated by the writer
    latest_ref_commit = (
        subprocess.check_output(["git", "rev-parse", "refs/quipu/history"], cwd=repo_path).decode().strip()
    )
    assert latest_ref_commit != initial_commit, "Git 引用必须更新到新的锚点"

    # Verify the new commit has the correct parent
    parent_of_latest = (
        subprocess.check_output(["git", "rev-parse", f"{latest_ref_commit}^"], cwd=repo_path).decode().strip()
    )
    assert parent_of_latest == initial_commit


class TestEngineFindNodes:
    @pytest.fixture
    def populated_engine(self, engine_setup):
        import time

        engine, repo_path = engine_setup

        def add_commit(filename, content, message, node_type, parent_hash):
            """辅助函数：创建文件变更并生成一个新节点"""
            (repo_path / filename).write_text(content)
            time.sleep(0.01)  # 确保时间戳唯一
            new_hash = engine.git_db.get_tree_hash()
            if node_type == "plan":
                engine.create_plan_node(parent_hash, new_hash, message)
            else:  # capture
                # 对于 capture，message 是用户备注，不是 plan content
                engine.capture_drift(new_hash, message=message)
            return new_hash

        # 创世状态
        parent = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"

        # Node 1 (Plan)
        parent = add_commit("f_a.txt", "content_a", "# feat: Add feature A", "plan", parent)
        # Node 2 (Capture)
        parent = add_commit("f_b.txt", "content_b", "Snapshot after feature A", "capture", parent)
        # Node 3 (Plan)
        parent = add_commit("f_c.txt", "content_c", "refactor: Cleanup code", "plan", parent)

        # 重新对齐以加载完整的图谱
        engine.align()
        return engine

    def test_find_by_type(self, populated_engine):
        plans = populated_engine.find_nodes(node_type="plan")
        captures = populated_engine.find_nodes(node_type="capture")

        assert len(plans) == 2
        assert all(p.node_type == "plan" for p in plans)

        assert len(captures) == 1
        assert captures[0].node_type == "capture"

    def test_find_by_summary_regex(self, populated_engine):
        feat_nodes = populated_engine.find_nodes(summary_regex="feat:")
        assert len(feat_nodes) == 1
        assert "Add feature A" in feat_nodes[0].summary

        snapshot_nodes = populated_engine.find_nodes(summary_regex="snapshot")
        assert len(snapshot_nodes) == 1
        assert "Snapshot after" in snapshot_nodes[0].summary

    def test_find_combined_filters(self, populated_engine):
        results = populated_engine.find_nodes(summary_regex="refactor", node_type="plan")
        assert len(results) == 1
        assert "Cleanup code" in results[0].summary

        # 使用更精确的正则表达式 (^feat:) 避免匹配 'feature'
        empty_results = populated_engine.find_nodes(summary_regex="^feat:", node_type="capture")
        assert len(empty_results) == 0

    def test_find_limit(self, populated_engine):
        results = populated_engine.find_nodes(limit=1)
        assert len(results) == 1
        # 应该是最新的节点
        assert "Cleanup code" in results[0].summary


class TestPersistentIgnores:
    def test_sync_creates_file_if_not_exists(self, engine_setup):
        """测试：如果 exclude 文件不存在，应能根据默认配置创建它。"""
        engine, repo_path = engine_setup

        (repo_path / ".quipu").mkdir(exist_ok=True)

        # 重新初始化 Engine 以触发同步逻辑
        engine = Engine(repo_path, db=engine.git_db, reader=engine.reader, writer=engine.writer)

        exclude_file = repo_path / ".git" / "info" / "exclude"
        assert exclude_file.exists()
        content = exclude_file.read_text("utf-8")

        assert "# --- Managed by Quipu ---" in content
        assert ".envs" in content

    def test_sync_appends_to_existing_file(self, engine_setup):
        """测试：如果 exclude 文件已存在，应追加 Quipu 块而不是覆盖。"""
        engine, repo_path = engine_setup

        exclude_file = repo_path / ".git" / "info" / "exclude"
        exclude_file.parent.mkdir(exist_ok=True)
        user_content = "# My personal ignores\n*.log\n"
        exclude_file.write_text(user_content)

        # 重新初始化 Engine 以触发同步逻辑
        engine = Engine(repo_path, db=engine.git_db, reader=engine.reader, writer=engine.writer)

        content = exclude_file.read_text("utf-8")
        assert user_content in content
        assert "# --- Managed by Quipu ---" in content
        assert "o.md" in content

    def test_sync_updates_existing_block(self, engine_setup):
        """测试：如果 Quipu 块已存在，应更新其内容。"""
        engine, repo_path = engine_setup

        exclude_file = repo_path / ".git" / "info" / "exclude"
        exclude_file.parent.mkdir(exist_ok=True)

        old_block = "# --- Managed by Quipu ---\nold_rule/\n# --- End Managed by Quipu ---"
        user_content = f"# My ignores\n{old_block}\n# More ignores"
        exclude_file.write_text(user_content)

        # 重新初始化 Engine 以触发同步逻辑
        engine = Engine(repo_path, db=engine.git_db, reader=engine.reader, writer=engine.writer)

        content = exclude_file.read_text("utf-8")
        assert "old_rule/" not in content
        assert ".vscode" in content
        assert "# My ignores" in content
        assert "# More ignores" in content

    def test_sync_uses_user_config(self, engine_setup):
        """测试：应优先使用 .quipu/config.yml 中的用户配置。"""
        import yaml

        engine, repo_path = engine_setup

        config_dir = repo_path / ".quipu"
        config_dir.mkdir(exist_ok=True)
        config_file = config_dir / "config.yml"

        user_ignores = {"sync": {"persistent_ignores": ["custom_dir/", "*.tmp"]}}
        config_file.write_text(yaml.dump(user_ignores), "utf-8")

        # 重新初始化 Engine 以触发同步逻辑
        engine = Engine(repo_path, db=engine.git_db, reader=engine.reader, writer=engine.writer)

        exclude_file = repo_path / ".git" / "info" / "exclude"
        content = exclude_file.read_text("utf-8")

        assert "custom_dir/" in content
        assert "*.tmp" in content
        assert ".envs" not in content
