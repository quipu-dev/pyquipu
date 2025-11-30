## [WIP] fix: 建立 Quipu 节点与工作区快照的强引用连接

### 错误分析
当前 `GitObjectHistoryWriter` 在构建 Quipu 历史节点（Commit）时，仅将用户工作区的状态哈希 (`output_tree`) 以文本形式记录在 Commit Message 的 `Trailer` (`X-Quipu-Output-Tree`) 中。

这种实现方式导致了**弱引用 (Weak Reference)** 问题：
1.  **GC 回收风险**：Git 的底层图谱算法无法识别 Commit 与 `output_tree` 之间的依赖关系。如果 `output_tree` 没有被其他分支（如 `master`）引用，Git 的垃圾回收机制 (`git gc`) 会将其视为“不可达对象”并将其物理删除。
2.  **同步失效**：`git push` / `git fetch` 仅传输可达对象。因此，远程同步时只会传输 Quipu 的元数据（Commit, metadata.json），而丢失实际的工作区文件快照，导致无法在远程恢复状态。

### 用户需求
修改 `quipu-engine` 的写入逻辑，在创建历史节点时，建立从 Quipu Commit 到用户工作区 Tree 的**强引用 (Strong Reference)**，以防止数据被 GC 并确保同步完整性。

### 评论
这是一个**严重 (Critical)** 级别的架构缺陷修复。如果不修复，Quipu 的历史记录将面临随机性的数据丢失风险，且无法支持多机协作。修复方案非常优雅：利用 Git 的 Subtree 机制，将用户工作区作为一个名为 `snapshot` 的子树挂载到 Quipu 的存储树中。

### 目标
1.  修改 `GitObjectHistoryWriter.create_node` 方法。
2.  在构建 `tree_descriptor` 时，增加一行 `040000 tree {output_tree}\tsnapshot`。
3.  确保新生成的节点在 Git 图谱层面物理连接到用户的工作区状态。

### 基本原理
通过在 Quipu 的内部存储树 (`Storage Tree`) 中添加一个指向 `output_tree` 的 `tree` 类型条目，我们构建了如下的引用链：
`Ref` -> `Quipu Commit` -> `Storage Tree` -> `snapshot (Directory)` -> `User Workspace Tree`
这就构成了一条标准的 Git 可达性路径，Git 的所有底层工具（GC, Prune, Push, Fetch, Fsck）都能正确处理它。

### 标签
#intent/fix #flow/ready #priority/critical #comp/engine #concept/state #scope/core #ai/instruct #task/domain/storage #task/object/git-backend #task/action/structural-linking #task/state/begin

---

### Script

#### Acts 1: 修改 GitObjectHistoryWriter 以包含快照子树

我们在 `packages/quipu-engine/src/pyquipu/engine/git_object_storage.py` 文件中，修改 `create_node` 方法的 `tree_descriptor` 构建逻辑。

~~~~~act
patch_file
packages/quipu-engine/src/pyquipu/engine/git_object_storage.py
~~~~~
~~~~~python
        meta_blob_hash = self.git_db.hash_object(meta_json_bytes)
        content_blob_hash = self.git_db.hash_object(content_md_bytes)

        # 使用 100444 权限 (只读文件)
        tree_descriptor = f"100444 blob {meta_blob_hash}\tmetadata.json\n100444 blob {content_blob_hash}\tcontent.md"
        tree_hash = self.git_db.mktree(tree_descriptor)

        # 1. 确定父节点 (Topological Parent)
~~~~~
~~~~~python
        meta_blob_hash = self.git_db.hash_object(meta_json_bytes)
        content_blob_hash = self.git_db.hash_object(content_md_bytes)

        # 使用 100444 权限 (只读文件)
        # 关键修复：建立强引用！将 output_tree 作为名为 'snapshot' 的子目录挂载。
        # 这确保了 Git 的 GC 不会回收工作区快照，且 sync 时能同步实际内容。
        tree_descriptor = (
            f"100444 blob {meta_blob_hash}\tmetadata.json\n"
            f"100444 blob {content_blob_hash}\tcontent.md\n"
            f"040000 tree {output_tree}\tsnapshot"
        )
        tree_hash = self.git_db.mktree(tree_descriptor)

        # 1. 确定父节点 (Topological Parent)
~~~~~

### 下一步建议
1.  **验证修复**：执行此计划后，创建一个新节点，然后运行 `git ls-tree <commit-hash>`，确认是否能看到 `snapshot` 目录。
2.  **数据迁移 (重要)**：此修复仅保护**新创建**的节点。旧节点仍然处于危险状态。我们需要规划一个迁移任务（Refactor），编写一个脚本遍历所有旧的 Quipu 节点，如果其关联的 Tree 对象尚未被 GC，则重写这些节点以包含 `snapshot` 引用。
