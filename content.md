好的，我们已经完成了 TUI 的前端修复和重构。现在我们将把这些成果固化到版本历史中，并规划下一步的核心任务。

## fix(cli): 全面修复 TUI 的分页、布局及状态更新问题

### 用户需求
在 TUI 分页功能重构后，出现了一系列 UI 显示和交互问题，包括启动崩溃、布局溢出、页脚不显示以及标题更新逻辑不规范。需要一次性修复这些问题，使 TUI 达到稳定可用的状态。

### 评论
本次修复遵循了 Textual 框架的最佳实践，通过 `dock` 布局解决了核心的溢出问题，并将动态信息移至 `Header`，增强了 UI 的健壮性。同时，将 CSS 分离到独立文件，提升了代码的可维护性。

### 目标
1.  创建一个稳定的、无布局错误的 TUI 界面。
2.  确保分页信息在 `Header` 中正确、实时地显示。
3.  实现代码与样式的分离。

### 基本原理
1.  **布局**: 使用 Textual 的 `dock` 属性为 `Header` 和 `Footer` 分配固定空间，让主内容区自动填充剩余空间，从根本上解决了尺寸计算导致的溢出问题。
2.  **状态更新**: 遵循 Textual 的设计模式，通过更新 `App` 实例的 `self.sub_title` 属性来动态修改 `Header` 的副标题，而不是直接操作 `Header` Widget。
3.  **代码组织**: 利用 `CSS_PATH` 类变量将样式表外部化，使 Python 代码专注于逻辑，CSS 文件专注于表现。

### 标签
#intent/fix #intent/refine #flow/ready #priority/high #comp/cli #concept/ui #scope/dx #ai/instruct #task/domain/ui #task/object/tui #task/action/bug-fix #task/state/end #task/status/completed

---

### Script

#### Acts 1: 提交 TUI 修复与重构

现在，我将把所有相关的修改（`tui.py`）和新文件（`tui.css`）添加到 Git 暂存区，并创建一个描述本次工作的提交。

~~~~~act
git_add
~~~~~
~~~~~text
packages/quipu-cli/src/quipu/cli/tui.py
packages/quipu-cli/src/quipu/cli/tui.css
~~~~~

~~~~~act
git_commit
~~~~~
~~~~~text
fix(cli): 全面修复 TUI 的分页、布局及状态更新问题

本次提交解决了一系列在 TUI 分页重构后出现的渲染和交互 bug，使 UI 达到稳定状态。

主要变更包括：
- **修复布局溢出**: 在 `tui.css` 中为 Header 和 Footer 添加 `dock` 属性，彻底解决了主内容区 `height: 100%` 导致的布局溢出和不必要的滚动条问题。
- **迁移分页信息**: 将分页状态（"Page P / T"）的显示位置从不稳定的 Footer 移至始终可见的 Header 副标题，提升了用户体验。
- **修正状态更新逻辑**: 重构 `_update_header` 方法，通过修改 `self.sub_title` 来更新标题，严格遵循了 Textual 框架的状态管理规范。
- **分离 CSS**: 将所有样式代码从 `tui.py` 中提取到独立的 `tui.css` 文件，提高了代码的可维护性和分离度。
- **增强分页控制**: 为分页动作 (`action_previous_page`, `action_next_page`) 添加了边界检查，防止越界加载并提供声音反馈。
~~~~~

---

### 下一步建议

现在 TUI 的**视图 (View)** 和**视图模型 (ViewModel)** 层已经稳定，但我们明确了问题的根源在于**模型 (Model)** 层——即 `quipu-engine` 提供的数据不准确。

**当前核心问题**: `SQLiteHistoryReader.get_ancestor_hashes` 方法未能返回从当前节点到根节点的完整祖先链，导致 UI 无法正确高亮主干分支。

因此，下一步的计划是深入 `quipu-engine` 模块，彻底修复这个数据源问题。
