import subprocess
from pathlib import Path

import pytest
from pyquipu.engine.git_db import GitDB
from pyquipu.engine.git_object_storage import GitObjectHistoryWriter
from pyquipu.engine.sqlite_db import DatabaseManager
from pyquipu.engine.sqlite_storage import SQLiteHistoryWriter


@pytest.fixture
def sqlite_setup(tmp_path: Path):
    """创建一个配置为使用 SQLite 后端的 Git 环境。"""
    ws = tmp_path / "ws_sqlite"
    ws.mkdir()

    # Init Git
    subprocess.run(["git", "init"], cwd=ws, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@quipu.dev"], cwd=ws, check=True)
    subprocess.run(["git", "config", "user.name", "Quipu Test"], cwd=ws, check=True)

    git_db = GitDB(ws)
    db_manager = DatabaseManager(ws)
    db_manager.init_schema()
    
    # 组装 Writer 栈：SQLiteWriter -> GitWriter -> GitDB
    git_writer = GitObjectHistoryWriter(git_db)
    sqlite_writer = SQLiteHistoryWriter(git_writer, db_manager)

    return sqlite_writer, db_manager, git_db, ws


class TestSQLiteWriterIntegration:
    def test_dual_write_and_link(self, sqlite_setup):
        """
        验证 SQLiteHistoryWriter 是否能正确地双写到 Git 和 DB，并建立父子关系。
        不依赖 application 层的 run_quipu。
        """
        writer, db_manager, git_db, ws = sqlite_setup
        
        EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"

        # --- Action 1: Create first node (Node A) ---
        # 模拟文件变更 A
        (ws / "a.txt").write_text("File A content")
        hash_a = git_db.get_tree_hash()
        
        node_a = writer.create_node(
            node_type="plan",
            input_tree=EMPTY_TREE,
            output_tree=hash_a,
            content="Plan A Content",
            summary_override="Write: a.txt"
        )
        commit_hash_a = node_a.commit_hash

        # --- Action 2: Create second node (Node B) ---
        # 模拟文件变更 B
        (ws / "b.txt").write_text("File B content")
        hash_b = git_db.get_tree_hash()
        
        node_b = writer.create_node(
            node_type="plan",
            input_tree=hash_a,  # Parent is A
            output_tree=hash_b,
            content="Plan B Content",
            summary_override="Write: b.txt"
        )
        commit_hash_b = node_b.commit_hash

        # --- Verification ---
        
        # 1. Verify Git plumbing
        # 确保两个 commit 都存在
        assert git_db.cat_file(commit_hash_a, "commit")
        assert git_db.cat_file(commit_hash_b, "commit")
        
        # 2. Verify SQLite Data
        conn = db_manager._get_conn()

        # Check Node B metadata
        cursor_node = conn.execute("SELECT * FROM nodes WHERE commit_hash = ?", (commit_hash_b,))
        node_row = cursor_node.fetchone()
        assert node_row is not None
        assert node_row["summary"] == "Write: b.txt"
        # 验证缓存已被写入 (Hot Path)
        assert node_row["plan_md_cache"] == "Plan B Content"

        # Check Edge A -> B
        cursor_edge = conn.execute("SELECT * FROM edges WHERE child_hash = ?", (commit_hash_b,))
        edge_row = cursor_edge.fetchone()
        assert edge_row is not None, "Edge for the second node was not created."
        assert edge_row["parent_hash"] == commit_hash_a, "The edge should point to Node A."

        db_manager.close()