好的，我们已经完成了核心架构的修复和相关测试的更新。现在，我们将这些变更作为一个原子提交，永久性地解决数据丢失和同步问题。

## [COMMIT] fix(engine): 建立节点与快照的强引用以防 GC 回收

### 用户需求
Quipu 历史节点仅通过 Commit Message 中的文本 Trailer 弱引用工作区快照 (`output_tree`)，这导致快照可能被 `git gc` 错误地回收，并且 `quipu sync` 无法正确传输快照数据。需要建立一个 Git 原生的强引用来解决此问题。

### 评论
这是一个至关重要的架构修复，它确保了 Quipu 历史记录的物理完整性和多设备同步的可靠性。通过将工作区快照作为 `snapshot` 子树嵌入，我们利用了 Git 自身的可达性算法来保护数据，这是最健壮的解决方案。

### 目标
1.  已修改 `GitObjectHistoryWriter`，在创建节点时，将其 `output_tree` 作为 `snapshot` 子树强链接到节点的存储树中。
2.  已更新受影响的测试用例 (`test_parent_linking_with_gap`)，使其使用有效的 Git Tree 对象，以通过 `git mktree` 的正确性校验。
3.  创建一个 Git 提交来固化此修复。

### 基本原理
通过在节点的存储树中添加一个 `040000 tree <hash> snapshot` 条目，我们构建了一条从 Quipu Ref 到工作区快照的完整可达路径 (`Ref -> Commit -> Storage Tree -> snapshot -> Workspace Tree`)。这使得 Git 的垃圾回收和数据传输协议能够正确识别并处理工作区快照，从而解决了数据丢失和同步失败的根本问题。

### 标签
#intent/fix #flow/ready #priority/critical #comp/engine #comp/tests #concept/state #concept/sync #scope/core #ai/instruct #task/domain/storage #task/object/git-backend #task/action/structural-linking #task/state/end #task/status/completed

---

### Script

#### Acts 1: 暂存并提交修复

我们将相关的代码和测试文件添加到暂存区，并创建一个描述详尽的 Git 提交。

~~~~~act
git_add
packages/quipu-engine/src/pyquipu/engine/git_object_storage.py
tests/engine/test_git_reader.py
~~~~~

~~~~~act
git_commit
~~~~~
~~~~~text
fix(engine): Establish strong reference to prevent snapshot GC

Previously, a Quipu history node only referenced its corresponding workspace state (output_tree) via a text-based trailer in the commit message. This constituted a weak reference that was invisible to Git's core algorithms.

This led to two critical issues:
1.  **Data Loss**: `git gc` could mistakenly garbage-collect unreferenced workspace tree objects, leading to permanent data loss.
2.  **Sync Failure**: `quipu sync` would only transfer the Quipu node metadata (commits) but not the actual workspace snapshots, as they were not part of the reachable object graph.

This commit fixes the issue by establishing a strong, Git-native reference. The `output_tree` is now included as a `snapshot` subtree within the Quipu node's own storage tree. This ensures that as long as the Quipu commit is reachable, its associated workspace snapshot is also reachable, protecting it from GC and enabling reliable synchronization.

Additionally, a related test (`test_parent_linking_with_gap`) has been updated. The test previously used invalid dummy hashes, which are no longer permissible due to the stricter object validation performed by `git mktree` as part of this fix.
~~~~~
