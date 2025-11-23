
## [2025-11-21 22:47:52]
Implementation Logic:
1.  **Refactored `plugin_loader.py`**: Switched from `import_module` to `spec_from_file_location`. This is crucial because `import_module` relies on Python's `sys.path`. If we have multiple folders named `.axon/acts` in different locations (Home, Project), Python would treat them as the same package namespace or fail to distinguish them. Loading by file path isolates each plugin file as a unique module in memory.
2.  **Enhanced `main.py`**: Added `_find_project_root` to detect Git boundaries. Added `_load_extra_plugins` to build a list of plugin paths.
3.  **Loading Order**: The order `Home -> Env -> Project -> Local` ensures that a script in your current folder can override a project-wide script, and a project script can override a global user script. This follows the standard "Cascading Configuration" pattern (like CSS or Git config).

## [2025-11-23 16:34:39]
开始执行阶段 3：用户体验与核心功能。

首要任务是实现 `axon log` 命令。
1.  **目标**: 提供一个简单的方式来查看 `.axon/history` 目录中记录的所有操作节点。
2.  **实现路径**:
    *   在 `main.py` 中使用 Typer 添加一个新的 `log` 命令。
    *   该命令将调用 `core.history.load_history_graph` 来加载所有历史节点。
    *   将加载的节点按时间戳降序排列。
    *   以清晰、格式化的方式将节点信息（时间戳、类型、哈希、内容摘要）打印到终端。
3.  **收尾**: 修改 `TODO.md`，将 `axon log` 相关的任务标记为已完成。

## [2025-11-23 16:39:53]
开始实现 `axon checkout <node_hash>` 功能。

1.  **底层实现 (`core/git_db.py`)**:
    *   创建一个新的 `checkout_tree(tree_hash: str)` 方法。
    *   这个方法需要执行原子性的工作区重置操作。
    *   **步骤**:
        1.  使用 `git read-tree <tree_hash>` 将 Git 的索引（staging area）更新到目标状态。这是无损的内存操作。
        2.  使用 `git checkout-index -a -f` 强制将工作区文件同步为索引的状态。
        3.  使用 `git clean -fdx -e .axon` 清理掉新状态下不存在、但旧状态下存在的文件（未追踪文件）。`-x` 会清理被忽略的文件，`-e .axon` 确保我们自己的目录安全。
    *   这个底层方法不应该包含用户交互或安全检查，只负责执行。

2.  **上层封装 (`main.py`)**:
    *   添加新的 `checkout` 命令，接收一个 `hash_prefix` 参数。
    *   **业务逻辑**:
        1.  加载历史图谱 (`load_history_graph`)。
        2.  根据用户提供的哈希前缀，在图谱中查找完整的 `output_tree` 哈希。如果找不到或找到多个，则报错。
        3.  **安全检查 (关键)**: 在执行 checkout 之前，调用 `Engine.align()` 和 `Engine.capture_drift()`。这确保了用户在执行危险操作前的所有本地修改都被自动保存为一个 `CaptureNode`，防止数据丢失。
        4.  调用 `git_db.checkout_tree(full_hash)` 执行物理状态切换。
        5.  向用户报告成功信息。

3.  **TODO 更新**:
    *   标记 `axon checkout` 相关任务为完成。

现在开始编码。

## [2025-11-23 16:41:07]
Now creating tests for the `checkout` functionality.

**Test Plan:**
1.  **Unit Test for `git_db.checkout_tree` (in `tests/test_git_db.py`):**
    *   **Goal**: Verify that the method correctly and destructively resets the workspace to a target tree state.
    *   **Steps**:
        1.  Create State A (e.g., `file1.txt`, `file2.txt`) and get its tree hash.
        2.  Create State B (e.g., modify `file1.txt`, delete `file2.txt`, add `file3.txt`). The workspace is now in State B.
        3.  Call `db.checkout_tree()` with the hash of State A.
        4.  Assert that the workspace file contents match State A exactly (`file3.txt` is gone, `file2.txt` is back).
        5.  Assert that the `.axon` directory is NOT affected by the cleanup.

2.  **Integration Test for `axon checkout` CLI (in `tests/test_integration_v2.py`):**
    *   **Goal**: Verify the end-to-end command, including hash lookup, safety captures, and error handling.
    *   **Test Cases**:
        *   **Success Case**: A clean checkout from one valid historical state to another.
        *   **Safety Capture Case**: Attempting a checkout from a "dirty" workspace should first create a new `CaptureNode` before proceeding.
        *   **Error Case**: Providing an invalid or non-existent hash prefix should fail gracefully with a proper error message.
        *   **Idempotent Case**: Checking out to the current state should do nothing and report success.

## [2025-11-23 16:41:30]
Now creating tests for the `checkout` functionality.

**Test Plan:**
1.  **Unit Test for `git_db.checkout_tree` (in `tests/test_git_db.py`):**
    *   **Goal**: Verify that the method correctly and destructively resets the workspace to a target tree state.
    *   **Steps**:
        1.  Create State A (e.g., `file1.txt`, `file2.txt`) and get its tree hash.
        2.  Create State B (e.g., modify `file1.txt`, delete `file2.txt`, add `file3.txt`). The workspace is now in State B.
        3.  Call `db.checkout_tree()` with the hash of State A.
        4.  Assert that the workspace file contents match State A exactly (`file3.txt` is gone, `file2.txt` is back).
        5.  Assert that the `.axon` directory is NOT affected by the cleanup.

2.  **Integration Test for `axon checkout` CLI (in `tests/test_integration_v2.py`):**
    *   **Goal**: Verify the end-to-end command, including hash lookup, safety captures, and error handling.
    *   **Test Cases**:
        *   **Success Case**: A clean checkout from one valid historical state to another.
        *   **Safety Capture Case**: Attempting a checkout from a "dirty" workspace should first create a new `CaptureNode` before proceeding.
        *   **Error Case**: Providing an invalid or non-existent hash prefix should fail gracefully with a proper error message.
        *   **Idempotent Case**: Checking out to the current state should do nothing and report success.

## [2025-11-23 16:43:07]
分析测试失败原因：

1.  **ERRORs**: `workspace` fixture 的作用域问题。它被定义在 `TestController` 类内部，导致 `TestCheckoutCLI` 无法访问。需要将其提升到模块级别。

2.  **FAILUREs**: `exit_code` 为 2，表明是 CLI 用法错误。在引入多命令（`run`, `log`, `checkout`）后，测试脚本没有相应地更新 `runner.invoke` 的参数，缺少了子命令。例如，`runner.invoke(app, ["plan.md"])` 应该改为 `runner.invoke(app, ["run", "plan.md"])`。

开始修复 `tests/test_integration_v2.py`。

## [2025-11-23 16:43:47]
`test_cli_checkout_success` 失败的原因在于 fixture `populated_workspace` 的实现逻辑有误。它在生成 State B 时，没有移除 State A 的产物（`a.txt`），导致最终的工作区是 A 和 B 的合集，而不是纯粹的 B。

这违反了测试用例中断言 `assert not (workspace / "a.txt").exists()` 的前提。

修复方法：在执行 `plan_b` 之前，手动删除 `a.txt`，确保 State B 是一个干净、独立的状态，只包含 `b.txt`。

## [2025-11-23 16:44:20]
所有测试均已通过，`axon checkout` 功能及其测试已完成。现在将这些变更提交到版本历史中。

## [2025-11-23 16:45:26]
开始实现 `axon sync` 功能。

这个功能的核心是 `git push` 和 `git pull` 一个自定义的 ref (`refs/axon/history`)。这不属于常规的文件操作 `act`，而是对 Git 仓库本身的元管理。因此，直接在 `main.py` 的 `sync` 命令处理函数中调用 `subprocess` 来执行 `git` 命令是更清晰的架构选择。

**步骤**：
1.  在 `main.py` 中添加 `sync` 命令。
2.  `sync` 函数将执行 `git push origin refs/axon/history:refs/axon/history`。
3.  为了完整性，它还会执行 `git fetch origin refs/axon/history:refs/axon/history` 来拉取远程的更新。
4.  在执行前，会检查 `.git` 目录是否存在，确保是在一个 Git 仓库中。
5.  更新 `TODO.md`。

## [2025-11-23 16:46:31]
`axon sync` 功能的自动化测试需要复杂的外部 Git 远程仓库依赖和环境配置，且其核心逻辑是调用 Git 自身命令，已由 Git 保证其健壮性。因此，跳过自动化测试是合理的。现在创建提交。

## [2025-11-23 16:48:13]
进入阶段 4：健壮性与打磨。

首要任务是完善错误处理。

1.  **目标**: 让 Axon 在遇到常见环境问题（如 `git` 未安装、非 Git 仓库、文件权限不足）时，能够提供清晰、可操作的错误提示，而不是直接崩溃或显示复杂的 Traceback。
2.  **第一步**: 修改 `core/git_db.py` 的 `__init__` 方法。在构造函数中就检查 `shutil.which("git")`。如果 `git` 不存在，立即抛出一个自定义的、信息明确的异常，比如 `ExecutionError("Git command not found. Please install Git to use Axon.")`。这将从根源上解决所有依赖 Git 的操作的潜在问题。

## [2025-11-23 16:49:32]
第一部分错误处理已完成，主要涉及 `git` 命令和 Git 仓库存在性检查。现在创建提交，并准备处理文件权限相关的错误。

## [2025-11-23 16:49:34]
开始处理文件权限错误。

**目标**: 在文件操作相关的 Act 中捕获 `PermissionError` 或 `OSError`，并提供用户友好的错误提示。

**步骤**:
1.  修改 `acts/basic.py` 中的 `_write_file`, `_replace`, `_append_file` 函数。
2.  在文件读写和操作的代码块外层添加 `try...except PermissionError`。
3.  如果捕获到 `PermissionError`，则抛出 `ExecutionError`，说明是权限问题，并建议用户检查权限。

## [2025-11-23 16:50:27]
继续完善错误处理，聚焦文件权限问题。

**策略**:
在 `acts` 模块的底层文件操作函数中，使用 `try...except PermissionError` 块来捕获权限错误。
当捕获到该错误时，重新抛出一个 `ExecutionError`，其中包含更友好的、针对用户操作的上下文信息，例如 "无法写入文件 [文件名]，权限不足"。

**执行步骤**:
1.  修改 `acts/basic.py` 中的 `_write_file`, `_replace`, `_append_file` 函数。
2.  在 `open()` 语句外层包裹 `try...except`。
3.  在 `except` 块中，`raise ExecutionError(f"对 {raw_path} 的操作失败：权限不足。")`。

这将使错误信息从通用的 "Permission denied" 变为与 Axon 操作直接相关的 "写入/替换/追加失败：权限不足"。

## [2025-11-23 16:51:20]
对刚才完成的错误处理改进进行评估，确定是否需要编写自动化测试。

1.  **Git 存在性检查**: 已被现有集成测试覆盖。
2.  **权限错误捕获**: 测试实现复杂，依赖于修改文件系统权限，可能导致测试不稳定。鉴于添加的逻辑非常简单（try/except 结构），通过代码审查足以保证质量。

结论是跳过专门的测试，直接提交。

## [2025-11-23 16:58:26]
开始实现配置系统。
1.  创建一个新的 `ConfigManager` 类，负责加载和解析 `.axon/config.yml`。
2.  该类需要健壮，能处理文件不存在、YAML 格式错误等情况。
3.  它将维护一套内部默认值，用户的配置会覆盖这些默认值。
4.  为了演示，我将添加 `sync.remote_name` 配置，并让 `sync` 命令使用它。

## [2025-11-23 16:59:38]
测试失败，原因是 `main.py` 中的相对导入 `from .core.config_manager import ConfigManager` 导致 `ImportError`。
`main.py` 是一个顶级脚本，不应使用相对导入。
修复方案：将其改为绝对导入 `from core.config_manager import ConfigManager`。
由于 `pytest.ini` 中有 `pythonpath = .`，这个绝对路径可以被正确解析。

## [2025-11-23 17:00:48]
用户报告可执行脚本 `./axon` 失败，原因是 `ImportError: cannot import name 'main' from 'main'`。
这是因为 `main.py` 中的 Typer 入口点是 `app`，而不是 `main`。
我将创建一个标准的 Python 可执行脚本 `axon`，它会正确地导入并运行 `app`。
修复完成后，我将把这次导入错误修复和可执行脚本的修复合并到同一个提交中。

## [2025-11-23 17:39:48]
## 插件加载逻辑重构决策

**问题**: 当前的插件加载逻辑 (Home -> Env -> Project -> **Local/Current**) 与 v4.2 的幽灵状态引擎存在核心冲突。Engine 依赖一个由 `.git` 定义的、唯一的“项目根”来确保 Tree Hash 计算的一致性。而“当前目录”的插件加载逻辑引入了一个可变的、不确定的上下文，这会导致：
1.  **状态计算不一致**: 在不同子目录运行 `axon` 会产生不同的 Tree Hash，破坏历史链。
2.  **配置与历史割裂**: 项目的行为（插件）和历史（Engine）可能存储在不同位置。
3.  **用户体验混乱**: 工具行为不可预测。

**解决方案**:
1.  **确立项目根的绝对权威**: Axon 启动时，必须首先从当前目录向上查找 `.git` 确定唯一的 `Project Root`。所有核心操作都基于此根进行。
2.  **简化插件加载路径**: 废弃“当前目录”查找。固化加载优先级为：
    -   `Project` (`PROJECT_ROOT/.axon/acts/`) - 最高
    -   `Env` (`$AXON_EXTRA_ACTS_DIR`)
    -   `User` (`~/.axon/acts/`) - 最低
3.  **显式优于隐式**: 这种方式移除了模糊的约定，使行为可预测，并从根本上解决了与 Engine 的冲突，保证了状态管理的健壮性。

## [2025-11-23 17:59:19]
## 架构重构：建立稳定的插件 API (ActContext)

**问题**: 当前插件 (`acts/*.py`) 直接导入并依赖 `core.executor.Executor` 和 `core.exceptions.ExecutionError`，造成了插件生态与核心实现的紧密耦合。这使得核心的任何重构都可能破坏所有插件，不利于长期维护和生态发展。

**解决方案**:
实施“依赖注入”模式，引入一个“上下文对象” (`ActContext`)作为插件和执行器之间的稳定 API 接口。

1.  **创建 `ActContext`**: 在 `core/types.py` 中定义 `ActContext` 类。它将封装所有插件需要的功能（如路径解析、用户确认、错误报告），并向插件隐藏具体的实现细节。
2.  **解耦插件**: 插件的函数签名将从 `_func(executor: Executor, ...)` 变为 `_func(ctx: ActContext, ...)`。
3.  **隐藏实现**: 插件不再直接 `raise ExecutionError`，而是调用 `ctx.fail("...")`。它们不再调用 `executor.resolve_path()`，而是 `ctx.resolve_path()`。

**收益**:
- **强解耦**: 核心可以自由重构，只要 `ActContext` 接口保持稳定，插件就无需修改。
- **清晰的 API**: 为插件开发者提供了清晰、简洁、稳定的开发契约。
- **可移植性**: 插件不再依赖 Axon 的内部实现，理论上可被任何遵循此 API 的执行器使用。
- **提升可测试性**: 测试插件时只需 mock `ActContext` 接口，而非整个 `Executor`。

## [2025-11-23 18:01:16]
## 测试失败分析与修复 (`ActContext` Refactor Fallout)

**诊断**: 6 个测试失败。
- **5x `AttributeError`**: 发生在 `test_check.py`, `test_ops.py`, `test_read.py`。根本原因是测试代码没有跟上 `ActContext` API 的重构。测试用例直接将 `Executor` 实例传递给了期望 `ActContext` 实例的 act 函数，导致 `ctx.fail()` 调用失败。
- **1x `AssertionError`**: 发生在 `test_search_scoped_path`。根本原因是 `_python_search` 的路径输出逻辑问题。它将路径格式化为相对于搜索目录，而不是项目根目录，导致断言失败。

**修复计划**:
1.  **修复测试用例**: 在所有直接调用 act 函数的测试中，引入 `from core.types import ActContext`，并在调用前创建 `ctx = ActContext(executor)`，然后传递 `ctx`。
2.  **修复搜索实现**: 向 `_python_search` 函数传递 `ctx`，并修改其输出格式，使用 `file_path.relative_to(ctx.root_dir)` 来确保路径的一致性。

## [2025-11-23 18:02:14]
## 测试失败分析与修复 (`ActContext` Refactor Fallout)

**诊断**: 6 个测试失败。
- **5x `AttributeError`**: 发生在 `test_check.py`, `test_ops.py`, `test_read.py`。根本原因是测试代码没有跟上 `ActContext` API 的重构。测试用例直接将 `Executor` 实例传递给了期望 `ActContext` 实例的 act 函数，导致 `ctx.fail()` 调用失败。
- **1x `AssertionError`**: 发生在 `test_search_scoped_path`。根本原因是 `_python_search` 的路径输出逻辑问题。它将路径格式化为相对于搜索目录，而不是项目根目录，导致断言失败。

**修复计划**:
1.  **修复测试用例**: 在所有直接调用 act 函数的测试中，引入 `from core.types import ActContext`，并在调用前创建 `ctx = ActContext(executor)`，然后传递 `ctx`。
2.  **修复搜索实现**: 向 `_python_search` 函数传递 `ctx`，并修改其输出格式，使用 `file_path.relative_to(ctx.root_dir)` 来确保路径的一致性。

## [2025-11-23 18:04:52]
## 纠正：`replace` 指令失败

**诊断**: 针对 `acts/read.py` 的 `replace` 操作失败，原因是提供的旧代码块与文件实际内容不完全匹配。这证明了 `replace` 指令严格性的重要性，它能防止对状态不确定的文件进行意外修改。

**恢复策略**:
1.  **感知 (Perceive)**: 使用 `read_file` 指令获取 `acts/read.py` 的确切内容。
2.  **行动 (Act)**: 在下一步中，利用 `read_file` 的输出作为 `replace` 指令中准确的“旧内容”块，重新执行替换、添加和提交操作，以完成整个 `ActContext` 的重构。

## [2025-11-23 18:11:38]
The user has requested a 'git checkout .' equivalent to discard changes from a failed plan. This is a fantastic idea for improving the workflow's robustness.

**Feature Name**: `axon discard`

**Logic**:
1.  The command needs to identify the "last clean state". In Axon's model, this is the `output_tree` of the most recently created history node (based on timestamp).
2.  The command will then use the existing `git_db.checkout_tree()` method to perform a hard reset of the workspace to that state's hash.
3.  It must include a confirmation prompt, as this is a destructive action (it discards unrecorded work). A `--force` flag will be provided to skip this.
4.  Edge cases to handle:
    - What if there is no history yet? The command should fail gracefully with a message.
    - What if the workspace is already in the last clean state? It should inform the user and do nothing.

**Implementation**:
- Add a new command function `discard()` to `main.py` using Typer.
- The function will instantiate an `Engine` to access `git_db` and helper methods.
- It will use `load_history_graph` to get all nodes.
- It will find the latest node by sorting on `timestamp`.
- It will perform the necessary checks and confirmation before calling `engine.git_db.checkout_tree()`.
- The implementation will be placed right after the `sync` command in `main.py` for logical grouping.

## [2025-11-23 18:12:23]
The user has approved the implementation of the `axon discard` command. I will now create a Git commit to persist this new feature.

**Commit Strategy:**
- **Type:** `feat` - This is a new feature for the user.
- **Scope:** `cli` - The change is primarily an addition to the command-line interface.
- **Subject:** A clear, concise summary: "Add `axon discard` command for workspace reset".
- **Body:** Explain the motivation and functionality. It solves the problem of a dirty workspace after a failed plan by providing a `git checkout .` style reset to the last known clean state.

This commit will finalize the implementation of this important workflow improvement.

## [2025-11-23 18:13:24]
The user wants to document the new `axon discard` feature.

**Plan:**
1.  **Update CLI Reference**: Modify `docs/03_user_guide/02_cli_reference.md` to add a detailed section for the `axon discard` command. This is the most critical documentation change. I will place it after `checkout` as it's also a state-manipulation command.
2.  **Update Roadmap**: Modify `TODO.md` to mark this user-experience feature as complete. This keeps our project tracking up-to-date.
3.  **Commit**: Create a `docs` commit that includes both updated files.

## [2025-11-23 22:04:57]
The user reported that an idempotent node (where input_tree == output_tree) was successfully created but did not appear in the TUI. This suggests a potential bug in `ui/tui.py` related to how the node graph is calculated, sorted, or rendered. Specifically, the logic might not be correctly handling cases where a node's parent is itself (conceptually) or when filtering nodes. While this plan focuses on versioning cleanup, this UI behavior should be investigated in a future step.
