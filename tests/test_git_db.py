import pytest
import subprocess
from pathlib import Path
from core.git_db import GitDB

@pytest.fixture
def git_repo(tmp_path):
    """创建一个初始化的 Git 仓库"""
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init"], cwd=root, check=True)
    
    # 配置 User，防止 Commit 报错
    subprocess.run(["git", "config", "user.email", "test@axon.dev"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Axon Test"], cwd=root, check=True)
    
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
        Axon 计算 Hash 的过程绝对不能把文件加入到用户的暂存区。
        """
        f = git_repo / "wip.txt"
        f.write_text("working in progress", encoding="utf-8")
        
        # 1. 确保用户暂存区是空的
        status_before = subprocess.check_output(["git", "status", "--porcelain"], cwd=git_repo).decode()
        assert "??" in status_before  # Untracked
        assert "A" not in status_before # Not staged
        
        # 2. Axon 执行计算
        _ = db.get_tree_hash()
        
        # 3. 验证用户暂存区依然是空的
        status_after = subprocess.check_output(["git", "status", "--porcelain"], cwd=git_repo).decode()
        assert status_after == status_before
        
        # 验证 Shadow Index 文件已被清理
        assert not (git_repo / ".axon" / "tmp_index").exists()

    def test_exclude_axon_dir(self, git_repo, db):
        """测试：.axon 目录内的变化不应改变 Tree Hash"""
        (git_repo / "main.py").touch()
        hash_base = db.get_tree_hash()
        
        # 在 .axon 目录下乱写东西
        axon_dir = git_repo / ".axon"
        axon_dir.mkdir(exist_ok=True)
        (axon_dir / "history.md").write_text("some history", encoding="utf-8")
        
        hash_new = db.get_tree_hash()
        
        assert hash_base == hash_new

    def test_anchor_commit_persistence(self, git_repo, db):
        """测试：创建影子锚点"""
        (git_repo / "f.txt").write_text("content")
        tree_hash = db.get_tree_hash()
        
        # 创建锚点
        commit_hash = db.create_anchor_commit(tree_hash, "Axon Shadow Commit")
        
        # 更新引用
        ref_name = "refs/axon/history"
        db.update_ref(ref_name, commit_hash)
        
        # 验证 Git 能够读取该引用
        read_back = subprocess.check_output(
            ["git", "rev-parse", ref_name], cwd=git_repo
        ).decode().strip()
        
        assert read_back == commit_hash
        
        # 验证该 Commit 确实指向正确的 Tree
        commit_tree = subprocess.check_output(
            ["git", "show", "--format=%T", "-s", commit_hash], cwd=git_repo
        ).decode().strip()
        
        assert commit_tree == tree_hash

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
        assert "Git plumbing error" not in caplog.text    def test_checkout_tree(self, git_repo: Path, db: GitDB):
        """Test the low-level hard reset functionality of checkout_tree."""
        # 1. Create State A
        (git_repo / "file1.txt").write_text("version 1", "utf-8")
        (git_repo / "common.txt").write_text("shared", "utf-8")
        hash_a = db.get_tree_hash()
        
        # Create a file inside .axon to ensure it's not deleted
        axon_dir = git_repo / ".axon"
        axon_dir.mkdir(exist_ok=True)
        (axon_dir / "preserve.me").touch()

        # 2. Create State B
        (git_repo / "file1.txt").write_text("version 2", "utf-8")
        (git_repo / "file2.txt").write_text("new file", "utf-8")
        
        # 3. Checkout to State A
        db.checkout_tree(hash_a)
        
        # 4. Assertions
        assert (git_repo / "file1.txt").read_text("utf-8") == "version 1"
        assert (git_repo / "common.txt").exists()
        assert not (git_repo / "file2.txt").exists(), "file2.txt should have been cleaned"
        assert (axon_dir / "preserve.me").exists(), ".axon directory should be preserved"