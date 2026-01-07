import subprocess

import pytest
from pyquipu.engine.state_machine import Engine


def test_align_orphan_state(engine_instance: Engine):
    """
    测试场景：在一个没有历史记录的项目中运行时，
    引擎应能正确识别为 "ORPHAN" 状态 (适用于两种后端)。
    """
    engine, repo_path = engine_instance, engine_instance.root_dir

    (repo_path / "main.py").write_text("print('new project')", "utf-8")

    status = engine.align()

    assert status == "ORPHAN"
    assert engine.current_node is None


def test_capture_drift_git_object(engine_instance: Engine):
    """
    测试场景 (GitObject Backend)：当工作区处于 DIRTY 状态时，引擎应能成功捕获变化，
    创建一个新的 Capture 节点，并更新 Git 引用。
    """
    engine, repo_path = engine_instance, engine_instance.root_dir

    # 1. Create initial state and corresponding node
    (repo_path / "main.py").write_text("version = 1", "utf-8")
    initial_hash = engine.git_db.get_tree_hash()
    initial_node = engine.writer.create_node(
        "plan", "4b825dc642cb6eb9a060e54bf8d69288fbee4904", initial_hash, "Initial content"
    )
    engine.align()  # Load the new node into the engine's graph

    # 2. Modify workspace to create a dirty state
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

    # Key Assertion: Verify that two distinct head refs now exist
    heads_cmd = ["git", "for-each-ref", "--format=%(objectname)", "refs/quipu/local/heads/"]
    all_heads = set(subprocess.check_output(heads_cmd, cwd=repo_path, text=True).strip().splitlines())
    assert len(all_heads) == 2, "应该存在两个独立的 head 引用"
    assert initial_node.commit_hash in all_heads
    assert capture_node.commit_hash in all_heads

    # Verify the new commit has the correct parent
    parent_of_capture = (
        subprocess.check_output(["git", "rev-parse", f"{capture_node.commit_hash}^"], cwd=repo_path).decode().strip()
    )
    assert parent_of_capture == initial_node.commit_hash


class TestEngineFindNodes:
    @pytest.fixture
    def populated_engine(self, engine_instance: Engine):
        """
        Populates an engine instance with a linear history using shared test helpers.
        History: (Genesis) -> Plan -> Capture -> Plan
        """
        import time

        from pyquipu.test_utils.helpers import (
            EMPTY_TREE_HASH,
            create_capture_node_with_change,
            create_plan_node_with_change,
        )

        engine = engine_instance
        parent = EMPTY_TREE_HASH

        # Node 1 (Plan)
        parent = create_plan_node_with_change(engine, parent, "f_a.txt", "content_a", "# feat: Add feature A")
        time.sleep(0.01)  # Ensure unique timestamps for ordering

        # Node 2 (Capture) - Parented to Node 1's state
        parent = create_capture_node_with_change(engine, "f_b.txt", "content_b", "Snapshot after feature A")
        time.sleep(0.01)

        # Node 3 (Plan) - Parented to Node 2's state
        parent = create_plan_node_with_change(engine, parent, "f_c.txt", "content_c", "refactor: Cleanup code")

        # Re-align to load the full graph into the reader component for testing
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
    def test_sync_creates_file_if_not_exists(self, engine_instance: Engine):
        """测试：如果 exclude 文件不存在，应能根据默认配置创建它。"""
        engine, repo_path = engine_instance, engine_instance.root_dir

        (repo_path / ".quipu").mkdir(exist_ok=True)

        # 重新初始化 Engine 以触发同步逻辑
        engine = Engine(repo_path, db=engine.git_db, reader=engine.reader, writer=engine.writer)

        exclude_file = repo_path / ".git" / "info" / "exclude"
        assert exclude_file.exists()
        content = exclude_file.read_text("utf-8")

        assert "# --- Managed by Quipu ---" in content
        assert ".envs" in content

    def test_sync_appends_to_existing_file(self, engine_instance: Engine):
        """测试：如果 exclude 文件已存在，应追加 Quipu 块而不是覆盖。"""
        engine, repo_path = engine_instance, engine_instance.root_dir

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

    def test_sync_updates_existing_block(self, engine_instance: Engine):
        """测试：如果 Quipu 块已存在，应更新其内容。"""
        engine, repo_path = engine_instance, engine_instance.root_dir

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

    def test_sync_uses_user_config(self, engine_instance: Engine):
        """测试：应优先使用 .quipu/config.yml 中的用户配置。"""
        import yaml

        engine, repo_path = engine_instance, engine_instance.root_dir

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
