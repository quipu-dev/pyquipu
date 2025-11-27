## test 创建一个新的测试文件 `tests/test_sqlite_reader_integrity.py`
好的，这是一个非常好的实践。在修复一个严重错误后，为其编写一个专门的回归测试，可以确保该问题在未来的重构中不再出现。

### 用户需求

你需要一个单元测试，用于验证 `SQLiteHistoryReader` 在面对数据库中存在循环引用（一个节点将自己作为父节点）的脏数据时，是否能够正确处理，避免在内存中构建出带循环的图谱，从而防止 UI 等上层应用陷入无限循环。

### 评论

这是一个关键的健壮性测试。数据库中的数据可能会因为各种原因（例如，旧版本的 bug、手动修改、不完整的同步操作）而被破坏。数据读取层必须有能力在这种情况下保持稳定，而不是将问题传递给上层逻辑。这个测试将直接模拟最坏情况，并验证我们刚刚应用的修复。

### 目标

创建一个新的测试文件 `tests/test_sqlite_reader_integrity.py`，其中包含一个测试用例，该用例：
1.  手动在 SQLite 数据库中插入一个自引用的 `edge` 记录。
2.  调用 `SQLiteHistoryReader.load_all_nodes()`。
3.  断言该调用能够正常返回，不会挂起。
4.  断言返回的节点列表中不包含循环引用。

### 基本原理

我们将利用 `pytest` 框架和项目现有的测试夹具 (fixtures) 来创建一个干净的测试环境。测试的核心是直接对 `history.sqlite` 文件进行写操作，以模拟数据损坏的场景。然后，我们实例化 `SQLiteHistoryReader` 并调用其 `load_all_nodes` 方法。最后，我们通过一个图遍历算法 (DFS) 来检测返回的 `QuipuNode` 对象列表中是否存在 `.parent` 指针形成的循环。

### 标签

#intent/tooling #flow/ready #priority/high
#comp/engine #comp/tests #concept/history #scope/core
#ai/instruct
#task/domain/storage
#task.object/sqlite-backend
#task.action/bug-fix
#task/state/continue

---

### Script

#### Acts 1: 创建单元测试文件

我们将创建一个新的测试文件，以保持这个关键的完整性测试的独立性和清晰性。

~~~~~act
write_file
~~~~~
~~~~~path
tests/test_sqlite_reader_integrity.py
~~~~~
~~~~~python
import pytest
import time
from typing import List

from quipu.core.models import QuipuNode
from quipu.core.sqlite_storage import SQLiteHistoryReader

# We rely on a fixture from conftest.py, which is a standard pattern in this project.
# The fixture `repo_with_sqlite_db` should provide a tuple of (DatabaseManager, GitDB)
# in a clean temporary directory.


def _has_cycle(nodes: List[QuipuNode]) -> bool:
    """
    ## test: Detects cycles in a graph represented by parent pointers.

    Uses a standard Depth-First Search traversal. For each node, it traverses
    up the parent chain, keeping track of the nodes in the current path. If a
    node is encountered that is already in the current path, a cycle is detected.
    """
    # A set for all nodes visited during the entire traversal, to avoid re-checking paths
    global_visited = set()
    for node in nodes:
        if node.output_tree in global_visited:
            continue

        # A set for nodes visited in the current traversal path
        path_visited = set()
        curr = node
        while curr:
            if curr.output_tree in path_visited:
                # We've seen this node before in the *same* path, cycle detected
                return True
            if curr.output_tree in global_visited:
                # We've seen this node in a previous path that was checked and found to be safe
                break

            path_visited.add(curr.output_tree)
            curr = curr.parent

        # Mark all nodes in the now-verified-acyclic path as globally visited
        global_visited.update(path_visited)

    return False


@pytest.mark.timeout(5)  # Fails the test if it hangs for more than 5 seconds
def test_load_all_nodes_handles_self_referencing_edge(repo_with_sqlite_db):
    """
    ## test: SQLite reader should not create a graph with cycles from corrupted data.

    This test ensures that `SQLiteHistoryReader.load_all_nodes` can gracefully
    handle a corrupted `edges` table where a node incorrectly lists itself as
    its own parent. The reader should ignore this edge and not produce an
    in-memory graph with a cycle, which would otherwise cause infinite loops.
    """
    db_manager, git_db = repo_with_sqlite_db

    # --- Setup: Manually inject corrupted data into the SQLite database ---

    # 1. Create a legitimate node that we will then corrupt
    conn = db_manager._get_conn()
    commit_hash = "cycledeadbeefdeadbeefdeadbeefdeadbeef01"
    output_tree = "outputdeadbeefdeadbeefdeadbeefdeadbeef01"

    with conn:
        conn.execute(
            """
            INSERT INTO nodes (commit_hash, output_tree, node_type, timestamp, summary, meta_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (commit_hash, output_tree, "capture", time.time(), "Corrupted Self-Loop Node", "{}"),
        )

        # 2. Inject the self-referencing edge that would cause an infinite loop
        conn.execute(
            "INSERT INTO edges (child_hash, parent_hash) VALUES (?, ?)",
            (commit_hash, commit_hash),
        )

    # --- Act: Attempt to load the graph from the corrupted database ---
    reader = SQLiteHistoryReader(db_manager=db_manager, git_db=git_db)
    all_nodes = reader.load_all_nodes()

    # --- Assert ---
    # The `@pytest.mark.timeout(5)` decorator implicitly asserts that the call did not hang.

    # 1. Verify that the node itself was still loaded, despite the bad edge
    corrupted_node = next((n for n in all_nodes if n.filename.name == commit_hash), None)
    assert corrupted_node is not None, "The node with the corrupted edge should still be loaded."

    # 2. Verify that its parent pointer is None, because the self-referencing edge was ignored
    assert corrupted_node.parent is None, "The node's parent should be None after ignoring the self-loop."

    # 3. Verify the entire loaded graph structure is free of cycles
    assert not _has_cycle(all_nodes), "The final loaded graph should not contain any cycles."
~~~~~

### 下一步建议

现在，你可以运行 `pytest tests/test_sqlite_reader_integrity.py`。
*   **如果测试失败**，说明我们对 `sqlite_storage.py` 的修复还不够完善，需要进一步调试。
*   **如果测试通过**，那么我们可以非常有信心地确认，即使数据库中存在自引用脏数据，系统也不会再因此而卡死。接下来就可以继续推进 UI 性能优化的其他步骤了。
