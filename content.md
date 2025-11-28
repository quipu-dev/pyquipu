好的，我们已经成功重构了 `sync` 机制并添加了相应的集成测试来验证其正确性。现在是时候将这些变更作为一个逻辑上完整的工作单元提交了。

我将生成一个符合规范的 `[COMMIT]` 计划，其中包含 `git add` 和 `git commit` 指令。

## [COMMIT] refactor: 实现无损多设备同步机制

### 用户需求
当前的 `quipu sync` 命令在多设备场景下存在数据丢失的风险。这是因为 `push --prune` 会用当前设备不完整的本地历史覆盖远程的完整历史。需要将 `sync` 流程重构为一个安全的、非破坏性的双向同步模型。

### 评论
这是一个关键的架构修复，解决了之前设计中的严重缺陷。新的“拉取-调和-推送”模型将确保用户可以在多个设备之间安全、无缝地工作，而不会丢失任何历史记录。

### 目标
1.  在 `GitDB` 中移除 `push` 操作的 `--prune` 选项，使其变为非破坏性操作。
2.  在 `GitDB` 中增加一个新的 `reconcile` 方法，用于将远程获取的 refs 安全地合并到本地工作区。
3.  调整 `quipu-cli` 中的 `sync` 命令，使其遵循 `Fetch -> Reconcile -> Push` 的正确顺序。
4.  添加了相应的集成测试来验证新逻辑的正确性，并确保不会发生数据丢失。

### 基本原理
通过将 `sync` 从一个单向的“镜像推送”操作，转变为一个真正的双向同步操作，来保证数据的完整性。首先拉取远程的全量数据到本地的一个隔离命名空间，然后通过一个新的“调和”步骤将这些新数据安全地合并到本地工作区，最后再将这个合并后的、最完整的本地状态推送回远程。这个过程确保了任何时候都不会有数据被意外删除。

### 标签
#intent/refine #flow/ready #priority/critical #comp/engine #comp/cli #comp/tests #concept/sync #scope/core #ai/brainstorm #task/domain/sync #task/object/multi-device #task/action/bug-fix #task/state/end #task/status/completed

---

### Script

#### Acts 1: 提交变更

现在，我们将所有相关的代码修改和新的测试文件添加到 Git 暂存区，并创建一个提交。

~~~~~act
git_add
packages/quipu-engine/src/quipu/core/git_db.py
packages/quipu-cli/src/quipu/cli/commands/remote.py
tests/integration/test_sync_workflow.py
~~~~~

~~~~~act
git_commit
~~~~~
~~~~~text
refactor(sync): implement non-destructive multi-device sync

Refactors the `quipu sync` command to prevent data loss in multi-device workflows. The previous implementation used `git push --prune`, which could overwrite remote history with an incomplete local view.

This commit introduces a safe "Fetch -> Reconcile -> Push" model:
1.  **Fetch**: All remote user refs are fetched into a local, isolated `remotes/` namespace.
2.  **Reconcile**: A new `reconcile_local_with_remote` method in `GitDB` safely copies any missing remote refs into the local working `local/` namespace. This is an additive-only operation.
3.  **Push**: The now-complete local history is pushed back to the remote *without* the `--prune` flag, ensuring no remote refs are ever deleted unintentionally.

Additionally, a comprehensive integration test suite (`test_sync_workflow.py`) has been added to validate the new behavior, including scenarios for multi-device reconciliation and ensuring that local ref deletion does not propagate to the remote. This resolves a critical data integrity issue.
~~~~~
