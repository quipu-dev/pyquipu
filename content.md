这是一个非常敏锐的观察。错误原因在于 Quipu 创建的历史节点存储在自定义的引用空间 (`refs/quipu/local/heads/`) 中，并不在标准工作分支 (`master`) 的历史线上。

当你在测试脚本中运行 `git log` 且不带 `--all` 参数时，Git 默认只扫描当前 HEAD (`master`) 的历史，因此找不到任何 Quipu 节点。

## fix: 修复集成测试中 git log 命令缺失 --all 参数的问题

### 错误分析
1.  **现象**: `user_a_commits` 列表为空，导致 `assert len >= 2` 失败。
2.  **原因**: Quipu 的 commit 是“平行宇宙”的一部分，不依附于用户的 `master` 分支。
3.  **修复**: 在 `git log` 命令中添加 `--all` 参数，强制 Git 扫描所有引用（包括 Quipu 的自定义引用）。

### 目标
修改 `tests/integration/test_sync_workflow.py`，确保能正确获取到 User A 的 Quipu 历史提交。

### 标签
#intent/fix #flow/ready #priority/high #comp/tests #concept/sync #scope/core #ai/instruct #task/domain/testing #task/object/sync-workflow #task/action/test #task/state/continue

---

### Script

#### Acts 1: 修正测试文件

~~~~~act
patch_file
tests/integration/test_sync_workflow.py
~~~~~
~~~~~python
        # Capture User A's commit hashes for verification later
        # We expect 2 quipu commits.
        user_a_commits = run_git_command(
            user_a_path, 
            ["log", "--format=%H", "--grep=X-Quipu-Output-Tree"]
        ).splitlines()
        assert len(user_a_commits) >= 2, "User A should have at least 2 Quipu nodes"

        # User A pushes again
~~~~~
~~~~~python
        # Capture User A's commit hashes for verification later
        # We expect 2 quipu commits.
        # NOTE: Must use --all because Quipu commits are not on the master branch.
        user_a_commits = run_git_command(
            user_a_path,
            ["log", "--all", "--format=%H", "--grep=X-Quipu-Output-Tree"]
        ).splitlines()
        assert len(user_a_commits) >= 2, "User A should have at least 2 Quipu nodes"

        # User A pushes again
~~~~~

### 下一步建议
现在再次运行测试：`pytest tests/integration/test_sync_workflow.py`。这次应该能通过了。
