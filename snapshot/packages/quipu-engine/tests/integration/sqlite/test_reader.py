import subprocess
import time
from pathlib import Path

import pytest
from pyquipu.engine.git_db import GitDB
from pyquipu.engine.git_object_storage import GitObjectHistoryWriter
from pyquipu.engine.hydrator import Hydrator
from pyquipu.engine.sqlite_db import DatabaseManager
from pyquipu.engine.sqlite_storage import SQLiteHistoryReader


@pytest.fixture
def sqlite_reader_setup(tmp_path: Path):
    """
    创建一个包含 Git 仓库、DB 管理器、Writer 和 Reader 的测试环境。
    此 Fixture 保持 function 作用域，为需要隔离的测试提供服务。
    """
    repo_path = tmp_path / "sql_read_repo"
    repo_path.mkdir()
    subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@quipu.dev"], cwd=repo_path, check=True)
    subprocess.run(["git", "config", "user.name", "Quipu Test"], cwd=repo_path, check=True)

    git_db = GitDB(repo_path)
    db_manager = DatabaseManager(repo_path)
    db_manager.init_schema()

    # Git-only writer to create commits
    git_writer = GitObjectHistoryWriter(git_db)
    # The reader we want to test
    reader = SQLiteHistoryReader(db_manager, git_db)
    # Hydrator to populate the DB from Git commits
    hydrator = Hydrator(git_db, db_manager)

    return reader, git_writer, hydrator, db_manager, repo_path, git_db


class TestSQLiteHistoryReader:
    def test_load_linear_history_from_db(self, sqlite_reader_setup):
        """测试从 DB 加载一个简单的线性历史。"""
        reader, git_writer, hydrator, _, repo, git_db = sqlite_reader_setup

        # 1. 在 Git 中创建两个节点
        (repo / "a.txt").touch()
        hash_a = git_db.get_tree_hash()
        git_writer.create_node("plan", "4b825dc642cb6eb9a060e54bf8d69288fbee4904", hash_a, "Content A")

        (repo / "b.txt").touch()
        hash_b = git_db.get_tree_hash()
        git_writer.create_node("plan", hash_a, hash_b, "Content B")

        # 2. 补水到数据库
        hydrator.sync("test-user")

        # 3. 使用 SQLite Reader 读取
        nodes = reader.load_all_nodes()

        # 4. 验证
        assert len(nodes) == 2
        # 按时间戳排序，确保顺序稳定
        nodes.sort(key=lambda n: n.timestamp)
        node_a, node_b = nodes[0], nodes[1]

        assert node_a.summary == "Content A"
        assert node_b.summary == "Content B"
        assert node_b.parent == node_a
        assert node_a.children == [node_b]
        assert node_b.input_tree == node_a.output_tree

    def test_read_through_cache(self, sqlite_reader_setup):
        """测试通读缓存是否能正确工作（从未缓存到已缓存）。"""
        reader, git_writer, hydrator, db_manager, repo, git_db = sqlite_reader_setup

        # 1. 在 Git 中创建节点
        (repo / "c.txt").touch()
        hash_c = git_db.get_tree_hash()
        node_c_git = git_writer.create_node(
            "plan", "4b825dc642cb6eb9a060e54bf8d69288fbee4904", hash_c, "Cache Test Content"
        )
        commit_hash_c = node_c_git.commit_hash

        # 2. 补水 (这将创建一个 plan_md_cache 为 NULL 的记录)
        hydrator.sync("test-user")

        # 3. 验证初始状态：缓存为 NULL
        conn = db_manager._get_conn()
        cursor = conn.execute("SELECT plan_md_cache FROM nodes WHERE commit_hash = ?", (commit_hash_c,))
        row = cursor.fetchone()
        assert row["plan_md_cache"] is None, "Cache should be NULL for cold data."

        # 4. 使用 Reader 加载节点并触发 get_node_content
        nodes = reader.load_all_nodes()
        node_c = [n for n in nodes if n.commit_hash == commit_hash_c][0]

        # 首次读取前，内存中的 content 应该是空的
        assert not node_c.content

        # 触发读取
        content = reader.get_node_content(node_c)
        assert content == "Cache Test Content"

        # 5. 再次验证数据库：缓存应该已被回填
        cursor_after = conn.execute("SELECT plan_md_cache FROM nodes WHERE commit_hash = ?", (commit_hash_c,))
        row_after = cursor_after.fetchone()
        assert row_after["plan_md_cache"] == "Cache Test Content", "Cache was not written back to DB."


@pytest.fixture(scope="class")
def populated_db(tmp_path_factory):
    """
    一个预填充了15个节点和一些私有数据的数据库环境。
    此 Fixture 具有 class 作用域，仅为 TestSQLiteReaderPaginated 类设置一次。
    """
    # --- Class-scoped setup logic (from sqlite_reader_setup) ---
    class_tmp_path = tmp_path_factory.mktemp("populated_db_class_scope")
    repo_path = class_tmp_path / "sql_read_repo"
    repo_path.mkdir()
    subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@quipu.dev"], cwd=repo_path, check=True)
    subprocess.run(["git", "config", "user.name", "Quipu Test"], cwd=repo_path, check=True)

    git_db = GitDB(repo_path)
    db_manager = DatabaseManager(repo_path)
    db_manager.init_schema()
    git_writer = GitObjectHistoryWriter(git_db)
    reader = SQLiteHistoryReader(db_manager, git_db)
    hydrator = Hydrator(git_db, db_manager)
    # --- End of setup logic ---

    # --- Data population logic ---
    parent_hash = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
    commit_hashes = []
    output_tree_hashes = []

    for i in range(15):
        (repo_path / f"file_{i}.txt").write_text(f"v{i}")
        time.sleep(0.01)  # Ensure unique timestamps
        output_hash = git_db.get_tree_hash()
        node = git_writer.create_node("plan", parent_hash, output_hash, f"Node {i}")
        commit_hashes.append(node.commit_hash)
        output_tree_hashes.append(node.output_tree)
        parent_hash = output_hash

    # First, hydrate the nodes table from git objects
    hydrator.sync("test-user")

    # Now, with nodes in the DB, we can add private data referencing them
    db_manager.execute_write(
        "INSERT OR IGNORE INTO private_data (node_hash, intent_md) VALUES (?, ?)",
        (commit_hashes[3], "This is a secret intent."),
    )

    return reader, db_manager, commit_hashes, output_tree_hashes


class TestSQLiteReaderPaginated:
    def test_get_node_count(self, populated_db):
        reader, _, _, _ = populated_db
        assert reader.get_node_count() == 15

    def test_load_first_page(self, populated_db):
        reader, _, _, _ = populated_db
        nodes = reader.load_nodes_paginated(limit=5, offset=0)
        assert len(nodes) == 5
        # Nodes are ordered by timestamp DESC, so newest is first
        assert nodes[0].summary == "Node 14"
        assert nodes[4].summary == "Node 10"

    def test_load_middle_page(self, populated_db):
        reader, _, _, _ = populated_db
        nodes = reader.load_nodes_paginated(limit=5, offset=5)
        assert len(nodes) == 5
        assert nodes[0].summary == "Node 9"
        assert nodes[4].summary == "Node 5"

    def test_load_last_page_partial(self, populated_db):
        reader, _, _, _ = populated_db
        nodes = reader.load_nodes_paginated(limit=5, offset=12)
        assert len(nodes) == 3  # 15 - 12 = 3
        assert nodes[0].summary == "Node 2"
        assert nodes[2].summary == "Node 0"

    def test_load_out_of_bounds(self, populated_db):
        reader, _, _, _ = populated_db
        nodes = reader.load_nodes_paginated(limit=5, offset=20)
        assert len(nodes) == 0

    def test_get_private_data_found(self, populated_db):
        reader, _, commit_hashes, _ = populated_db
        private_data = reader.get_private_data(commit_hashes[3])
        assert private_data == "This is a secret intent."

    def test_get_private_data_not_found(self, populated_db):
        reader, _, commit_hashes, _ = populated_db
        private_data = reader.get_private_data(commit_hashes[4])
        assert private_data is None

    def test_get_ancestors_with_cte(self, populated_db):
        reader, db_manager, commit_hashes, output_tree_hashes = populated_db
        # We want ancestors of the last created node (Node 14)
        # The input is the output_tree_hash of the last node.
        ancestor_output_trees = reader.get_ancestor_output_trees(output_tree_hashes[14])

        # It should contain all previous 14 output_tree hashes
        assert len(ancestor_output_trees) == 14
        assert output_tree_hashes[0] in ancestor_output_trees
        assert output_tree_hashes[13] in ancestor_output_trees
        assert output_tree_hashes[14] not in ancestor_output_trees  # Should not contain itself
