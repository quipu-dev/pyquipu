好的，测试已通过。我们现在将把 `query` 和 `show` 命令的重构工作，连同对测试的修复，一并提交，以固化这次的成果。

## [COMMIT] refactor(cli): 迁移 query 和 show 命令至 MessageBus

### 用户需求
将 `quipu query` 和 `quipu show` 两个子命令的输出逻辑，从硬编码的 `typer` 调用迁移到 `MessageBus` 系统。此过程包括分离数据流 (`stdout`) 和元信息流 (`stderr`)，更新消息资源文件，并重构相关测试以使用模拟技术进行意图验证。

### 评论
这次重构是 `MessageBus` 推广计划中的一次成功迭代。它不仅推进了代码库的健康度，更重要的是，通过解决 `stdout`/`stderr` 的分离问题，让 `Quipu` 的核心查询功能成为了一个“行为良好”的 Unix 命令行公民，极大地增强了其在自动化脚本和管道操作中的实用性。修复测试逻辑中的顺序错误也证明了新测试模式的价值——它迫使我们更精确地定义和验证应用的行为。

### 目标
1.  **命令重构**：`query.py` 和 `show.py` 已完全使用 `MessageBus` 进行输出，代码意图更加清晰。
2.  **流分离**：成功将数据输出 (`bus.data()`) 定向到 `stdout`，元信息 (`bus.info()`, `bus.error()`) 定向到 `stderr`。
3.  **内容外部化**：所有相关的消息文本都已提取到 `locales/zh/cli.json`。
4.  **测试健壮性**：`test_query_commands.py` 已完全重构为使用模拟 `bus` 的方式，并且修复了一个关键的逻辑顺序断言，使测试与实现行为精确对齐。

### 基本原理
我们继续遵循“依赖倒置”原则，将输出实现从命令逻辑中解耦。关键的实践是区分了两种输出类型：**数据**和**元信息**。通过分别调用 `bus.data()` 和 `bus.info()` 等方法，`MessageBus` 的 `TyperRenderer` 能够智能地将它们路由到正确的输出流（`stdout` 和 `stderr`）。

在测试中，我们通过模拟 `bus` 对象，可以精确断言 `data` 方法被哪些内容调用，`info` 方法被哪个消息 ID 调用，从而在不依赖具体输出格式的情况下，验证了命令的逻辑正确性，包括数据输出的顺序。

### 标签
#intent/refine #flow/ready #priority/high #comp/cli #comp/tests #concept/ui #scope/dx #scope/ux #ai/instruct #task/domain/ui #task/object/message-bus #task/action/implementation #task/state/continue

---

### Script

#### Acts 1: 将所有相关的变更添加到暂存区

我们将所有修改过的文件添加到 Git 暂存区。

~~~~~act
git_add
packages/quipu-cli/src/quipu/cli/commands/query.py
packages/quipu-cli/src/quipu/cli/commands/show.py
locales/zh/cli.json
tests/cli/test_query_commands.py
~~~~~

#### Acts 2: 创建 Git 提交

现在，我们创建一个内容详尽的提交，记录本次重构的所有工作。

~~~~~act
git_commit
~~~~~
~~~~~text
refactor(cli): migrate query and show commands to MessageBus

Continues the adoption of the MessageBus architecture by refactoring the `query` and `show` commands.

Key changes:
- All user-facing output in `query.py` and `show.py` now uses the central `bus` instance.
- Data output (e.g., node lists) is correctly routed to stdout via `bus.data()`, enabling shell piping with tools like `grep`. Metadata remains on stderr.
- All associated message strings have been externalized to `locales/zh/cli.json`.
- Tests in `test_query_commands.py` are refactored to use mocking.
- Fixed an assertion order bug in `test_log_output` to correctly reflect the reverse chronological order of the `log` command, making the test more accurate.
~~~~~

### 下一步建议
我们已经成功重构了所有只读命令。现在是时候处理一些带有副作用但逻辑相对简单的命令了。

根据我们之前制定的路线图，下一个理想的目标是 `cache` 命令 (`cache sync` 和 `cache rebuild`)。这将让我们在处理文件系统交互（删除/创建数据库）的场景下，继续应用和巩固 `MessageBus` 的重构模式。

如果你同意，我将开始准备重构 `cache` 命令的计划。
