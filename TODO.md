## ✅ 已完成里程碑

我们已经成功完成了 Axon v4.2 架构的核心重构和引擎集成。主要成就包括：

*   **引擎集成与核心生命周期**：Phantom State Engine 不再是一个孤立的模块。它现在完全驱动着 Axon 的核心“感知-行动-记录”循环。应用启动时会自动对齐状态（`align`），在执行 Plan 前会自动捕获任何环境漂移（`capture_drift`），并在成功后将 Plan 固化为历史节点（`create_plan_node`）。

*   **核壳分离架构 (Core-Shell Architecture)**：我们通过将业务逻辑（**核**：`core/controller.py`）与 CLI 交互（**壳**：`main.py`）彻底解耦，从根本上解决了测试环境的 I/O 冲突问题。这不仅使测试变得极其稳定，也为未来将 Axon 核心逻辑暴露为 API 或集成到其他工具中奠定了基础。

*   **端到端测试验证**：新的分层架构由一套全新的、稳定的集成测试套件（`tests/test_integration_v2.py`）提供支持，所有测试均已通过，证明了新设计的健壮性和正确性。

---

## 🚀 Axon v4.2 开发路线图

### ✅ 阶段 1: 幽灵引擎内核 (已完成)

这是 v4.2 架构中最复杂、最核心的部分。我们已经构建并验证了一个功能完备的状态引擎地基。

*   [x] **Git 数据库接口 (`core/git_db.py`)**
    *   [x] 实现零污染的影子索引 (`shadow_index`)
    *   [x] 实现精确的状态指纹计算 (`get_tree_hash`)
    *   [x] 实现历史保活机制 (`create_anchor_commit`, `update_ref`)
    *   [x] 实现 Git 血统检测 (`is_ancestor`)
*   [x] **数据模型与历史加载器 (`core/models.py`, `core/history.py`)**
    *   [x] 定义 `AxonNode` 数据结构
    *   [x] 实现从文件系统加载历史图谱 (`load_history_graph`)
*   [x] **核心状态机逻辑 (`core/engine.py`)**
    *   [x] 实现 `align` 方法，可准确识别 `CLEAN`, `DIRTY`, `ORPHAN` 状态
    *   [x] 实现 `capture_drift` 方法，可自动将漂移状态固化为 `CaptureNode`
*   [x] **测试驱动开发 (TDD)**
    *   [x] 完整的单元测试覆盖了 `GitDB` 和 `Engine` 的所有核心功能

---

### ✅ 阶段 2: 集成与运行时 (已完成)

我们将强大的 `Engine` 与用户可见的 `CLI` 和 `Executor` 连接起来，形成了完整的“感知-行动”循环。

*   [x] **CLI 与引擎集成 (`main.py`, `core/controller.py`)**
    *   [x] Engine 在应用启动时由 Controller 实例化。
    *   [x] Controller 调用 `engine.align()` 获取当前状态。
*   [x] **实现核心生命周期**
    *   [x] **处理 `DIRTY` 状态**：在执行 Plan 之前检测到 `DIRTY`，自动调用 `engine.capture_drift()`。
    *   [x] **处理 `ORPHAN` 状态**：如果是首次运行，执行一个“创世捕获”（Genesis Capture）。
*   [x] **实现 Plan 节点生成**
    *   [x] 在 `Executor` **成功执行完**所有 `acts` 后，计算新的 `output_tree_hash`。
    *   [x] 为 `Engine` 添加并实现了 `create_plan_node(...)` 方法。
    *   [x] Controller 调用该方法，将本次执行的 Plan 固化为一个新的 `PlanNode`，并更新 Git 引用。
*   [x] **端到端测试**
    *   [x] 编写了新的集成测试 (`test_integration_v2.py`)，模拟 `axon run plan.md` 的完整流程，验证 Capture 和 Plan 节点都按预期生成，且所有测试通过。

---

### ➡️ 阶段 3: 用户体验与核心功能 (当前阶段)

当核心循环跑通后，我们将添加让用户能够与历史图谱交互的核心功能。

*   [x] **历史查看 (`axon log`)**
    *   [x] 实现一个新的 CLI 命令 `axon log`，用于列出 `.axon/history` 中的所有节点。
    *   [ ] (可选) 实现 `--graph` 标志，以 TUI 形式可视化历史分支。
*   [x] **时间旅行 (`axon checkout`)**
    *   [x] 实现 CLI 命令 `axon checkout <node_hash>`。
    *   [x] 在 `GitDB` 中添加 `checkout_tree(tree_hash)` 方法，用于将工作区硬重置到指定状态。
*   [ ] **分布式协作 (`axon sync`)**
    *   [ ] 实现 `axon sync` 命令，用于 `git push/pull` `refs/axon/history` 引用。

---

### 🛠️ 阶段 4: 健壮性与打磨

让 Axon 从一个原型变成一个可靠的工具。

*   [ ] **完善错误处理**：处理 `git` 未安装、权限不足、Plan 执行失败等情况。
*   [ ] **配置系统**：允许用户通过 `.axon/config.yml` 自定义行为。
*   [ ] **文档更新**：更新 `README.md` 和 `PROMPT.md`，反映 v4.2 的新概念和工作流。
*   [ ] **打包与分发**：为 `pip` 发布做准备。
