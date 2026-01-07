import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from pyquipu.engine.git_db import GitDB


@pytest.fixture
def git_repo(tmp_path):
    """创建一个初始化的 Git 仓库"""
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init"], cwd=root, check=True)

    # 配置 User，防止 Commit 报错
    subprocess.run(["git", "config", "user.email", "test@quipu.dev"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Quipu Test"], cwd=root, check=True)

    return root


@pytest.fixture
def db(git_repo):
    """返回绑定到该仓库的 GitDB 实例"""
    return GitDB(git_repo)


class TestGitDBPlumbing:
    def test_get_tree_hash_stability(self, git_repo, db):
        """测试：内容不变，Hash 不变 (State Truth)"""
        f = git_repo / "test.txt"
        f.write_text("hello", encoding="utf-8")

        hash1 = db.get_tree_hash()
        hash2 = db.get_tree_hash()

        assert len(hash1) == 40
        assert hash1 == hash2

    def test_get_tree_hash_sensitivity(self, git_repo, db):
        """测试：内容变化，Hash 必变"""
        f = git_repo / "test.txt"
        f.write_text("v1", encoding="utf-8")
        hash1 = db.get_tree_hash()

        f.write_text("v2", encoding="utf-8")
        hash2 = db.get_tree_hash()

        assert hash1 != hash2

    def test_shadow_index_isolation(self, git_repo, db):
        """
        测试关键特性：零污染 (Zero Pollution)
        Quipu 计算 Hash 的过程绝对不能把文件加入到用户的暂存区。
        """
        f = git_repo / "wip.txt"
        f.write_text("working in progress", encoding="utf-8")

        # 1. 确保用户暂存区是空的
        status_before = subprocess.check_output(["git", "status", "--porcelain"], cwd=git_repo).decode()
        assert "??" in status_before  # Untracked
        assert "A" not in status_before  # Not staged

        # 2. Quipu 执行计算
        _ = db.get_tree_hash()

        # 3. 验证用户暂存区依然是空的
        status_after = subprocess.check_output(["git", "status", "--porcelain"], cwd=git_repo).decode()
        assert status_after == status_before

        # 验证 Shadow Index 文件已被清理
        assert not (git_repo / ".quipu" / "tmp_index").exists()

    def test_exclude_quipu_dir(self, git_repo, db):
        """测试：.quipu 目录内的变化不应改变 Tree Hash"""
        (git_repo / "main.py").touch()
        hash_base = db.get_tree_hash()

        # 在 .quipu 目录下乱写东西
        quipu_dir = git_repo / ".quipu"
        quipu_dir.mkdir(exist_ok=True)
        (quipu_dir / "history.md").write_text("some history", encoding="utf-8")

        hash_new = db.get_tree_hash()

        assert hash_base == hash_new

    def test_anchor_commit_persistence(self, git_repo, db):
        """测试：创建影子锚点"""
        (git_repo / "f.txt").write_text("content")
        tree_hash = db.get_tree_hash()

        # 创建锚点
        commit_hash = db.commit_tree(tree_hash, parent_hashes=None, message="Quipu Shadow Commit")

        # 更新引用
        ref_name = "refs/quipu/history"
        db.update_ref(ref_name, commit_hash)

        # 验证 Git 能够读取该引用
        read_back = subprocess.check_output(["git", "rev-parse", ref_name], cwd=git_repo).decode().strip()

        assert read_back == commit_hash

        # 验证该 Commit 确实指向正确的 Tree
        commit_tree = (
            subprocess.check_output(["git", "show", "--format=%T", "-s", commit_hash], cwd=git_repo).decode().strip()
        )

        assert commit_tree == tree_hash

    def test_hash_object(self, db):
        """测试 hash_object 能否正确创建 blob 并返回 hash。"""
        content = b"hello quipu blob"
        expected_hash = "9cb67783b5a82481c643efb6897e5412d4c221ea"

        blob_hash = db.hash_object(content, object_type="blob")
        assert blob_hash == expected_hash

    def test_mktree_and_commit_tree(self, db):
        """测试 mktree 和 commit_tree 的协同工作。"""
        # 1. Create a blob
        file_content = b"content of file.txt"
        blob_hash = db.hash_object(file_content)

        # 2. Create a tree
        tree_descriptor = f"100644 blob {blob_hash}\tfile.txt"
        tree_hash = db.mktree(tree_descriptor)

        # Verify tree content using git command
        ls_tree_output = subprocess.check_output(["git", "ls-tree", tree_hash], cwd=db.root).decode()
        assert blob_hash in ls_tree_output
        assert "file.txt" in ls_tree_output

        # 3. Create a commit
        commit_message = "feat: Initial commit via commit_tree\n\nThis is the body."
        commit_hash = db.commit_tree(tree_hash, parent_hashes=None, message=commit_message)

        # Verify commit content
        commit_content = subprocess.check_output(["git", "cat-file", "-p", commit_hash], cwd=db.root).decode()
        assert f"tree {tree_hash}" in commit_content
        assert "feat: Initial commit" in commit_content
        assert "This is the body" in commit_content

    def test_is_ancestor(self, git_repo, db, caplog):
        """测试血统检测，并验证无错误日志"""
        import logging

        caplog.set_level(logging.INFO)

        # Create C1
        (git_repo / "a").touch()
        subprocess.run(["git", "add", "."], cwd=git_repo, check=True)
        subprocess.run(["git", "commit", "-m", "C1"], cwd=git_repo, check=True)
        c1 = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=git_repo).decode().strip()

        # Create C2
        (git_repo / "b").touch()
        subprocess.run(["git", "add", "."], cwd=git_repo, check=True)
        subprocess.run(["git", "commit", "-m", "C2"], cwd=git_repo, check=True)
        c2 = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=git_repo).decode().strip()

        # 验证逻辑
        assert db.is_ancestor(c1, c2) is True
        assert db.is_ancestor(c2, c1) is False

        # 验证日志清洁度
        assert "Git plumbing error" not in caplog.text

    def test_checkout_tree(self, git_repo: Path, db: GitDB):
        """Test the low-level hard reset functionality of checkout_tree."""
        # 1. Create State A
        (git_repo / "file1.txt").write_text("version 1", "utf-8")
        (git_repo / "common.txt").write_text("shared", "utf-8")
        hash_a = db.get_tree_hash()

        # Create a file inside .quipu to ensure it's not deleted
        quipu_dir = git_repo / ".quipu"
        quipu_dir.mkdir(exist_ok=True)
        (quipu_dir / "preserve.me").touch()

        # 2. Create State B
        (git_repo / "file1.txt").write_text("version 2", "utf-8")
        (git_repo / "file2.txt").write_text("new file", "utf-8")

        # 3. Checkout to State A
        db.checkout_tree(hash_a)

        # 4. Assertions
        assert (git_repo / "file1.txt").read_text("utf-8") == "version 1"
        assert (git_repo / "common.txt").exists()
        assert not (git_repo / "file2.txt").exists(), "file2.txt should have been cleaned"
        assert (quipu_dir / "preserve.me").exists(), ".quipu directory should be preserved"

    def test_checkout_tree_messaging(self, git_repo: Path, db: GitDB, monkeypatch):
        """Verify checkout_tree emits correct messages via the bus."""
        mock_bus = MagicMock()
        monkeypatch.setattr("pyquipu.engine.git_db.bus", mock_bus)

        (git_repo / "file1.txt").write_text("v1")
        hash_a = db.get_tree_hash()

        db.checkout_tree(hash_a)

        mock_bus.info.assert_called_once_with("engine.git.info.checkoutStarted", short_hash=hash_a[:7])
        mock_bus.success.assert_called_once_with("engine.git.success.checkoutComplete")

    def test_get_diff_name_status(self, git_repo: Path, db: GitDB):
        """Test the file status diffing functionality."""
        # State A
        (git_repo / "modified.txt").write_text("v1", "utf-8")
        (git_repo / "deleted.txt").write_text("delete me", "utf-8")
        hash_a = db.get_tree_hash()

        # State B
        (git_repo / "modified.txt").write_text("v2", "utf-8")
        (git_repo / "deleted.txt").unlink()
        (git_repo / "added.txt").write_text("new file", "utf-8")
        hash_b = db.get_tree_hash()

        changes = db.get_diff_name_status(hash_a, hash_b)

        # Convert to a dictionary for easier assertion
        changes_dict = {path: status for status, path in changes}

        assert "M" == changes_dict.get("modified.txt")
        assert "A" == changes_dict.get("added.txt")
        assert "D" == changes_dict.get("deleted.txt")
        assert len(changes) == 3

    def test_log_ref_basic(self, git_repo, db):
        """测试 log_ref 能正确解析 Git 日志格式"""
        # Create 3 commits
        for i in range(3):
            (git_repo / f"f{i}").touch()
            subprocess.run(["git", "add", "."], cwd=git_repo, check=True)
            subprocess.run(["git", "commit", "-m", f"commit {i}\n\nBody {i}"], cwd=git_repo, check=True)

        logs = db.log_ref("HEAD")
        assert len(logs) == 3
        assert logs[0]["body"].strip() == "commit 2\n\nBody 2"
        assert logs[2]["body"].strip() == "commit 0\n\nBody 0"
        assert "hash" in logs[0]
        assert "tree" in logs[0]
        assert "timestamp" in logs[0]

    def test_log_ref_non_existent(self, db):
        """测试读取不存在的引用返回空列表而不是报错"""
        logs = db.log_ref("refs/heads/non-existent")
        assert logs == []

    def test_cat_file_types(self, git_repo, db):
        """测试 cat_file 处理不同类型对象的能力"""
        # 1. Prepare data: create file, add, and commit
        (git_repo / "test_file").write_text("file content", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=git_repo, check=True)
        subprocess.run(["git", "commit", "-m", "test commit"], cwd=git_repo, check=True)

        # 2. Get hashes using git command for verification source
        head_hash = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=git_repo).decode().strip()
        tree_hash = subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], cwd=git_repo).decode().strip()
        # Get blob hash via ls-tree
        ls_out = subprocess.check_output(["git", "ls-tree", "HEAD", "test_file"], cwd=git_repo).decode()
        blob_hash = ls_out.split()[2]

        # 3. Verify Blob reading
        read_blob = db.cat_file(blob_hash, "blob")
        assert read_blob == b"file content"

        # 4. Verify Commit reading
        read_commit = db.cat_file(head_hash, "commit")
        assert b"tree " in read_commit
        assert b"test commit" in read_commit

        # 5. Verify Tree reading
        read_tree = db.cat_file(tree_hash, "tree")
        # The raw tree object contains the binary hash, not the hex representation.
        assert b"test_file" in read_tree
        assert bytes.fromhex(blob_hash) in read_tree

    def test_batch_cat_file(self, git_repo, db):
        """测试 batch_cat_file 的批量读取能力"""
        # 1. Prepare objects
        h1 = db.hash_object(b"obj1")
        h2 = db.hash_object(b"obj2")
        h3_missing = "a" * 40  # non-existent

        # 2. Batch fetch
        results = db.batch_cat_file([h1, h2, h3_missing, h1])  # Duplicate h1

        # 3. Verify
        assert len(results) == 2
        assert results[h1] == b"obj1"
        assert results[h2] == b"obj2"
        assert h3_missing not in results
