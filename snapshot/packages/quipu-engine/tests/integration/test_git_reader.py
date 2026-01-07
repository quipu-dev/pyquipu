import json
import subprocess
import time

import pytest
from pyquipu.engine.git_db import GitDB
from pyquipu.engine.git_object_storage import GitObjectHistoryReader, GitObjectHistoryWriter


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

        (repo / "a").touch()
        h1 = git_db.get_tree_hash()
        node_a = writer.create_node("plan", h0, h1, "Plan A", start_time=1000)
        time.sleep(0.01)

        (repo / "b").touch()
        h2 = git_db.get_tree_hash()
        node_b = writer.create_node("plan", h1, h2, "Plan B", start_time=2000)
        time.sleep(0.01)

        (repo / "c").touch()
        h3 = git_db.get_tree_hash()
        writer.create_node("capture", h2, h3, "Capture C", start_time=3000)

        nodes = reader.load_all_nodes()

        assert len(nodes) == 3

        roots = [n for n in nodes if n.parent is None]
        assert len(roots) == 1
        found_node_a = roots[0]
        assert found_node_a.commit_hash == node_a.commit_hash

        # Lazy load verification
        assert found_node_a.content == ""
        assert reader.get_node_content(found_node_a).strip() == "Plan A"
        assert found_node_a.timestamp.timestamp() == 1000.0

        assert len(found_node_a.children) == 1
        found_node_b = found_node_a.children[0]
        assert found_node_b.commit_hash == node_b.commit_hash
        assert reader.get_node_content(found_node_b).strip() == "Plan B"
        assert found_node_b.input_tree == h1
        assert found_node_b.parent == found_node_a

        assert len(found_node_b.children) == 1
        node_c = found_node_b.children[0]
        assert reader.get_node_content(node_c).strip() == "Capture C"
        assert node_c.node_type == "capture"

    def test_load_forked_history(self, reader_setup):
        """测试：正确加载分叉的历史 A -> B and A -> C"""
        reader, writer, git_db, repo = reader_setup

        h0 = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
        (repo / "base").touch()
        hash_a = git_db.get_tree_hash()
        writer.create_node("plan", h0, hash_a, "Plan A", start_time=1000)
        time.sleep(0.01)

        # Create branch B from A
        (repo / "file_b").touch()
        hash_b = git_db.get_tree_hash()
        writer.create_node("plan", hash_a, hash_b, "Plan B", start_time=2000)
        time.sleep(0.01)

        # Create branch C from A
        (repo / "file_c").touch()
        (repo / "file_b").unlink()  # Modify workspace to create a different tree hash
        hash_c = git_db.get_tree_hash()
        writer.create_node("plan", hash_a, hash_c, "Plan C", start_time=3000)

        nodes = reader.load_all_nodes()

        assert len(nodes) == 3

        # Explicitly load content for mapping
        nodes_by_content = {reader.get_node_content(n).strip(): n for n in nodes}

        found_node_a = nodes_by_content["Plan A"]
        found_node_b = nodes_by_content["Plan B"]
        found_node_c = nodes_by_content["Plan C"]

        assert found_node_a.parent is None
        assert found_node_b.parent == found_node_a
        assert found_node_c.parent == found_node_a

        assert len(found_node_a.children) == 2
        child_contents = sorted([child.content.strip() for child in found_node_a.children])
        assert child_contents == ["Plan B", "Plan C"]

    def test_corrupted_node_missing_metadata(self, reader_setup):
        """测试：Commit 存在但缺少 metadata.json"""
        reader, _, git_db, repo = reader_setup

        content_hash = git_db.hash_object(b"content")
        tree_hash = git_db.mktree(f"100444 blob {content_hash}\tcontent.md")
        commit_msg = f"Bad Node\n\nX-Quipu-Output-Tree: {'a' * 40}"
        commit_hash = git_db.commit_tree(tree_hash, None, commit_msg)
        # Manually create a head ref to make it discoverable
        git_db.update_ref(f"refs/quipu/local/heads/{commit_hash}", commit_hash)

        nodes = reader.load_all_nodes()
        assert len(nodes) == 0

    def test_corrupted_node_missing_trailer(self, reader_setup):
        """测试：Commit 存在但缺少 Output Tree Trailer"""
        reader, _, git_db, repo = reader_setup

        meta_hash = git_db.hash_object(json.dumps({"type": "plan"}).encode())
        content_hash = git_db.hash_object(b"c")
        tree_hash = git_db.mktree(f"100444 blob {meta_hash}\tmetadata.json\n100444 blob {content_hash}\tcontent.md")

        commit_hash = git_db.commit_tree(tree_hash, None, "Just a summary")
        # Manually create a head ref to make it discoverable
        git_db.update_ref(f"refs/quipu/local/heads/{commit_hash}", commit_hash)

        nodes = reader.load_all_nodes()
        assert len(nodes) == 0

    def test_parent_linking_with_gap(self, reader_setup):
        """测试：如果父 Commit 是损坏的节点，子节点应断开链接并视为新的根"""
        reader, writer, git_db, _ = reader_setup

        h0 = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"

        # Helper to create a valid tree object in the ODB
        def make_valid_tree(content: bytes) -> str:
            blob = git_db.hash_object(content)
            return git_db.mktree(f"100644 blob {blob}\tfile")

        tree_a = make_valid_tree(b"state_a")
        tree_c = make_valid_tree(b"state_c")

        # 1. Create a valid node A
        node_a = writer.create_node("plan", h0, tree_a, "A", start_time=1000)

        # 2. Manually create a corrupted commit B, parented to A
        empty_tree = git_db.mktree("")
        commit_b_bad = git_db.commit_tree(empty_tree, [node_a.commit_hash], "Bad B")
        # Make the bad commit discoverable by creating a head for it
        git_db.update_ref(f"refs/quipu/local/heads/{commit_b_bad}", commit_b_bad)

        # 3. Create a valid node C, whose logical parent (by input_tree) is A,
        # but whose topological parent in Git is the bad commit B.
        # The writer will link C to A based on input_tree. The reader must correctly
        # parse this graph despite the corrupted intermediary.
        writer.create_node("plan", node_a.output_tree, tree_c, "C", start_time=3000)

        nodes = reader.load_all_nodes()

        # The reader should find 2 valid nodes (A and C) and skip the bad one (B).
        assert len(nodes) == 2
        valid_nodes = {reader.get_node_content(n).strip(): n for n in nodes}
        assert "A" in valid_nodes
        assert "C" in valid_nodes

        found_node_a = valid_nodes["A"]
        found_node_c = valid_nodes["C"]

        # C should be correctly parented to A, effectively ignoring the bad commit.
        assert found_node_c.parent == found_node_a
        assert found_node_a.children == [found_node_c]
