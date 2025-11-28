好的，我们将把本次 TUI 性能优化的所有工作——从最初的防抖实现到最终的细节修复——整合到一个完整的、可交付的 `[COMMIT]` 计划中。

这个计划将包含所有相关文件的 `git add` 指令，以及一个详细描述了整个优化过程的 Git 提交信息。

## [COMMIT] fix(cli): 解决 TUI 滚动卡顿和视觉伪影问题

### 用户需求
修复 TUI 在快速滚动历史列表时出现的严重性能问题，包括 UI 卡顿、内容视图渲染延迟、旧内容残留 (Ghosting)、以及 Header 与光标位置不同步等一系列视觉和交互缺陷。

### 评论
这是一次对 TUI 核心交互体验的全面重构和优化。通过引入防抖机制和双组件切换架构，我们从根本上解决了高频事件导致的渲染瓶颈，使 TUI 具备了流畅、专业、响应迅速的交互表现，极大地提升了用户体验。

### 目标
1.  **实现流畅滚动**: 解决了快速滚动时因高频 Markdown 渲染导致的 UI 阻塞问题。
2.  **提供即时反馈**: 在滚动时，通过轻量级 `Static` 组件实时显示节点的 Header 和摘要作为占位符。
3.  **消除视觉错误**:
    *   修复了 `display: true` 的 CSS 语法错误。
    *   解决了切换节点时旧内容“一闪而过”的重影 (Ghosting) 问题。
    *   修复了 TUI 启动时 Header 未能正确初始化的问题。
4.  **同步 UI 状态**: 确保了 Header 信息能够实时跟随光标移动，而不是延迟更新。
5.  **代码提交**: 将所有相关改进作为一个原子性提交，永久记录到版本历史中。

### 基本原理
本次优化的核心是采用了**双组件切换**的设计模式，将高频、低成本的 UI 更新与低频、高成本的更新彻底分离：
1.  **`Static` 组件**: 用于处理高频的 `RowHighlighted` 事件。它负责实时显示 Header 和摘要占位符，因为更新 `Static` 的文本开销极低。
2.  **`Markdown` 组件**: 用于处理低频的、经过防抖处理的最终渲染任务。它在后台（当 `display: none` 时）完成昂贵的 Markdown 解析和高亮，完成后再通过一次廉价的 `display` 切换呈现给用户。

通过在滚动时显示 `Static`、隐藏 `Markdown`，并在滚动停止后反向操作，我们确保了 Textual 的事件循环始终保持畅通，从而实现了流畅的滚动体验。

### 标签
#intent/fix #flow/ready #priority/high
#comp/cli #concept/ui #scope/ux
#ai/brainstorm
#task/domain/ui #task/object/tui-performance #task/action/bug-fix #task/state/end #task/status/completed

---

### Script

#### Acts 1: 将所有相关的变更添加到暂存区

我们将把对 `tui.py` 和 `tui.css` 的所有修改都添加到 Git 的暂存区，准备提交。

~~~~~act
git_add
packages/quipu-cli/src/quipu/cli/tui.py
packages/quipu-cli/src/quipu/cli/tui.css
~~~~~

#### Acts 2: 创建一个内容详尽的 Git 提交

最后，我们创建一个 Git 提交，详细记录这次重要的优化。

~~~~~act
git_commit
~~~~~
~~~~~text
fix(cli): Resolve TUI scrolling lag and visual artifacts

This commit comprehensively overhauls the TUI content view to fix severe performance issues and visual glitches during rapid scrolling.

The root cause was the expensive `Markdown.update()` operation being called synchronously on every `DataTable.RowHighlighted` event, blocking the event loop.

The solution implements a dual-component switching architecture:
1.  A `Static` widget (`#content-placeholder`) is now used to display a lightweight, real-time preview (node summary) during scrolling. Updating a Static widget is extremely cheap.
2.  The expensive `Markdown` widget (`#content-body`) is hidden during scrolling. Its content is only updated via a debounced timer that fires after the user stops scrolling.
3.  Visibility of the two widgets is swapped to present the fully rendered content seamlessly after the debounce delay.

This resolves the following issues:
- Eliminates UI lag and stuttering during fast scrolling.
- Provides immediate, semantic feedback via the placeholder.
- Fixes "ghosting" artifacts where stale content from the previous node would flash briefly by clearing the Markdown widget when it's hidden.
- Ensures the header bar updates in real-time with the cursor, as its update logic was moved out of the debounced function.
- Corrects the initial state of the header on app startup.
- Fixes a CSS syntax error (`display: true` to `display: block`).
~~~~~

### 下一步建议
TUI 性能优化任务已圆满完成。现在可以继续处理其他开发任务了。
