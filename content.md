好的，我们继续推进 `sync` 功能的开发。

现在执行任务 2.2 和 2.3，核心是重构 `quipu-engine` 的历史存储逻辑，使其与 v1.1 架构蓝图中定义的、支持分布式协作的 Git 引用命名空间保持一致。

## refactor: 使历史存储适应新的 Git 引用命名空间

### 用户需求
根据 `Quipu Sync 功能开发任务列表`，需要执行任务 2.2 和 2.3：
1.  **调整 `HistoryWriter`**: 修改 `GitObjectHistoryWriter` 的节点创建逻辑，使其不再更新单一的 `refs/quipu/history` 引用，而是遵循 v1.1 规范，在 `refs/quipu/local/heads/` 目录下为每个新节点创建一个独立的 head 引用。
2.  **扩展 `HistoryReader`**: 确保 `GitObjectHistoryReader` 能够从新的、包含多个子目录（如 `local/` 和 `remotes/`）的 `refs/quipu/` 命名空间中正确加载所有历史节点。

### 评论
这是一项 foundational 的重构，是实现无冲突 `sync` 的基石。通过从“单历史线”模型切换到“多分支头”模型，我们为每个协作者的探索路径提供了独立的持久化锚点，从根本上解决了远程推送时的竞争问题。

在分析过程中，我发现 `GitObjectHistoryReader` 当前的实现（扫描 `refs/quipu/` 根目录）已经足够健壮，可以自动发现新的子目录结构（如 `local/` 和未来的 `remotes/`），因此无需修改。核心的变更将集中在 `GitObjectHistoryWriter`。

### 目标
1.  修改 `GitObjectHistoryWriter.create_node` 方法中的引用管理逻辑。
2.  新的引用将被创建在 `refs/quipu/local/heads/{new_commit_hash}`。
3.  移除所有更新旧 `refs/quipu/history` 和 `refs/quipu/heads/{hash}` 的代码。
4.  移除删除父节点 head 引用的逻辑，因为它与多分支、非线性的历史模型相悖。

### 基本原理
Quipu Sync v1.1 架构的核心是**物理隔离，逻辑联通**。本次重构在物理层面实现了这一点：每个分支的末端节点（head）都是一个独立的 Git ref，存储在个人专属的 `local/` 命名空间下。这使得 Git 的 `push` 和 `fetch` 操作可以精确地、无冲突地对这些独立的 refs 进行操作，就像管理普通 Git 分支一样。读取器在逻辑层面，通过扫描整个 `refs/quipu/` 目录将这些分散的 refs 重新聚合成一个完整的历史图谱。

### 标签
#intent/refine #flow/ready #priority/high 
#comp/engine 
#concept/history #concept/sync #scope/core 
#ai/instruct
#task/domain/sync #task/object/ref-namespace #task/action/refactor #task-state/continue

---

### Script

#### Acts 1: 重构 HistoryWriter 的引用更新逻辑

我们将精确地替换 `GitObjectHistoryWriter.create_node` 方法中负责管理 Git 引用的代码块，使其符合新的 v1.1 规范。

~~~~~act
patch_file
packages/quipu-engine/src/quipu/core/git_object_storage.py
~~~~~
~~~~~python
        # 3. 引用管理 (Multi-Head Strategy)
        self.git_db.update_ref("refs/quipu/history", new_commit_hash)
        self.git_db.update_ref(f"refs/quipu/heads/{new_commit_hash}", new_commit_hash)

        if parent_commit:
            self.git_db.delete_ref(f"refs/quipu/heads/{parent_commit}")
~~~~~
~~~~~python
        # 3. 引用管理 (QDPS v1.1 - Local Heads Namespace)
        # 在本地工作区命名空间中为新的 commit 创建一个持久化的 head 引用。
        # 这是 push 操作的唯一来源，并且支持多分支图谱，因此不再删除父节点的 head。
        self.git_db.update_ref(f"refs/quipu/local/heads/{new_commit_hash}", new_commit_hash)
~~~~~

### 下一步建议
我们已经成功地将 Quipu 的核心存储引擎与 v1.1 同步架构的命名空间对齐。现在，底层已经准备好进行真正的远程交互。

下一步，我们将执行任务 **2.4**：在 `GitDB` 中实现封装了 `push` 和 `fetch` 核心逻辑的高层方法，为 CLI 命令的实现铺平道路。
