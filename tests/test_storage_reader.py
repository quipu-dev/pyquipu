import json
import pytest
import subprocess
import time
from pathlib import Path
from typing import List

from quipu.core.git_db import GitDB
from quipu.core.git_object_storage import GitObjectHistoryReader, GitObjectHistoryWriter
from quipu.core.models import QuipuNode

@pytest.fixture
def reader_setup(tmp_path):
    repo_path = tmp_path / "read_repo"
    repo_path.mkdir()
    subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "reader@quipu.dev"], cwd=repo_path, check=True)
    subprocess.run(["git", "config", "user.name", "Quipu Reader"], cwd=repo_path, check=True)
    
    git_db = GitDB(repo_path)
    writer = GitObjectHistoryWriter(git_db)
    reader = GitObjectHistoryReader(git_db)
    
    return reader, writer, git_db, repo_path

class TestGitObjectHistoryReader:
    
    def test_load_empty_history(self, reader_setup):
        """测试：没有 Quipu 历史时的行为"""
        reader, _, _, _ = reader_setup
        nodes = reader.load_all_nodes()
        assert nodes == []

    def test_load_linear_history(self, reader_setup):
        """测试：标准的线性历史 A -> B -> C"""
        reader, writer, git_db, repo = reader_setup
        
        h0 = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
        
        (repo/"a").touch()
        h1 = git_db.get_tree_hash()
        writer.create_node("plan", h0, h1, "Plan A", start_time=1000)
        time.sleep(0.01)
        
        (repo/"b").touch()
        h2 = git_db.get_tree_hash()
        writer.create_node("plan", h1, h2, "Plan B", start_time=2000)
        time.sleep(0.01)
        
        (repo/"c").touch()
        h3 = git_db.get_tree_hash()
        writer.create_node("capture", h2, h3, "Capture C", start_time=3000)
        
        nodes = reader.load_all_nodes()
        
        assert len(nodes) == 3
        
        roots = [n for n in nodes if n.input_tree == h0]
        assert len(roots) == 1
        node_a = roots[0]
        assert node_a.content.strip() == "Plan A"
        assert node_a.timestamp.timestamp() == 1000.0
        
        assert len(node_a.children) == 1
        node_b = node_a.children[0]
        assert node_b.content.strip() == "Plan B"
        assert node_b.input_tree == h1
        assert node_b.parent == node_a
        
        assert len(node_b.children) == 1
        node_c = node_b.children[0]
        assert node_c.content.strip() == "Capture C"
        assert node_c.node_type == "capture"

    def test_load_forked_history(self, reader_setup):
        """测试：正确加载分叉的历史 A -> B and A -> C"""
        reader, writer, git_db, repo = reader_setup
        
        h0 = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
        (repo/"base").touch()
        hash_a = git_db.get_tree_hash()
        writer.create_node("plan", h0, hash_a, "Plan A", start_time=1000)
        commit_a = git_db._run(["rev-parse", "refs/quipu/history"]).stdout.strip()
        time.sleep(0.01)

        (repo/"file_b").touch()
        hash_b = git_db.get_tree_hash()
        writer.create_node("plan", hash_a, hash_b, "Plan B", start_time=2000)
        # Rename the ref to create a fork head
        git_db._run(["update-ref", "refs/quipu/branch_b", "refs/quipu/history"])
        time.sleep(0.01)

        # Reset main ref back to commit_a to create another branch
        git_db.update_ref("refs/quipu/history", commit_a)
        
        (repo/"file_c").touch()
        (repo/"file_b").unlink()
        hash_c = git_db.get_tree_hash()
        writer.create_node("plan", hash_a, hash_c, "Plan C", start_time=3000)

        nodes = reader.load_all_nodes()
        
        assert len(nodes) == 3
        
        nodes_by_content = {n.content.strip(): n for n in nodes}
        node_a = nodes_by_content["Plan A"]
        node_b = nodes_by_content["Plan B"]
        node_c = nodes_by_content["Plan C"]
        
        assert node_a.parent is None
        assert node_b.parent == node_a
        assert node_c.parent == node_a
        
        assert len(node_a.children) == 2
        child_contents = sorted([child.content.strip() for child in node_a.children])
        assert child_contents == ["Plan B", "Plan C"]

    def test_corrupted_node_missing_metadata(self, reader_setup):
        """测试：Commit 存在但缺少 metadata.json"""
        reader, _, git_db, repo = reader_setup
        
        content_hash = git_db.hash_object(b"content")
        tree_hash = git_db.mktree(f"100444 blob {content_hash}\tcontent.md")
        commit_msg = f"Bad Node\n\nX-Quipu-Output-Tree: {'a'*40}"
        commit_hash = git_db.commit_tree(tree_hash, None, commit_msg)
        git_db.update_ref("refs/quipu/history", commit_hash)
        
        nodes = reader.load_all_nodes()
        assert len(nodes) == 0

    def test_corrupted_node_missing_trailer(self, reader_setup):
        """测试：Commit 存在但缺少 Output Tree Trailer"""
        reader, _, git_db, repo = reader_setup
        
        meta_hash = git_db.hash_object(json.dumps({"type": "plan"}).encode())
        content_hash = git_db.hash_object(b"c")
        tree_hash = git_db.mktree(
            f"100444 blob {meta_hash}\tmetadata.json\n"
            f"100444 blob {content_hash}\tcontent.md"
        )
        
        commit_hash = git_db.commit_tree(tree_hash, None, "Just a summary")
        git_db.update_ref("refs/quipu/history", commit_hash)
        
        nodes = reader.load_all_nodes()
        assert len(nodes) == 0

    def test_parent_linking_with_gap(self, reader_setup):
        """测试：如果父 Commit 是损坏的节点，子节点应断开链接并视为新的根"""
        reader, writer, git_db, _ = reader_setup
        
        h0 = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
        hash_a = "a" * 40
        writer.create_node("plan", h0, hash_a, "A", start_time=1000)
        
        commit_a = git_db._run(["rev-parse", "refs/quipu/history"]).stdout.strip()
        
        empty_tree = git_db.mktree("")
        commit_b_bad = git_db.commit_tree(empty_tree, [commit_a], "Bad B")
        git_db.update_ref("refs/quipu/history", commit_b_bad)
        
        hash_c = "c" * 40
        writer.create_node("plan", "b_implied", hash_c, "C", start_time=3000)
        
        nodes = reader.load_all_nodes()
        
        assert len(nodes) == 2
        valid_nodes = {n.content.strip(): n for n in nodes}
        assert "A" in valid_nodes
        assert "C" in valid_nodes
        
        node_c = valid_nodes["C"]
        assert node_c.parent is None
        assert node_c.input_tree == h0