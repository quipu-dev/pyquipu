好的，测试已通过。现在我将生成一个 `[COMMIT]` 计划，将这次成功的重构作为一个原子单元提交到版本历史中。

## [COMMIT] refactor(cli): 集中用户确认逻辑到 ui_utils 模块

### 用户需求
在之前的步骤中，我们完成了对 `quipu-cli` 模块的重构，将分散的用户确认逻辑统一到了一个新的 `quipu.cli.ui_utils` 模块中，以解决代码重复和潜在的循环依赖问题。现在需要将这些已经过测试验证的变更提交到版本控制。

### 评论
这次重构是提升项目代码质量和可维护性的关键一步。通过建立一个单一、健壮的 UI 交互源头，我们确保了未来所有相关功能的行为一致性，并为开发者提供了一个清晰、标准的工具，避免了未来的实现分歧。

### 目标
1.  将所有相关的已修改和新建文件（`ui_utils.py`, `helpers.py`, `controller.py`, `cache.py`, `navigation.py`, `workspace.py`）添加到 Git 暂存区。
2.  创建一个符合 Conventional Commits 规范的 Git 提交，清晰地记录这次重构的目的和影响。

### 基本原理
通过一个原子性的 Git 提交，我们将这次架构改进固化下来。提交信息将详细说明重构前的“痛点”（代码重复、行为不一致、依赖问题）和重构后的“收益”（代码统一、架构清晰、可维护性增强），为未来的代码考古和维护提供清晰的上下文。

### 标签
#intent/refine #flow/ready #priority/high #comp/cli #concept/ui #scope/dx #ai/instruct #task/domain/cli #task/object/refactoring #task/action/dependency-resolution #task/state/end #task/status/completed

---

### Script

#### Acts 1: 暂存所有相关变更

我们将所有涉及本次重构的文件添加到 Git 的暂存区。

~~~~~act
git_add
~~~~~
~~~~~text
packages/quipu-cli/src/quipu/cli/ui_utils.py
packages/quipu-cli/src/quipu/cli/commands/helpers.py
packages/quipu-cli/src/quipu/cli/commands/cache.py
packages/quipu-cli/src/quipu/cli/commands/navigation.py
packages/quipu-cli/src/quipu/cli/commands/workspace.py
packages/quipu-cli/src/quipu/cli/controller.py
~~~~~

#### Acts 2: 创建 Git 提交

现在，我们创建一个内容详尽的提交，记录这次重构。

~~~~~act
git_commit
~~~~~
~~~~~text
refactor(cli): centralize user confirmation logic in ui_utils

Introduces a new `quipu.cli.ui_utils` module to consolidate all user confirmation logic into a single, robust `prompt_for_confirmation` function.

Previously, user confirmation logic was duplicated in `controller.py` (for the executor) and `commands/helpers.py` (for various commands). This led to inconsistent behavior, especially in non-interactive or piped environments, and created a potential for circular dependencies.

This refactor:
1. Creates `ui_utils.prompt_for_confirmation` as the single source of truth, using `click.getchar()` for reliable, non-buffered input.
2. Removes the duplicated logic from `controller.py` and `commands/helpers.py`.
3. Updates all call sites in the `commands` and `controller` modules to use the new unified function.

This resolves the architectural issue, eliminates code duplication, and ensures a consistent and robust user experience for all interactive prompts across the CLI.
~~~~~

### 下一步建议
- **代码整洁**: 既然我们已经创建了 `ui_utils`，可以考虑是否还有其他小的、通用的 UI 辅助函数（如特定的消息格式化器）可以被迁移到这个模块中，以进一步净化 `commands/helpers.py`。
- **发布准备**: 这次重构提升了 CLI 的健壮性，我们可以开始规划下一个版本的发布，将这些改进交付给用户。
