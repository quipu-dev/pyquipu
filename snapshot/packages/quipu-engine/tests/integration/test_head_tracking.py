import pytest
from pyquipu.engine.git_object_storage import GitObjectHistoryReader, GitObjectHistoryWriter
from pyquipu.engine.state_machine import Engine


class TestHeadTracking:
    @pytest.fixture
    def engine_with_repo(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        import subprocess

        subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
        # Config git user
        subprocess.run(["git", "config", "user.email", "test@quipu.dev"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.name", "Quipu Test"], cwd=repo, check=True)

        from pyquipu.engine.git_db import GitDB

        git_db = GitDB(repo)
        reader = GitObjectHistoryReader(git_db)
        writer = GitObjectHistoryWriter(git_db)
        return Engine(repo, db=git_db, reader=reader, writer=writer)

    def test_head_persistence(self, engine_with_repo):
        """测试 HEAD 指针的创建和更新"""
        engine = engine_with_repo

        # 1. 初始状态，无 HEAD
        assert not engine.head_file.exists()
        assert engine._read_head() is None

        # 2. 创建一个 Plan 节点
        # 这会自动更新 HEAD
        (engine.root_dir / "a.txt").touch()
        tree1 = engine.git_db.get_tree_hash()
        engine.create_plan_node("genesis", tree1, "plan content")

        assert engine.head_file.exists()
        assert engine._read_head() == tree1

        # 3. Align 应该保持 HEAD
        engine.align()
        assert engine._read_head() == tree1

    def test_drift_uses_head(self, engine_with_repo):
        """测试漂移捕获时使用 HEAD 作为父节点"""
        engine = engine_with_repo

        # 1. 建立 State A 并确立 HEAD
        (engine.root_dir / "f.txt").write_text("v1")
        hash_a = engine.git_db.get_tree_hash()
        engine.create_plan_node("genesis", hash_a, "setup")
        assert engine._read_head() == hash_a

        # 2. 制造漂移 (State B)
        (engine.root_dir / "f.txt").write_text("v2")
        hash_b = engine.git_db.get_tree_hash()

        # 3. 捕获漂移
        # 此时 engine 应该读取 HEAD (hash_a) 作为 input_tree
        capture_node = engine.capture_drift(hash_b)

        assert capture_node.input_tree == hash_a
        assert capture_node.output_tree == hash_b

        # 4. 验证 capture 后 HEAD 更新
        assert engine._read_head() == hash_b

    def test_checkout_updates_head(self, engine_with_repo):
        """验证 engine.checkout 正确更新 HEAD"""
        engine = engine_with_repo

        # 1. Create State A (Plan)
        (engine.root_dir / "f.txt").write_text("v1")
        hash_a = engine.git_db.get_tree_hash()
        engine.create_plan_node("genesis", hash_a, "State A")

        # 2. Create State B (Plan)
        (engine.root_dir / "f.txt").write_text("v2")
        hash_b = engine.git_db.get_tree_hash()
        engine.create_plan_node(hash_a, hash_b, "State B")

        assert engine._read_head() == hash_b

        # 3. Checkout to State A
        engine.checkout(hash_a)

        # 4. Assert Physical State
        assert (engine.root_dir / "f.txt").read_text() == "v1"

        # 5. Assert Logical State (HEAD)
        assert engine._read_head() == hash_a

    def test_capture_drift_on_detached_head(self, engine_with_repo):
        """
        A more robust regression test. Ensures capture_drift uses the HEAD
        pointer even when it's not pointing to the latest node in history.
        """
        engine = engine_with_repo
        engine.align()

        # 1. Create linear history A -> B
        (engine.root_dir / "f.txt").write_text("state A")
        hash_a = engine.git_db.get_tree_hash()
        engine.create_plan_node("genesis", hash_a, "State A")

        (engine.root_dir / "f.txt").write_text("state B")
        hash_b = engine.git_db.get_tree_hash()
        engine.create_plan_node(hash_a, hash_b, "State B")
        engine.align()  # History graph is now loaded, B is the latest node

        # 2. Checkout to the older node A. This moves the HEAD pointer.
        engine.checkout(hash_a)
        assert engine._read_head() == hash_a

        # 3. Create a new change (State C) based on State A
        (engine.root_dir / "f.txt").write_text("state C")
        hash_c = engine.git_db.get_tree_hash()

        # 4. Capture the drift. This should create Node C parented to A.
        node_c = engine.capture_drift(hash_c, message="State C")

        # 5. Assertions
        # The parent MUST be A, not B. This proves the logic reads HEAD
        # and doesn't just fall back to the "latest" node.
        assert node_c.input_tree == hash_a
        assert node_c.input_tree != hash_b
        assert node_c.output_tree == hash_c
        assert engine._read_head() == hash_c
