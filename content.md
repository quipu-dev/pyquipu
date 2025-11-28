好的，我们将把这两次修复合并为一个逻辑提交，以完成“统一输出流”这个宏观任务。

## [COMMIT] fix(cli): 统一 CLI 命令的数据输出到 stdout

### 用户需求
所有输出数据的 Quipu 命令（如 `log`, `find`, `axon --list-acts`）都应将其核心数据结果输出到标准输出 (`stdout`)，同时将元信息和日志输出到标准错误 (`stderr`)，以支持标准的 Unix 管道操作。

### 评论
这是一个关键的开发者体验 (DX) 修复。通过使 Quipu CLI 的行为与 Unix 哲学保持一致，我们极大地增强了它在自动化脚本和命令行工作流中的可组合性和实用性，使其成为一个行为良好且可预测的工具。

### 目标
1.  已将 `query.py`, `axon.py` 和 `run.py` 中负责打印核心数据（节点列表、指令列表）的 `typer` 调用修改为输出到 `stdout`。
2.  确保了所有标题和元信息的输出调用仍然保留 `err=True` 参数，定向到 `stderr`。
3.  创建一个 Git 提交，将这一系列改进作为一个原子单元进行持久化，正式结束此项重构任务。

### 基本原理
通过在整个 CLI 工具集中严格区分数据流 (`stdout`) 和元信息/日志流 (`stderr`)，我们遵循了命令行工具设计的最佳实践。这使得用户可以依赖标准 shell 功能（如 `|` 和 `>`）来处理 Quipu 的输出，而不会混入不相关的日志信息。

### 标签
#intent/fix #flow/ready #priority/medium #comp/cli #concept/ui #scope/dx #scope/ux #ai/instruct #task/domain/cli #task/object/output-streams #task/action/refactor #task/state/end #task/status/completed

---

### Script

#### Acts 1: 提交所有输出流相关的修复

我们将把所有修改过的文件添加到 Git 暂存区，并创建一个清晰的提交，标志着此项任务的完成。

~~~~~act
git_add
~~~~~
~~~~~text
packages/quipu-cli/src/quipu/cli/commands/query.py
packages/quipu-cli/src/quipu/cli/commands/axon.py
packages/quipu-cli/src/quipu/cli/commands/run.py
~~~~~

~~~~~act
git_commit
~~~~~
~~~~~text
fix(cli): unify command data output to stdout

Redirects the data output of commands like 'log', 'find', and '--list-acts' to stdout, while keeping metadata and progress on stderr.

Previously, all output was sent to stderr, preventing the use of standard shell pipelines with tools like 'grep', 'awk', or 'less'. This change aligns the entire CLI's behavior with standard Unix practices.

Now, only informational headers and prompts are sent to stderr, while the actual data is sent to stdout, making the commands composable and script-friendly.
~~~~~

### 下一步建议
现在 Quipu CLI 的文本输出已经变得干净且可预测，下一步可以考虑为其增加机器可读的输出格式，以进一步增强其在自动化流程中的能力。

我建议为 `log` 和 `find` 等命令增加一个 `--json` 标志，当启用时，将结果以 JSON 格式输出到 `stdout`。这将使其能够被其他程序轻松解析和使用。
