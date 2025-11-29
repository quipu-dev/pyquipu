好的，我们已经成功地重构了 `export` 命令，修复了引入的 bug，并恢复了完整的测试覆盖。现在，是时候将这项工作作为一个完整的、健壮的逻辑单元提交了。

## [COMMIT] feat(cli): enhance export command with fine-grained link control

### 用户需求
将 `quipu export` 命令的功能从简单的布尔标志 (`--no-branch-link`) 升级为一个更强大、可重复使用的 `--hide-link-type` 选项，允许用户精确控制要禁用哪些类型的导航链接（如 `summary`, `branch`, `parent`, `child`）。

### 评论
这是一个重要的功能演进。它不仅为高级用户提供了强大的灵活性，使 `export` 成为一个更专业的文档生成工具，而且通过统一的接口 (`--hide-link-type`) 替代了未来可能出现的多个 `--no-*` 标志，保持了 CLI 的整洁和可扩展性。

### 目标
1.  已将 `export.py` 中的 `--no-branch-link` 选项重构为可接受多个值的 `--hide-link-type` 选项。
2.  已修复重构过程中引入的 `NameError` bug。
3.  已将 `test_export_command.py` 完全重写，不仅为新功能添加了健壮的参数化测试，还恢复并整合了之前被意外覆盖的旧测试用例，确保了完整的测试覆盖率。
4.  创建一个高质量的 Git 提交，将此项功能增强永久记录下来。

### 基本原理
我们利用了 Typer 处理可重复选项的能力，将用户输入的多个 `--hide-link-type` 值收集到一个集合中。这个集合被传递给 `_generate_navbar` 函数，该函数现在使用简单的条件逻辑来跳过渲染被禁用的链接类型。测试套件的全面重构确保了这一新逻辑在各种场景下都能正确工作，并且没有破坏任何现有功能。

### 标签
#intent/build #intent/refine #flow/ready #priority/medium #comp/cli #comp/tests #concept/navigation #scope/api #scope/ux #ai/brainstorm #task/domain/cli #task/object/export-command #task/action/feature-enhancement #task/state/end #task/status/completed

---

### Script

#### Acts 1: 提交功能增强和测试重构

现在，我们将所有相关的修改添加到 Git 暂存区，并创建一个内容详尽的提交。

~~~~~act
git_add
packages/quipu-cli/src/quipu/cli/commands/export.py
tests/cli/test_export_command.py
~~~~~

~~~~~act
git_commit
~~~~~
~~~~~text
feat(cli): enhance export command with fine-grained link control

This commit refactors the `quipu export` command to provide more granular control over the navigation links in exported Markdown files.

The previous `--no-branch-link` flag has been removed and replaced by a more flexible, repeatable `--hide-link-type` option. This new option can be used multiple times to disable specific categories of links.

Supported link types for hiding are:
- `summary`: Links to ancestor summary (idempotent) nodes.
- `branch`: Links to the nearest ancestor branch point.
- `parent`: Links to the direct parent node.
- `child`: Links to direct child nodes.

This change enhances the utility of the export command for users who need to generate cleaner, more focused documentation for specific review purposes.

Additionally, the test suite for this command (`test_export_command.py`) has been significantly refactored. It now uses a more comprehensive fixture and parameterized tests to robustly validate the new functionality, while also restoring previously lost test cases for filtering and edge-case handling, ensuring full test coverage.
~~~~~

### 下一步建议
- **更新文档**: 我们应该更新项目的 `README.md` 或相关文档，详细说明 `quipu export` 命令的这个新功能及其可用选项。
- **探索新链接类型**: 未来可以考虑为导航栏增加更多类型的链接（例如，兄弟节点 `sibling`），并将它们也纳入 `--hide-link-type` 的控制范围。
