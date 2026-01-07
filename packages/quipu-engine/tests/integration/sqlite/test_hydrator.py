import subprocess
from pathlib import Path

import pytest
from pyquipu.engine.git_db import GitDB
from pyquipu.engine.git_object_storage import GitObjectHistoryWriter
from pyquipu.engine.hydrator import Hydrator
from pyquipu.engine.sqlite_db import DatabaseManager


@pytest.fixture
def hydrator_setup(tmp_path: Path):
    repo_path = tmp_path / "hydro_repo"
    repo_path.mkdir()
    subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@quipu.dev"], cwd=repo_path, check=True)
    subprocess.run(["git", "config", "user.name", "Quipu Test"], cwd=repo_path, check=True)

    git_db = GitDB(repo_path)
    db_manager = DatabaseManager(repo_path)
    db_manager.init_schema()

    writer = GitObjectHistoryWriter(git_db)
    hydrator = Hydrator(git_db, db_manager)

    return hydrator, writer, git_db, db_manager, repo_path


class TestHydration:
    def test_full_hydration_from_scratch(self, hydrator_setup):
        hydrator, writer, git_db, db_manager, repo = hydrator_setup

        # 1. 在 Git 中创建两个节点
        (repo / "a.txt").touch()
        hash_a = git_db.get_tree_hash()
        writer.create_node("plan", "genesis", hash_a, "Node A")

        (repo / "b.txt").touch()
        hash_b = git_db.get_tree_hash()
        writer.create_node("plan", hash_a, hash_b, "Node B")

        # 2. 初始状态下 DB 为空
        assert len(db_manager.get_all_node_hashes()) == 0

        # 3. 执行补水
        hydrator.sync("test-user")

        # 4. 验证
        db_hashes = db_manager.get_all_node_hashes()
        assert len(db_hashes) == 2

        conn = db_manager._get_conn()
        # 验证 Node B 的内容
        node_b_row = conn.execute("SELECT * FROM nodes WHERE summary = ?", ("Node B",)).fetchone()
        assert node_b_row is not None
        assert node_b_row["plan_md_cache"] is None  # 必须是冷数据

        # 验证边关系
        edge_row = conn.execute("SELECT * FROM edges WHERE child_hash = ?", (node_b_row["commit_hash"],)).fetchone()
        assert edge_row is not None

    def test_incremental_hydration(self, hydrator_setup):
        hydrator, writer, git_db, db_manager, repo = hydrator_setup

        # 1. 创建节点 A 并立即补水
        (repo / "a.txt").touch()
        hash_a = git_db.get_tree_hash()
        writer.create_node("plan", "genesis", hash_a, "Node A")
        hydrator.sync("test-user")
        assert len(db_manager.get_all_node_hashes()) == 1

        # 2. 创建节点 B
        (repo / "b.txt").touch()
        hash_b = git_db.get_tree_hash()
        writer.create_node("plan", hash_a, hash_b, "Node B")

        # 3. 再次补水
        hydrator.sync("test-user")

        # 4. 验证，总数应为 2
        assert len(db_manager.get_all_node_hashes()) == 2

        conn = db_manager._get_conn()
        node_b_row = conn.execute("SELECT * FROM nodes WHERE summary = ?", ("Node B",)).fetchone()
        assert node_b_row is not None

    def test_hydration_idempotency(self, hydrator_setup):
        hydrator, writer, git_db, db_manager, repo = hydrator_setup

        (repo / "a.txt").touch()
        hash_a = git_db.get_tree_hash()
        writer.create_node("plan", "genesis", hash_a, "Node A")

        # 运行两次
        hydrator.sync("test-user")
        hydrator.sync("test-user")

        assert len(db_manager.get_all_node_hashes()) == 1
