import pytest
import subprocess
from quipu.core.git_db import GitDB
from quipu.core.git_object_storage import GitObjectHistoryWriter, GitObjectHistoryReader


@pytest.fixture
def branching_env(tmp_path):
    repo_path = tmp_path / "branch_repo"
    repo_path.mkdir()
    subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@quipu.dev"], cwd=repo_path, check=True)
    subprocess.run(["git", "config", "user.name", "Quipu Test"], cwd=repo_path, check=True)

    git_db = GitDB(repo_path)
    writer = GitObjectHistoryWriter(git_db)
    reader = GitObjectHistoryReader(git_db)
    return repo_path, git_db, writer, reader


def test_branching_creation(branching_env):
    """
    测试分支创建场景：
    1. A -> B
    2. Checkout A -> C
    结果应为:
      A -> B
       \\-> C
    Reader 应能读取到所有节点。
    """
    repo, git_db, writer, reader = branching_env

    # 1. Base Node A
    (repo / "f.txt").write_text("v1")
    hash_a = git_db.get_tree_hash()
    writer.create_node("plan", "4b825dc642cb6eb9a060e54bf8d69288fbee4904", hash_a, "Node A")

    # 2. Node B (Child of A)
    (repo / "f.txt").write_text("v2")
    hash_b = git_db.get_tree_hash()
    writer.create_node("plan", hash_a, hash_b, "Node B")

    # Verify linear state
    heads = git_db.get_all_ref_heads("refs/quipu/heads")
    assert len(heads) == 1  # Only B should be head

    # 3. Branching: Create C from A (Simulate Checkout A then Save C)
    # Physical checkout isn't strictly needed for writer test, just correct input hash
    (repo / "f.txt").write_text("v3")
    hash_c = git_db.get_tree_hash()

    # The writer should detect A is the parent based on input_tree=hash_a
    writer.create_node("plan", hash_a, hash_c, "Node C")

    # 4. Verify Branching State
    heads = git_db.get_all_ref_heads("refs/quipu/heads")
    assert len(heads) == 2  # B and C should be heads

    # 5. Verify Reader sees all
    nodes = reader.load_all_nodes()
    assert len(nodes) == 3

    node_map = {n.summary: n for n in nodes}
    node_a = node_map["Node A"]
    node_b = node_map["Node B"]
    node_c = node_map["Node C"]

    assert node_b.parent == node_a
    assert node_c.parent == node_a
    assert len(node_a.children) == 2
