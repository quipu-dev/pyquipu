import pytest
import subprocess
from pathlib import Path

from quipu.cli.controller import run_quipu
from quipu.core.sqlite_db import DatabaseManager

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
        # --- Action 1: Create first node ---
        result_a = run_quipu(PLAN_A, work_dir=sqlite_workspace, yolo=True)
        assert result_a.success, f"run_quipu failed on Plan A: {result_a.message}"

        # Get its commit hash using the stable ref
        commit_hash_a = subprocess.check_output(
            ["git", "rev-parse", "refs/quipu/history"], cwd=sqlite_workspace, text=True
        ).strip()
        assert len(commit_hash_a) == 40

        # --- Action 2: Create second node, which should be a child of the first ---
        result_b = run_quipu(PLAN_B, work_dir=sqlite_workspace, yolo=True)
        assert result_b.success, f"run_quipu failed on Plan B: {result_b.message}"

        # Get the new commit hash from the updated ref
        commit_hash_b = subprocess.check_output(
            ["git", "rev-parse", "refs/quipu/history"], cwd=sqlite_workspace, text=True
        ).strip()
        assert len(commit_hash_b) == 40
        assert commit_hash_a != commit_hash_b, "History ref was not updated after second run"

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
