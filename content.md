好的，所有测试都已通过。我们已经成功修复了因底层接口重构而导致的整个测试套件的失败。现在是时候将这些修复工作作为一个原子单元提交到版本控制中了。

我将生成一个 `[COMMIT]` 计划来完成这项工作。

## [COMMIT] fix(tests): 修复测试套件以适配新的存储接口和二进制数据流

### 用户需求
将最近为修复测试套件所做的所有更改（包括接口实现、类型导入和逻辑断言更新）提交到 Git 仓库，并撰写一条清晰的提交信息，说明修复的原因和内容。

### 评论
这次对测试套件的修复是底层存储接口重构工作的最后一步，也是至关重要的一步。一个健康的、全绿的测试套件是我们未来进行更复杂功能开发和重构的信心保证。

### 目标
1.  将所有已修改的测试文件和引擎代码文件添加到 Git 暂存区。
2.  创建一个符合 Conventional Commits 规范的 Git 提交，清晰地记录本次修复工作。

### 基本原理
通过一个原子提交来封装所有与本次修复相关的更改，可以确保版本历史的清晰和可追溯性。提交信息将详细解释失败的根本原因（接口变更和数据格式变更）以及相应的修复策略，为未来的代码审查和维护提供上下文。

### 标签
#intent/fix #flow/ready #priority/high #comp/tests #comp/engine #scope/core #ai/instruct #task/domain/testing #task/object/test-suite #task/action/bug-fix #task/state/end #task/status/completed

---

### Script

#### Acts 1: 将所有相关的修复提交到版本控制

我们将把所有修改过的文件添加到暂存区，并创建一个内容详尽的提交。

~~~~~act
git_add
tests/engine/test_engine_memory.py
tests/cli/test_view_model.py
packages/quipu-engine/src/quipu/core/git_object_storage.py
tests/engine/test_git_db.py
tests/helpers.py
~~~~~

~~~~~act
git_commit
~~~~~
~~~~~text
fix(tests): align test suite with new storage interface and binary data handling

This commit resolves a series of test failures that occurred after refactoring the HistoryReader interface and the underlying git_db data handling.

The failures were caused by two main issues:

1.  **Interface Mismatch (TypeError):**
    The `HistoryReader` abstract class introduced a new `get_node_blobs` method. Mock classes used in tests (`InMemoryHistoryManager`, `MockHistoryReader`) had not implemented this method, causing `TypeError` during test collection and setup. This has been fixed by adding a stub implementation to these classes in `tests/helpers.py` and `tests/cli/test_view_model.py`.

2.  **Behavioral Changes (AssertionError/KeyError):**
    The `git_db.cat_file` method was updated to return raw `bytes` instead of decoded text. Tests and reader logic that relied on the old text-based output failed.
    - Fixed a bug in `GitObjectHistoryReader` where a call to `cat_file` was missing the `object_type` argument.
    - Updated assertions in `test_git_db.py` to correctly handle and verify binary data from tree objects.

These changes restore the test suite to a fully passing state, validating the recent core refactoring work.
~~~~~

### 下一步建议
测试套件已经恢复健康。现在我们可以继续开发新功能了。根据我们的任务列表，下一步是实现 `quipu show` 命令，它将允许用户查看单个历史节点的详细信息。如果你同意，我将开始制定实现该功能的计划。
