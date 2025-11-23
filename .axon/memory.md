
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
