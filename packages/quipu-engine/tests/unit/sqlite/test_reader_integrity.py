import subprocess
import time
from typing import List

import pytest
from pyquipu.engine.git_db import GitDB
from pyquipu.engine.sqlite_db import DatabaseManager
from pyquipu.engine.sqlite_storage import SQLiteHistoryReader
from pyquipu.interfaces.models import QuipuNode


@pytest.fixture
def repo_with_sqlite_db(tmp_path):
    # 1. Initialize Git repo
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    # Configure user for commits (needed if we were making commits, good practice anyway)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=tmp_path, check=True)

    # 2. Initialize GitDB
    git_db = GitDB(tmp_path)

    # 3. Initialize DatabaseManager
    db_manager = DatabaseManager(tmp_path)
    db_manager.init_schema()

    yield db_manager, git_db

    # Teardown
    db_manager.close()


def _has_cycle(nodes: List[QuipuNode]) -> bool:
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
    db_manager, git_db = repo_with_sqlite_db

    # --- Setup: Manually inject corrupted data into the SQLite database ---

    # 1. Create a legitimate node that we will then corrupt
    conn = db_manager._get_conn()
    commit_hash = "cycledeadbeefdeadbeefdeadbeefdeadbeef01"
    output_tree = "outputdeadbeefdeadbeefdeadbeefdeadbeef01"

    with conn:
        conn.execute(
            """
            INSERT INTO nodes (
                commit_hash, output_tree, node_type, timestamp, summary,
                generator_id, meta_json, plan_md_cache
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (commit_hash, output_tree, "capture", time.time(), "Corrupted Self-Loop Node", "manual", "{}", None),
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
