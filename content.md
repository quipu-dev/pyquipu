## 我们将创建一个巨大的、总结性的提交，为 `sync` 功能的完整开发周期画上句号。这个提交将涵盖从最初的架构设计到最终的测试修复所有工作。

### 提交信息

**标题**: `feat(sync): Implement v1.1 distributed collaboration engine`

**正文**:
引入了 Quipu Sync v1.1，这是一个基于 Git 原生能力的、去中心化的、无冲突的协作与历史同步引擎。

该功能的核心是“物理隔离，逻辑联通”的设计哲学。每个协作者在远程仓库的专属命名空间 (`refs/quipu/users/<user_id>/`) 中进行写入，从根本上杜绝了推送冲突。协作通过“订阅”关系实现，系统在读取端将各个独立的探索历史在本地聚合，形成一个统一的、多维的全局视图。

**主要特性与实现**:
*   **Git 原生架构**:
    *   实现了基于 `user.email` 的用户身份规范化 (`get_user_id_from_email`)。
    *   重构了历史写入逻辑，从单一的 `refs/quipu/history` 引用模型迁移到多头的 `refs/quipu/local/heads/{commit_hash}` 模型，为分支和协作奠定了基础。
    *   在 `GitDB` 中实现了 `push_quipu_refs` 和 `fetch_quipu_refs` 方法，封装了与远程仓库交互的 refspec 逻辑，并支持 `--prune` 自动清理。
*   **CLI 与工作流**:
    *   新增 `quipu sync` 命令，负责编排完整的推拉同步流程。
    *   为首次使用的用户实现了自动化的“引导 (Onboarding)”流程，自动从 Git 配置生成并保存 `user_id`。
*   **多所有权支持**:
    *   扩展了 SQLite schema 和 `QuipuNode` 数据模型，增加了 `owner_id` 字段，以支持多用户数据的存储和区分。
    *   重构了 `Hydrator` (数据补水器)，使其能够从 Git 引用路径中解析出每个历史节点的所有者，并正确存入数据库。
*   **测试套件**:
    *   创建了全面的端到端集成测试 (`test_sync_workflow.py`)，覆盖了 Onboarding、Push、Fetch、订阅和 Pruning 等核心场景。
    *   对整个测试套件进行了系统性的大修，使其适应了新的多头 Git 引用架构，修复了因架构变更引发的大量连锁测试失败。

---

### Script

#### Acts 1: 将所有相关变更添加到暂存区

由于这是一个涵盖多个模块的大型功能，我们将添加所有已跟踪的变更。

~~~~~act
git_add
.
~~~~~

#### Acts 2: 执行 Git 提交

~~~~~act
git_commit
~~~~~
~~~~~
feat(sync): Implement v1.1 distributed collaboration engine

引入了 Quipu Sync v1.1，这是一个基于 Git 原生能力的、去中心化的、无冲突的协作与历史同步引擎。

该功能的核心是“物理隔离，逻辑联通”的设计哲学。每个协作者在远程仓库的专属命名空间 (`refs/quipu/users/<user_id>/`) 中进行写入，从根本上杜绝了推送冲突。协作通过“订阅”关系实现，系统在读取端将各个独立的探索历史在本地聚合，形成一个统一的、多维的全局视图。

主要特性与实现:
*   **Git 原生架构**:
    *   实现了基于 `user.email` 的用户身份规范化 (`get_user_id_from_email`)。
    *   重构了历史写入逻辑，从单一的 `refs/quipu/history` 引用模型迁移到多头的 `refs/quipu/local/heads/{commit_hash}` 模型，为分支和协作奠定了基础。
    *   在 `GitDB` 中实现了 `push_quipu_refs` 和 `fetch_quipu_refs` 方法，封装了与远程仓库交互的 refspec 逻辑，并支持 `--prune` 自动清理。
*   **CLI 与工作流**:
    *   新增 `quipu sync` 命令，负责编排完整的推拉同步流程。
    *   为首次使用的用户实现了自动化的“引导 (Onboarding)”流程，自动从 Git 配置生成并保存 `user_id`。
*   **多所有权支持**:
    *   扩展了 SQLite schema 和 `QuipuNode` 数据模型，增加了 `owner_id` 字段，以支持多用户数据的存储和区分。
    *   重构了 `Hydrator` (数据补水器)，使其能够从 Git 引用路径中解析出每个历史节点的所有者，并正确存入数据库。
*   **测试套件**:
    *   创建了全面的端到端集成测试 (`test_sync_workflow.py`)，覆盖了 Onboarding、Push、Fetch、订阅和 Pruning 等核心场景。
    *   对整个测试套件进行了系统性的大修，使其适应了新的多头 Git 引用架构，修复了因架构变更引发的大量连锁测试失败。
~~~~~
