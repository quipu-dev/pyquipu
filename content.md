分析正确，测试失败暴露了我们实现中的两个缺陷和一个测试用例中的逻辑漏洞。

1.  **`test_pull_only_mode` 失败原因**: 测试用例本身存在逻辑问题。它期望用户 B 拉取用户 A 的历史，但从未在用户 B 的配置文件中添加对用户 A 的订阅。因此，`sync` 命令只会拉取用户 B 自己的（空的）远程历史，导致断言失败。
2.  **`test_push_force_mode` 失败原因**: 实现有误。`git push --force` 命令本身只会强制覆盖匹配的远程分支，**并不会删除**在远程存在但在本地不存在的分支。要实现“让远程与本地完全一致”的修剪（prune）行为，`push` 命令需要附带 `--prune` 标志。
3.  **`test_pull_prune_mode` 失败原因**: 这个失败是前一个问题的连锁反应。`push` 命令未能正确地在远程建立初始状态，导致后续的 `pull-prune` 操作基于不正确的远程状态进行计算，最终错误地删除了不该删除的本地分支。

我将生成一个计划，一次性修复这三个问题。

## [WIP] fix(tests): 修复同步模式的实现和集成测试

### 错误分析
当前的同步模式集成测试失败，原因有三：
1.  **实现缺陷**: `push-force` 模式的底层 `GitDB.push_quipu_refs` 方法缺少 `--prune` 标志，导致它无法删除远程仓库中多余的分支，未能实现预期的“镜像”效果。
2.  **测试逻辑缺陷**: `test_pull_only_mode` 测试用例在验证用户 B 拉取用户 A 的历史之前，忘记了为用户 B 添加对用户 A 的订阅，导致测试场景设置不完整。
3.  **连锁故障**: `test_pull_prune_mode` 的失败很可能是由 `push-force` 实现不正确导致的。由于前置步骤未能正确清理远程状态，导致 `pull-prune` 在一个脏的远程状态下执行，从而产生了错误的结果。

### 用户需求
1.  修正 `GitDB.push_quipu_refs` 方法，在 `force=True` 时，为 `git push` 命令添加 `--prune` 标志。
2.  修正 `test_pull_only_mode` 测试，在执行 `pull-only` 操作前，为用户 B 添加对用户 A 的订阅。
3.  确保所有同步相关的测试都能稳定通过。

### 评论
这些修复是确保 `sync` 命令可靠性的关键。通过修正底层的 Git 调用和完善测试用例的逻辑，我们可以保证每种同步模式的行为都符合预期，为用户提供一个稳定、可预测的协作工具。

### 目标
1.  修改 `packages/quipu-engine/src/quipu/engine/git_db.py` 文件。
2.  修改 `tests/integration/test_sync_modes.py` 文件。
3.  使所有与 `sync` 相关的集成测试全部通过。

### 基本原理
我们将直接在 `GitDB` 的 `push_quipu_refs` 方法中添加 `--prune` 标志，这是 `git` 命令提供的标准功能，用于在推送时删除远程不再存在的对应分支。同时，在 `test_pull_only_mode` 测试中，我们将通过写入配置文件来模拟用户订阅操作，确保测试环境的正确性。这两个修复将从根本上解决所有相关的测试失败问题。

### 标签
#intent/fix #intent/tooling #flow/ready #priority/critical #comp/engine #comp/tests #concept/sync #scope/core #ai/instruct #task/domain/sync #task/object/sync-modes #task/action/bug-fix #task/state/continue

---

### Script

#### Acts 1: 修正 `git_db.py` 中 `push_quipu_refs` 的实现

我们在 `force` 模式下为 `git push` 添加 `--prune` 选项。

~~~~~act
patch_file
packages/quipu-engine/src/quipu/engine/git_db.py
~~~~~
~~~~~python
    def push_quipu_refs(self, remote: str, user_id: str, force: bool = False):
        """
        将本地 Quipu heads 推送到远程用户专属的命名空间。
        遵循 QDPS v1.1 规范。
        """
        refspec = f"refs/quipu/local/heads/*:refs/quipu/users/{user_id}/heads/*"
        action = "Force-pushing" if force else "Pushing"
        logger.info(f"🚀 {action} Quipu history to {remote} for user {user_id}...")

        cmd = ["push", remote, refspec]
        if force:
            cmd.append("--force")
        self._run(cmd)
~~~~~
~~~~~python
    def push_quipu_refs(self, remote: str, user_id: str, force: bool = False):
        """
        将本地 Quipu heads 推送到远程用户专属的命名空间。
        遵循 QDPS v1.1 规范。
        """
        refspec = f"refs/quipu/local/heads/*:refs/quipu/users/{user_id}/heads/*"
        action = "Force-pushing" if force else "Pushing"
        logger.info(f"🚀 {action} Quipu history to {remote} for user {user_id}...")

        cmd = ["push", remote, refspec]
        if force:
            cmd.extend(["--force", "--prune"])
        self._run(cmd)
~~~~~

#### Acts 2: 修复 `test_sync_modes.py` 中的逻辑漏洞

现在，我们修复测试用例，确保 `pull-only` 模式的测试环境设置正确。

~~~~~act
patch_file
tests/integration/test_sync_modes.py
~~~~~
~~~~~python
    def test_pull_only_mode(self, sync_test_environment):
        """User B pulls User A's changes, but does not push its own."""
        remote_path, user_a_path, user_b_path = sync_test_environment
        user_a_id = get_user_id_from_email("user.a@example.com")

        # User A creates a node and pushes
        node_a = create_node(user_a_path, "node_from_a_for_pull")
        runner.invoke(app, ["sync", "--work-dir", str(user_a_path)])

        # User B creates a node but doesn't push
        node_b = create_node(user_b_path, "node_from_b_local")

        # User B syncs with pull-only
        sync_result = runner.invoke(app, ["sync", "--work-dir", str(user_b_path), "--mode", "pull-only"])
        assert sync_result.exit_code == 0
~~~~~
~~~~~python
    def test_pull_only_mode(self, sync_test_environment):
        """User B pulls User A's changes, but does not push its own."""
        remote_path, user_a_path, user_b_path = sync_test_environment
        user_a_id = get_user_id_from_email("user.a@example.com")
        import yaml

        # User A creates a node and pushes
        node_a = create_node(user_a_path, "node_from_a_for_pull")
        runner.invoke(app, ["sync", "--work-dir", str(user_a_path)])

        # User B creates a node but doesn't push
        node_b = create_node(user_b_path, "node_from_b_local")

        # [FIX] User B must subscribe to User A to be able to pull their changes.
        runner.invoke(app, ["sync", "--work-dir", str(user_b_path)]) # Onboard B first
        config_path_b = user_b_path / ".quipu" / "config.yml"
        with open(config_path_b, "r") as f:
            config_b = yaml.safe_load(f)
        config_b["sync"]["subscriptions"] = [user_a_id]
        with open(config_path_b, "w") as f:
            yaml.dump(config_b, f)


        # User B syncs with pull-only
        sync_result = runner.invoke(app, ["sync", "--work-dir", str(user_b_path), "--mode", "pull-only"])
        assert sync_result.exit_code == 0
~~~~~

### 下一步建议
我们已经修复了实现中的缺陷和测试中的逻辑漏洞。现在，请再次运行测试套件。如果所有测试都通过，我将为你生成一个 `[COMMIT]` 计划，将这些重要的修复工作持久化到版本历史中。
