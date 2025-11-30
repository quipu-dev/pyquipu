import pytest
import subprocess
from pathlib import Path

from pyquipu.cli.controller import run_quipu
from pyquipu.engine.sqlite_db import DatabaseManager

PLAN_A = """
```act
write_file a.txt
```
```content
File A content
```
"""

PLAN_B = """
```act
write_file b.txt
```
```content
File B content
```
"""


@pytest.fixture
def sqlite_workspace(tmp_path: Path) -> Path:
    """创建一个配置为使用 SQLite 后端的 Git 工作区。"""
    ws = tmp_path / "ws_sqlite"
    ws.mkdir()

    # Init Git
    subprocess.run(["git", "init"], cwd=ws, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@quipu.dev"], cwd=ws, check=True)
    subprocess.run(["git", "config", "user.name", "Quipu Test"], cwd=ws, check=True)

    # Init Quipu config for SQLite
    quipu_dir = ws / ".quipu"
    quipu_dir.mkdir()
    (quipu_dir / "config.yml").write_text("storage:\n  type: sqlite\n")

    return ws


class TestSQLiteWriterIntegration:
    def test_dual_write_on_run_and_link(self, sqlite_workspace):
        """
        验证 `quipu run` 在 SQLite 模式下是否能正确地双写到 Git 和 DB，并建立父子关系。
        """
        # Command to get all local head commit hashes
        get_all_heads_cmd = ["git", "for-each-ref", "--format=%(objectname)", "refs/quipu/local/heads/"]

        # --- Action 1: Create first node ---
        result_a = run_quipu(PLAN_A, work_dir=sqlite_workspace, yolo=True)
        assert result_a.success, f"run_quipu failed on Plan A: {result_a.message}"

        # Get the state after the first run
        heads_after_a = set(
            subprocess.check_output(get_all_heads_cmd, cwd=sqlite_workspace, text=True).strip().splitlines()
        )
        assert len(heads_after_a) == 1
        commit_hash_a = heads_after_a.pop()

        # --- Action 2: Create second node, which should be a child of the first ---
        result_b = run_quipu(PLAN_B, work_dir=sqlite_workspace, yolo=True)
        assert result_b.success, f"run_quipu failed on Plan B: {result_b.message}"

        # Get the state after the second run and find the new commit
        heads_before_b = {commit_hash_a}  # The set of heads before this action
        heads_after_b = set(
            subprocess.check_output(get_all_heads_cmd, cwd=sqlite_workspace, text=True).strip().splitlines()
        )

        new_heads = heads_after_b - heads_before_b
        assert len(new_heads) == 1, "Expected exactly one new head to be created"
        commit_hash_b = new_heads.pop()
        assert commit_hash_a != commit_hash_b

        # --- Verification ---
        db_path = sqlite_workspace / ".quipu" / "history.sqlite"
        assert db_path.exists()
        db = DatabaseManager(sqlite_workspace)
        conn = db._get_conn()

        # 1. Verify node B exists
        cursor_node = conn.execute("SELECT * FROM nodes WHERE commit_hash = ?", (commit_hash_b,))
        node_row = cursor_node.fetchone()
        assert node_row is not None
        assert node_row["summary"] == "Write: b.txt"
        assert node_row["plan_md_cache"] is not None  # Should be hot-cached

        # 2. Verify the edge exists and points to node A
        cursor_edge = conn.execute("SELECT * FROM edges WHERE child_hash = ?", (commit_hash_b,))
        edge_row = cursor_edge.fetchone()
        assert edge_row is not None, "Edge for the second node was not created in the database."
        assert edge_row["parent_hash"] == commit_hash_a, "The parent hash in the edge is incorrect."

        db.close()
