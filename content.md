好的，第一步已成功执行。`test_hydrator.py` 中的 `TypeError` 问题已经解决。

现在我们继续执行修复计划，处理 `tests/engine/sqlite/test_reader.py` 文件中的 `TypeError`。这个文件包含了 8 个错误和 2 个失败，全部源于同样的问题。修复此文件将完成阶段一的核心任务。

## fix: 修复 Hydrator 接口变更导致的测试失败 (阶段 1.2)

### 错误分析
与上一步类似，`tests/engine/sqlite/test_reader.py` 文件中的测试用例和 fixture (`sqlite_reader_setup` 的使用者和 `populated_db` fixture 自身) 在设置测试环境时调用了 `hydrator.sync()`，但没有提供新的 `local_user_id` 必需参数。这导致了所有依赖数据库填充的测试在启动阶段就因 `TypeError` 而崩溃。

### 用户需求
修复 `tests/engine/sqlite/test_reader.py` 文件中的所有 `TypeError`，使其测试用例能够正常执行。

### 评论
这个修复将完成对 `Hydrator` 接口变更的所有适应性修改，解决所有核心的 `TypeError` 阻塞。完成之后，测试的失败原因将转移到更深层次的架构不匹配问题上，即对 Git 引用模型的依赖。

### 目标
修改 `test_reader.py` 文件中 `TestSQLiteHistoryReader` 类下的测试方法以及 `populated_db` fixture，将所有对 `hydrator.sync()` 的调用更新为 `hydrator.sync("test-user")`。

### 基本原理
更新测试代码以匹配 `Hydrator.sync` 的新方法签名，为测试提供一个固定的用户 ID，从而解除 `TypeError` 阻塞。

### 标签
#intent/fix #flow/ready #priority/critical #comp/tests #concept/sync #scope/api #ai/instruct #task/domain/testing #task/object/test-suite #task/action/bug-fix #task/state/continue

---

### Script

#### Acts 1: 更新 `test_reader.py` 中的 `sync` 调用

对文件中的 `test_load_linear_history_from_db`、`test_read_through_cache` 方法以及 `populated_db` fixture 中的 `hydrator.sync()` 调用进行修改。

~~~~~act
patch_file
tests/engine/sqlite/test_reader.py
~~~~~
~~~~~python
class TestSQLiteHistoryReader:
    def test_load_linear_history_from_db(self, sqlite_reader_setup):
        """测试从 DB 加载一个简单的线性历史。"""
        reader, git_writer, hydrator, _, repo, git_db = sqlite_reader_setup

        # 1. 在 Git 中创建两个节点
        (repo / "a.txt").touch()
        hash_a = git_db.get_tree_hash()
        node_a_git = git_writer.create_node("plan", "4b825dc642cb6eb9a060e54bf8d69288fbee4904", hash_a, "Content A")

        (repo / "b.txt").touch()
        hash_b = git_db.get_tree_hash()
        node_b_git = git_writer.create_node("plan", hash_a, hash_b, "Content B")

        # 2. 补水到数据库
        hydrator.sync()

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
        hydrator.sync()

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
    hydrator.sync()

    # Now, with nodes in the DB, we can add private data referencing them
    db_manager.execute_write(
        "INSERT OR IGNORE INTO private_data (node_hash, intent_md) VALUES (?, ?)",
        (commit_hashes[3], "This is a secret intent."),
    )

    return reader, db_manager, commit_hashes, output_tree_hashes
~~~~~
~~~~~python
class TestSQLiteHistoryReader:
    def test_load_linear_history_from_db(self, sqlite_reader_setup):
        """测试从 DB 加载一个简单的线性历史。"""
        reader, git_writer, hydrator, _, repo, git_db = sqlite_reader_setup

        # 1. 在 Git 中创建两个节点
        (repo / "a.txt").touch()
        hash_a = git_db.get_tree_hash()
        node_a_git = git_writer.create_node("plan", "4b825dc642cb6eb9a060e54bf8d69288fbee4904", hash_a, "Content A")

        (repo / "b.txt").touch()
        hash_b = git_db.get_tree_hash()
        node_b_git = git_writer.create_node("plan", hash_a, hash_b, "Content B")

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
~~~~~

### 下一步建议
请执行此计划。这应该会解决所有 `TypeError` 问题。完成后，请重新运行测试套件，我们将根据新的测试结果进入修复计划的第二阶段，处理因 Git 引用架构变更而导致的失败。
