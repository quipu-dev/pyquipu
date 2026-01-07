from pathlib import Path

import pytest
from pyquipu.engine.state_machine import Engine
from pyquipu.test_utils.helpers import EMPTY_TREE_HASH, InMemoryDB, InMemoryHistoryManager


@pytest.fixture
def memory_engine(tmp_path: Path) -> Engine:
    db = InMemoryDB()
    history_manager = InMemoryHistoryManager(db)
    # The root_dir is just a placeholder for the in-memory engine
    engine = Engine(root_dir=tmp_path, db=db, reader=history_manager, writer=history_manager)
    return engine


class TestEngineWithMemoryBackend:
    def test_align_clean_genesis(self, memory_engine: Engine):
        status = memory_engine.align()
        assert status == "CLEAN"
        assert memory_engine.current_node is None

    def test_capture_drift_from_genesis(self, memory_engine: Engine):
        # 1. 模拟文件变更
        memory_engine.git_db.vfs.write("a.txt", "hello")
        current_hash = memory_engine.git_db.get_tree_hash()
        assert current_hash != EMPTY_TREE_HASH

        # 2. 对齐，应为 DIRTY (或 ORPHAN)
        status = memory_engine.align()
        assert status == "ORPHAN"

        # 3. 捕获漂移
        node = memory_engine.capture_drift(current_hash, message="Initial commit")
        assert node is not None
        assert node.node_type == "capture"
        assert node.input_tree == EMPTY_TREE_HASH
        assert node.output_tree == current_hash

        # 4. 再次对齐，应为 CLEAN
        status_after = memory_engine.align()
        assert status_after == "CLEAN"
        assert memory_engine.current_node == node

    def test_plan_node_creation(self, memory_engine: Engine):
        # State A
        memory_engine.git_db.vfs.write("a.txt", "v1")
        hash_a = memory_engine.git_db.get_tree_hash()
        node_a = memory_engine.create_plan_node(EMPTY_TREE_HASH, hash_a, "Plan A")

        # State B
        memory_engine.git_db.vfs.write("a.txt", "v2")
        hash_b = memory_engine.git_db.get_tree_hash()
        node_b = memory_engine.create_plan_node(hash_a, hash_b, "Plan B")

        assert len(memory_engine.history_graph) == 2
        assert node_b.parent == node_a
        assert node_a.children == [node_b]

        # 验证 checkout
        memory_engine.checkout(hash_a)
        assert memory_engine.git_db.vfs.read("a.txt") == "v1"
