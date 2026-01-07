import subprocess

import pytest
from pyquipu.engine.git_db import GitDB
from pyquipu.engine.git_object_storage import GitObjectHistoryReader, GitObjectHistoryWriter


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
    ref_prefix = "refs/quipu/local/heads"

    # 1. Base Node A
    (repo / "f.txt").write_text("v1")
    hash_a = git_db.get_tree_hash()
    writer.create_node("plan", "4b825dc642cb6eb9a060e54bf8d69288fbee4904", hash_a, "Node A")
    heads_after_a = git_db.get_all_ref_heads(ref_prefix)
    assert len(heads_after_a) == 1

    # 2. Node B (Child of A)
    (repo / "f.txt").write_text("v2")
    hash_b = git_db.get_tree_hash()
    writer.create_node("plan", hash_a, hash_b, "Node B")
    heads_after_b = git_db.get_all_ref_heads(ref_prefix)
    assert len(heads_after_b) == 2, "创建子节点后，父节点的 head 不应被删除"

    # 3. Branching: Create C from A (Simulate Checkout A then Save C)
    (repo / "f.txt").write_text("v3")
    hash_c = git_db.get_tree_hash()
    writer.create_node("plan", hash_a, hash_c, "Node C")

    # 4. Verify Branching State
    heads_after_c = git_db.get_all_ref_heads(ref_prefix)
    assert len(heads_after_c) == 3, "创建分支节点后，所有节点都应是独立的 head"

    # 5. Verify Reader sees all and relationships are correct
    nodes = reader.load_all_nodes()
    assert len(nodes) == 3

    node_map = {n.summary: n for n in nodes}
    node_a = node_map["Node A"]
    node_b = node_map["Node B"]
    node_c = node_map["Node C"]

    assert node_b.parent.output_tree == node_a.output_tree
    assert node_c.parent.output_tree == node_a.output_tree
    assert len(node_a.children) == 2
