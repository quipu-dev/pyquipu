好的，我们将全面更新文档以反映最近的功能增强，然后创建一个最终的提交。

### 1. 更新核心概念

我们将精确描述 v4.2 引入的“幽灵状态引擎”和 DAG（有向无环图）历史模型。

~~~~~act
replace
~~~~~
~~~~~path
docs/03_user_guide/01_core_concepts.md
~~~~~
~~~~~old_string
## 4. 幽灵状态引擎 (Phantom State Engine)

Axon v4.2 引入了革命性的状态管理机制：

*   **State is Truth**: Axon 不维护额外的数据库来记录“当前在哪”。它通过计算当前工作区的 **Git Tree Hash** 来定位。
*   **Lazy Capture**: 在执行新指令前，如果发现环境与历史记录不一致（比如用户手动改了代码），Axon 会自动生成一个 **Capture Node** 来保存当前状态。这意味着你永远不用担心 Axon 会覆盖你未保存的工作。
*   **历史即图谱 (History as a DAG)**: Axon 的历史记录不是一条直线，而是一个**有向无环图 (DAG)**。当你 `checkout` 到一个旧节点并执行新的 Plan 时，就会创建出一个新的分支。这使得无损实验和多方案探索成为可能，也是 `undo`, `redo`, `prev`, `next` 等导航命令的基础。
~~~~~
~~~~~new_string
## 4. 幽灵状态引擎 (Phantom State Engine)

Axon v4.2 引入了革命性的状态管理机制，它基于 Git 底层对象模型，而非传统的文件数据库。

*   **状态即真理 (State is Truth)**: Axon 不维护任何状态数据库。它通过实时计算当前工作区所有文件的 **Git Tree Hash** 来唯一确定当前所处的状态。这从根本上杜绝了状态不同步的问题。

*   **惰性捕获 (Lazy Capture)**: 在执行新指令前，如果 Axon 发现当前工作区的状态与历史记录不符（例如，你手动修改了代码），它会自动触发一次“捕获”，生成一个 **Capture Node** 来保存你未记录的变更。这意味着你的工作永远不会被覆盖或丢失。

*   **事件时间轴 (Event-based Timeline)**: Axon v4.3 之后，即使一个操作没有修改任何文件（如 `git commit` 或运行测试），它也会被记录为一个**幂等节点 (Idempotent Node)**。这确保了 Axon 的历史是一条完整的、可审计的**事件流**，而不仅仅是文件快照。

*   **历史即图谱 (History as a DAG)**: Axon 的历史记录不是一条直线，而是一个**有向无环图 (DAG)**。当你 `checkout` 到一个旧节点并执行新的 Plan 时，就会自然地创建出一个新的分支。这使得无损实验和多方案探索成为可能，也是 `undo`, `redo`, `prev`, `next` 等导航命令的基础。
~~~~~

### 2. 更新 CLI 命令参考

这是最重要的部分，我们将添加 `save`, `discard`, `sync`，导航命令，并更新 `ui` 命令的描述。

~~~~~act
replace
~~~~~
~~~~~path
docs/03_user_guide/02_cli_reference.md
~~~~~
~~~~~old_string
# 💻 CLI 命令参考

Axon 的命令行界面设计得简洁直观。所有命令的入口均为 `python main.py`（安装后为 `axon`）。

## `run` - 执行脚本

执行 Markdown 文件中的指令。

```bash
axon run [FILE] [OPTIONS]
```

*   `FILE`: (可选) 要执行的 Markdown 文件路径。如果不提供且没有管道输入，默认寻找 `o.md`。
*   `--work-dir, -w`: 指定工作区根目录。默认为当前目录。
*   `--yolo, -y`: **You Only Look Once**。跳过所有交互式确认，直接执行。
*   `--parser, -p`: 指定解析器 (`auto`, `backtick`, `tilde`)。默认为 `auto`。
*   `--list-acts, -l`: 列出所有可用的 Act 指令。

**示例**:
```bash
# 管道模式：将 LLM 的输出直接喂给 Axon
llm "Refactor code" | axon run -y
```

## `log` - 查看历史

显示 Axon 的操作历史图谱。

```bash
axon log [OPTIONS]
```

*   `--work-dir, -w`: 指定工作区。

输出将显示时间戳、节点类型（Plan/Capture）、Hash 前缀以及摘要。

## `checkout` - 时间旅行

将工作区重置到指定的历史状态。

```bash
axon checkout <HASH_PREFIX> [OPTIONS]
```

*   `<HASH_PREFIX>`: 目标状态 Hash 的前几位（从 `log` 命令获取）。
*   `--force, -f`: 强制重置，不询问确认。

**安全机制**: 如果当前工作区有未记录的修改，`checkout` 会在切换前自动创建一个 Capture 节点保存现场。
~~~~~
~~~~~new_string
# 💻 CLI 命令参考

Axon 的命令行界面设计得简洁直观。所有命令的入口均为 `axon`。

## `run` - 执行脚本

执行 Markdown 文件中的指令。

```bash
axon run [FILE] [OPTIONS]
```

*   `FILE`: (可选) 要执行的 Markdown 文件路径。如果不提供且没有管道输入，默认寻找 `o.md`。
*   `--work-dir, -w`: 指定工作区根目录。默认为当前目录。
*   `--yolo, -y`: **You Only Look Once**。跳过所有交互式确认，直接执行。
*   `--parser, -p`: 指定解析器 (`auto`, `backtick`, `tilde`)。默认为 `auto`。
*   `--list-acts, -l`: 列出所有可用的 Act 指令。

**示例**:```bash
# 管道模式：将 LLM 的输出直接喂给 Axon
llm "Refactor code" | axon run -y
```

## `log` - 查看历史

以列表形式显示 Axon 的操作历史。

```bash
axon log [OPTIONS]
```

*   `--work-dir, -w`: 指定工作区。

输出将显示时间戳、节点类型（Plan/Capture）、Hash 前缀以及摘要。

## `checkout` - 时间旅行

将工作区重置到指定的历史状态。

```bash
axon checkout <HASH_PREFIX> [OPTIONS]
```

*   `<HASH_PREFIX>`: 目标状态 Hash 的前几位（从 `log` 或 `ui` 命令获取）。
*   `--force, -f`: 强制重置，不询问确认。

**安全机制**: 如果当前工作区有未记录的修改，`checkout` 会在切换前自动创建一个 Capture 节点保存现场。

## `discard` - 丢弃变更

丢弃工作区中所有未被 Axon 记录的变更，将文件恢复到上一个干净的历史状态。

```bash
axon discard [OPTIONS]
```

*   `--force, -f`: 强制执行，不询问确认。

**使用场景**: 当一个 Plan 执行失败或被中途取消后，工作区可能会处于一个包含部分修改的“脏”状态。`discard` 命令提供了一个类似于 `git checkout .` 的功能，可以一键清理这些残留的修改，让你从一个已知的良好起点重新开始。

## `sync` - 远程同步

同步 Axon 的隐形历史记录到远程 Git 仓库。

```bash
axon sync [OPTIONS]
```

*   `--remote, -r`: 指定远程仓库名称（默认 `origin`）。

此命令通过 `git push/pull refs/axon/history` 实现历史共享，让团队成员可以复现彼此的 AI 操作历史。

## `save` - 保存快照 (微提交)

创建一个当前工作区状态的轻量级快照。

```bash
axon save "[MESSAGE]" [OPTIONS]
```

*   `[MESSAGE]`: (可选) 为这个快照添加一句描述，例如 "尝试修复 bug" 或 "重构前的状态"。
*   `--work-dir, -w`: 指定工作区。

**核心用途**:
`save` 命令填补了“编辑器撤销”和“Git 提交”之间的巨大空白。它允许你以极低的成本、极高的频率保存你的工作进度，而不会污染 Git 的主提交历史。你可以把它看作是一个拥有无限历史记录的“存盘点”。
---
## 🧭 导航命令

当历史记录出现分支时，这些命令允许你像在浏览器中前进/后退一样，在历史图谱中轻松穿梭，而无需手动复制哈希值。

| 命令 | 描述 | 示例 |
| :--- | :--- | :--- |
| `axon undo` | 移动到当前节点的**父节点** (类似 Ctrl+Z)。 | `axon undo -n 2` (向上移动2次) |
| `axon redo` | 移动到当前节点的**子节点** (类似 Ctrl+Y)。 | `axon redo` |
| `axon prev` | 在兄弟分支间，切换到**上一个 (更旧的)** 分支。 | `axon prev` |
| `axon next` | 在兄弟分支间，切换到**下一个 (更新的)** 分支。 | `axon next` |

## 📺 交互式界面

### `ui` - 启动 TUI 历史浏览器

提供一个全屏的、可视化的界面来浏览和操作历史图谱。

```bash
axon ui
```

*   **视图**: 类似于 `git log --graph` 的垂直时间轴，清晰展示主干与分支。
*   **高亮**: 启动时自动高亮当前工作区所处的状态。
*   **操作**:
    *   使用 `↑` / `↓` 方向键选择节点。
    *   按 `Enter` 或 `c` 键检出 (checkout) 到选中节点。
    *   按 `h` 键切换显示/隐藏与当前分支无关的节点。
    *   按 `q` 键退出。
~~~~~

### 3. 更新开发者文档

说明插件的加载优先级。

~~~~~act
replace
~~~~~
~~~~~path
docs/05_developer_guide/02_adding_new_acts.md
~~~~~
~~~~~old_string
# 🔌 开发自定义 Act

Axon 支持插件系统。你可以通过添加 `.py` 文件来扩展指令集。
~~~~~
~~~~~new_string
# 🔌 开发自定义 Act

Axon 支持插件系统。你可以通过添加 `.py` 文件来扩展指令集。

## 插件加载路径

Axon 按以下优先级顺序加载插件 (高优先级覆盖低优先级):

1.  **项目插件 (Project)**: `PROJECT_ROOT/.axon/acts/`
    *   最高优先级。定义项目专属、应由团队共享的指令。Axon 会从当前目录向上查找 `.git` 来确定项目根目录。
2.  **环境变量插件 (Env)**: `$AXON_EXTRA_ACTS_DIR`
    *   用于指定公司内部共享的插件库等。
3.  **用户全局插件 (User)**: `~/.axon/acts/`
    *   最低优先级。用于存放您个人的、跨项目通用的自定义指令。
~~~~~

### 4. 更新 TODO 列表

将已完成的功能标记掉。

~~~~~act
replace
~~~~~
~~~~~path
TODO.md
~~~~~
~~~~~old_string
### ✅ 阶段 3: 用户体验与核心功能 (已完成)

当核心循环跑通后，我们将添加让用户能够与历史图谱交互的核心功能。

*   [x] **历史查看 (`axon log`)**
    *   [x] 实现一个新的 CLI 命令 `axon log`，用于列出 `.axon/history` 中的所有节点。
*   [x] **时间旅行 (`axon checkout`)**
    *   [x] 实现 CLI 命令 `axon checkout <node_hash>`。
    *   [x] 在 `GitDB` 中添加 `checkout_tree(tree_hash)` 方法，用于将工作区硬重置到指定状态。
*   [x] **工作区重置 (`axon discard`)**
    *   [x] 实现 `axon discard` 命令，用于一键恢复到上一个干净状态，清理失败 Plan 留下的变更。
*   [x] **分布式协作 (`axon sync`)**
    *   [x] 实现 `axon sync` 命令，用于 `git push/pull` `refs/axon/history` 引用。
*   [x] **CLI 图导航 (`undo`, `redo`, `prev`, `next`)**
    *   [x] 实现快捷命令，允许在历史图谱中进行相对移动。
*   [x] **交互式 TUI (`axon ui`)**
    *   [x] 集成 Textual，提供一个可视化的历史浏览器和检出工具。

---

### 🛠️ 阶段 4: 健壮性与打磨

让 Axon 从一个原型变成一个可靠的工具。

*   [ ] **完善错误处理**：
    *   [x] 处理 `git` 未安装或工作目录非 Git 仓库的情况。
    *   [x] 在文件操作中处理权限问题 (`PermissionError`)。
    *   [ ] 细化 Plan 执行失败时的错误报告。
*   [x] **配置系统**：实现 `core/config_manager.py` 以加载 `.axon/config.yml`，并集成了第一个配置项 (`sync.remote_name`)。
*   [ ] **文档更新**：更新 `README.md` 和 `PROMPT.md`，反映 v4.2 的新概念和工作流。
*   [ ] **打包与分发**：为 `pip` 发布做准备。
~~~~~
~~~~~new_string
### ✅ 阶段 3: 用户体验与核心功能 (已完成)

当核心循环跑通后，我们将添加让用户能够与历史图谱交互的核心功能。

*   [x] **历史查看 (`axon log`)**
    *   [x] 实现一个新的 CLI 命令 `axon log`，用于列出 `.axon/history` 中的所有节点。
*   [x] **时间旅行 (`axon checkout`)**
    *   [x] 实现 CLI 命令 `axon checkout <node_hash>`。
    *   [x] 在 `GitDB` 中添加 `checkout_tree(tree_hash)` 方法，用于将工作区硬重置到指定状态。
*   [x] **工作区重置 (`axon discard`)**
    *   [x] 实现 `axon discard` 命令，用于一键恢复到上一个干净状态，清理失败 Plan 留下的变更。
*   [x] **分布式协作 (`axon sync`)**
    *   [x] 实现 `axon sync` 命令，用于 `git push/pull` `refs/axon/history` 引用。
*   [x] **CLI 图导航 (`undo`, `redo`, `prev`, `next`)**
    *   [x] 实现快捷命令，允许在历史图谱中进行相对移动。
*   [x] **交互式 TUI (`axon ui`)**
    *   [x] 集成 Textual，提供一个可视化的、类似 `git log --graph` 的历史浏览器。

---

### 🛠️ 阶段 4: 健壮性与打磨

让 Axon 从一个原型变成一个可靠的工具。

*   [x] **完善错误处理**：
    *   [x] 处理 `git` 未安装或工作目录非 Git 仓库的情况。
    *   [x] 在文件操作中处理权限问题 (`PermissionError`)。
    *   [ ] 细化 Plan 执行失败时的错误报告。
*   [x] **配置系统**：实现 `core/config_manager.py` 以加载 `.axon/config.yml`，并集成了第一个配置项 (`sync.remote_name`)。
*   [x] **文档更新**：更新 `README.md` 和 `docs/` 目录，反映 v4.3 的新概念和工作流。
*   [ ] **打包与分发**：为 `pip` 发布做准备。
~~~~~

### 5. 创建最终提交

~~~~~act
git_add
~~~~~
~~~~~files
docs/03_user_guide/01_core_concepts.md
docs/03_user_guide/02_cli_reference.md
docs/05_developer_guide/02_adding_new_acts.md
TODO.md
~~~~~

~~~~~act
git_commit
~~~~~
~~~~~message
Docs: Update documentation for v4.3 features

- Updated Core Concepts to explain the Event-based Timeline and Idempotent Nodes.
- Rewrote the CLI Reference to include new commands: `save`, `discard`, `sync`, `undo`, `redo`, `prev`, `next`.
- Updated the `ui` command documentation to reflect the new `git-log` style graph view and its features.
- Added plugin loading path priorities to the developer guide.
- Marked Phase 3 as complete in the TODO roadmap.
~~~~~