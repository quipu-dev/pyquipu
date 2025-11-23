# 🏗️ 架构深度解析

Axon 采用了 **核壳分离 (Core-Shell)** 架构。

## 目录结构

*   **`main.py` (Shell)**: 负责 CLI 参数解析、日志初始化、用户交互（Typer）。它不包含业务逻辑，只负责调用 Core。
*   **`core/` (Core)**:
    *   `controller.py`: 业务逻辑入口。协调 Engine、Parser 和 Executor。
    *   `engine.py`: **幽灵状态引擎**。负责 `align`（定位）、`capture_drift`（捕获）和 `create_plan_node`（记录）。
    *   `git_db.py`: Git 底层接口。负责 `read-tree`, `write-tree`, `commit-tree` 等 Plumbing 操作。
    *   `executor.py`: 执行器。负责加载插件并执行具体的 Act。
*   **`acts/` (Plugins)**: 内置的操作指令实现。

## 数据流 (The Lifecycle)

1.  **启动 (Boot)**:
    *   `Engine` 初始化，通过 `GitDB` 计算当前 Tree Hash。
    *   调用 `align()` 在 `.axon/history` 中查找匹配节点。
    *   如果状态是 `DIRTY` 或 `ORPHAN`，自动触发 Capture 流程，生成快照节点。

2.  **解析 (Parse)**:
    *   `Parser` 扫描输入文本，提取 Act 和 Contexts。
    *   支持自动检测围栏类型（Backtick/Tilde）。

3.  **执行 (Execute)**:
    *   `Executor` 根据注册表查找对应的函数。
    *   根据 ArgMode (Hybrid/Exclusive/BlockOnly) 组装参数。
    *   执行具体的文件操作（默认带交互确认）。

4.  **结晶 (Crystallize)**:
    *   执行成功后，`Controller` 再次获取新的 Tree Hash。
    *   调用 `engine.create_plan_node()` 将本次操作固化为历史记录。