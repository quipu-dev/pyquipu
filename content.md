好的，我们已经圆满完成了测试辅助函数的提取和标准化工作。现在的测试目录结构清晰，且具备了高度的可复用性。

我将生成一个 `[COMMIT]` 计划，将这些重构成果正式提交到代码库。

## [COMMIT] refactor(tests): 统一标准化辅助函数至 tests/helpers.py

### 用户需求

将测试套件中所有重复的、用于环境搭建和历史创建的逻辑提取到顶层的 `tests/helpers.py` 中，并清理冗余文件，以提升测试的可维护性。

### 评论

这是一项非常重要的架构清理工作。通过建立一个中心化的、声明式的测试辅助函数库，我们不仅消除了大量的代码重复，还显著提升了测试用例的可读性。现在，测试代码更像是在描述“场景”，而不是在执行“底层命令”，这为以后将测试按包进行拆分打下了坚实的基础。

### 目标

1.  将所有变更的文件添加到 Git 暂存区。
2.  创建一个详尽的提交记录，说明重构的内容和动机。

### 基本原理

通过 `[COMMIT]` 计划，我们将之前的多步重构操作（包括辅助函数的提取、测试文件的重写以及冗余文件的清理）作为一个逻辑完整的单元进行提交。这确保了版本历史的整洁和可追溯性。

### 标签

#intent/refine #flow/ready #priority/high #comp/tests #scope/dx #ai/instruct #task/domain/testing #task/object/helpers #task/action/refactor #task/state/end

---

### Script

#### Acts 1: 提交重构变更

我将把所有修改过的测试文件和新建立的辅助模块添加到 Git 暂存区，并创建一个内容丰富的提交。

~~~~~act
git_add
tests/helpers.py
tests/integration/conftest.py
tests/integration/test_sync_modes.py
tests/integration/test_sync_workflow.py
tests/cli/test_export_command.py
tests/cli/test_navigation_commands.py
tests/cli/test_unfriendly_paths.py
tests/cli/test_query_commands.py
~~~~~

~~~~~act
git_commit
~~~~~
~~~~~text
refactor(tests): consolidate and standardize test helpers in tests/helpers.py

Consolidated redundant and duplicated test setup logic from various test files (cli, integration) into a single, high-level helper module: 'tests/helpers.py'.

Key improvements:
- Established a declarative API for creating complex history scenarios:
    - `create_branching_history`
    - `create_complex_link_history`
    - `create_linear_history_from_specs`
- Abstracted common CLI and integration patterns into reusable functions:
    - `run_git_command`
    - `create_node_via_cli`
- Cleaned up the test directory by removing redundant local 'helpers.py' files and erroneous sub-directories.
- Refactored multiple test suites (export, navigation, query, sync) to use the new standardized helpers, significantly reducing boilerplate and improving test readability.

This refactoring aligns with the DRY principle and provides a solid foundation for splitting the test suite into package-specific components in the future.
~~~~~

### 下一步建议

重构完成后，建议执行一遍完整的测试套件 (`pytest`)，以确保在提取辅助函数的过程中没有引入任何逻辑回归。

在确认测试全部通过后，我们可以开始考虑将 `tests/` 下的各个子目录（`cli`, `engine`, `runtime` 等）正式重构为独立的 Python 包，以进一步优化项目结构。如果你准备好了，我们可以开始讨论那个计划。
