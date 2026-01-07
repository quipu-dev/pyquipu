import subprocess
import time
from pathlib import Path

import pytest
from pyquipu.engine.git_db import GitDB


@pytest.fixture
def git_env(tmp_path: Path):
    """Setup a real Git environment for testing plumbing commands."""
    repo = tmp_path / "checkout_repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    # Config git user
    subprocess.run(["git", "config", "user.email", "test@quipu.dev"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Quipu Test"], cwd=repo, check=True)
    return repo, GitDB(repo)


class TestCheckoutBehavior:
    def test_checkout_resets_dirty_index(self, git_env):
        """
        验证：当索引/工作区不干净（有未提交的 add）时，checkout_tree 能强制重置并成功。
        这是为了修复之前遇到的 'Entry not uptodate' 崩溃问题。
        """
        repo, db = git_env

        # 1. 创建状态 A
        (repo / "f.txt").write_text("v1")
        hash_a = db.get_tree_hash()

        # 此时需要将 A 的状态提交到 Git 对象库，否则后续 checkout 找不到 tree
        # 我们可以借用 commit_tree 来固化它，虽然这里不依赖 commit，但得有 tree 对象
        # get_tree_hash 内部其实已经 write-tree 了，所以 tree 对象存在。

        # 为了让 checkout 有意义，我们先手动让工作区处于状态 A
        # (其实 get_tree_hash 并没有修改工作区，所以现在工作区就是 v1)

        # 2. 创建状态 B
        (repo / "f.txt").write_text("v2")
        hash_b = db.get_tree_hash()

        # 3. 回到状态 A，准备制造麻烦
        db.checkout_tree(hash_a)
        assert (repo / "f.txt").read_text() == "v1"

        # 4. 制造脏索引：修改文件并添加到暂存区
        (repo / "f.txt").write_text("dirty_v3")
        subprocess.run(["git", "add", "f.txt"], cwd=repo, check=True)

        # 此时索引中的 f.txt 是 "dirty_v3"，与 hash_a 的 "v1" 不一致。
        # 旧的 read-tree -m 会在这里崩溃。

        # 5. 尝试强制切换到状态 B
        # 这里的 old_tree_hash 参数对于新的实现其实是可选的，但为了模拟 Engine 的调用我们传进去
        db.checkout_tree(new_tree_hash=hash_b, old_tree_hash=hash_a)

        # 6. 验证
        # 操作应该成功（不抛异常），且文件内容应为 v2
        assert (repo / "f.txt").read_text() == "v2"

        # 验证索引也被正确更新到了状态 B
        # 通过检查索引中 f.txt 的 blob hash 是否匹配 v2 的 hash
        ls_files = subprocess.check_output(["git", "ls-files", "-s", "f.txt"], cwd=repo).decode()
        # v2 content is "v2" -> git hash-object -t blob --stdin <<< "v2" -> ...
        # We can just verify it's NOT the hash of "dirty_v3"
        # "dirty_v3" hash:
        dirty_hash = (
            subprocess.check_output(["git", "hash-object", "-t", "blob", "--stdin"], input=b"dirty_v3", cwd=repo)
            .decode()
            .strip()
        )

        assert dirty_hash not in ls_files, "Index should have been reset from the dirty state"

    def test_checkout_optimization_mtime(self, git_env):
        """
        验证：对于未发生变更的文件，checkout_tree 不会更新其 mtime。
        这证明了 read-tree -u 的 diff 优化生效了。
        """
        repo, db = git_env

        # 1. 创建状态 A: 包含一个不变文件和一个变动文件
        common_file = repo / "common.txt"
        common_file.write_text("I am constant")

        changing_file = repo / "change.txt"
        changing_file.write_text("v1")

        hash_a = db.get_tree_hash()

        # 2. 创建状态 B: common 不变，change 变
        changing_file.write_text("v2")
        hash_b = db.get_tree_hash()

        # 3. 切换回 A
        db.checkout_tree(hash_a)

        # 记录 common.txt 的 mtime
        # 为了防止文件系统时间分辨率问题（有些是秒级），我们强制 sleep 一下
        time.sleep(1.1)
        mtime_before = common_file.stat().st_mtime

        # 4. 切换到 B
        # 理论上 common.txt 的 blob hash 没变，git 应该跳过它
        db.checkout_tree(new_tree_hash=hash_b, old_tree_hash=hash_a)

        # 5. 验证
        mtime_after = common_file.stat().st_mtime

        assert mtime_after == mtime_before, "Unchanged file was touched! Optimization failed."

        assert changing_file.read_text() == "v2", "Changed file was not updated."
