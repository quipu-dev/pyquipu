好的，代码已经通过测试，现在我们将创建一个符合规范的 `[COMMIT]` 计划来持久化这些变更。

## [COMMIT] feat(cli): 为 log 和 export 添加过滤功能

### 用户需求
1.  为 `quipu log` 和 `quipu export` 命令添加 `--since`, `--until`, `--limit` 过滤选项。
2.  为这两个命令添加 `--reachable-only` 选项，以仅显示/导出与当前工作区状态相关的历史节点。
3.  在实现过程中遵循 DRY 原则，将共享的过滤逻辑提取到公共辅助函数中。

### 评论
这次重构和功能增强显著提升了 `quipu` CLI 的可用性。用户现在可以精确地查询和导出他们关心的历史子集，特别是在处理复杂和多分枝的历史图谱时，`--reachable-only` 功能提供了一个强大的聚焦工具。将过滤逻辑抽象为公共辅助函数也提高了代码的可维护性。

### 目标
1.  已在 `pyquipu.cli.commands.helpers` 中创建 `filter_nodes` 和 `filter_reachable_nodes` 两个公共辅助函数。
2.  已重构 `export.py` 和 `query.py` 以使用这些辅助函数，并添加了相应的 Typer 选项。
3.  已更新 `tests/cli/test_export_command.py` 和 `tests/cli/test_query_commands.py` 以覆盖新的过滤功能。
4.  创建一个 Git 提交，将这些改进固化到代码库中。

### 基本原理
通过将过滤逻辑（时间范围、数量限制、可达性分析）从具体的命令实现中解耦出来，并放入 `helpers.py` 模块，我们实现了代码的复用。`export` 和 `log` 命令现在都作为这些公共函数的前端调用者，各自处理自己的输出格式化，而核心的过滤算法则由共享模块统一提供。这使得未来的维护（例如，修复时间戳解析的 bug）只需要在一个地方进行。

### 标签
#intent/build #flow/ready #priority/high #comp/cli #concept/history #scope/ux #scope/dx #ai/instruct #task/domain/cli #task/object/log-command #task/action/feature-enhancement #task/state/end #task/status/completed

---

### Script

#### Acts 1: 提交所有相关的变更

我们将把所有修改过的 CLI 命令文件、辅助函数文件以及对应的测试文件都添加到暂存区，然后创建一个原子提交。

~~~~~act
git_add
packages/quipu-cli/src/pyquipu/cli/commands/helpers.py
packages/quipu-cli/src/pyquipu/cli/commands/export.py
packages/quipu-cli/src/pyquipu/cli/commands/query.py
tests/cli/test_export_command.py
tests/cli/test_query_commands.py
~~~~~

~~~~~act
git_commit
~~~~~
~~~~~text
feat(cli): add filtering capabilities to log and export commands

This commit introduces advanced filtering options to the `quipu log` and `quipu export` commands, significantly improving their usability for large and complex histories.

Key changes include:
- **Shared Filtering Logic**: Refactored the filtering logic into common helper functions (`filter_nodes`, `filter_reachable_nodes`) in `helpers.py` to adhere to the DRY principle.

- **Time and Limit Filters**: Both `log` and `export` now support `--since`, `--until`, and `--limit` options, allowing users to select specific time ranges or result counts.

- **Reachable-Only Filter**: A new `--reachable-only` flag has been added to both commands. When enabled, it displays only the nodes that are direct ancestors or descendants of the current workspace state (HEAD), effectively hiding unrelated branches.

- **Updated Tests**: Added comprehensive tests to verify the correctness of all new filtering mechanisms for both commands.
~~~~~

### 下一步建议
- **UI 集成**: 我们现在可以在 `quipu ui` 中利用 `filter_reachable_nodes` 的逻辑，添加一个快捷键（例如 `t`）来动态地显示/隐藏不可达的分支。
- **性能评估**: 对于超大规模的历史库，可以考虑在 `SQLite` 后端为可达性分析添加索引或缓存，以优化性能。
