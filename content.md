好的，所有测试都已通过。`ViewModel` 的重构工作已经完成并经过验证。现在我将创建一个 Git 提交来固化这些变更。

## feat(cli): 重构 ViewModel 以支持分页并修复测试

### 用户需求
为了实现 UI 的秒级启动和分页浏览功能，需要将 `GraphViewModel` 从无限滚动模型重构为传统的分页模型。同时，相关的测试用例也需要更新以匹配新的 API。

### 评论
本次重构是 UI 性能优化方案的关键一步。通过将分页逻辑完全封装在 `ViewModel` 中，我们成功地将数据层与表现层解耦，为后续 `tui.py` 的改造奠定了坚实的基础。测试的同步修复确保了代码的健壮性。

### 目标
-   将 `GraphViewModel` 的分页模型从 `load_next_page` (无限滚动) 更改为 `load_page(page_number)` (传统分页)。
-   添加 `next_page()` 和 `previous_page()` 便捷方法，简化 UI 调用。
-   更新 `tests/test_view_model.py` 中的测试用例，以验证新的分页 API 的正确性。

### 基本原理
遵循 MVVM 设计模式，将分页的状态管理（如当前页、总页数）和数据获取逻辑（计算 offset、调用 reader）封装在 `ViewModel` 中。`View` (TUI) 层仅负责触发动作（如“下一页”）和渲染返回的数据，从而实现逻辑和视图的清晰分离。

### 标签
#intent/refine #intent/tooling #flow/done #priority/high
#comp/cli #comp/tests #concept/ui #scope/core
#ai/instruct
#task/state/continue #task-status/active

---

### Script

#### Acts 1: 提交代码

将所有已修改的文件（`view_model.py` 和 `test_view_model.py`）添加到暂存区并创建一个提交。

~~~~~act
git_add .
~~~~~

~~~~~act
git_commit
~~~~~
~~~~~
feat(cli): 重构 ViewModel 以支持分页并修复测试

本次提交完成了 UI 性能优化方案中的 ViewModel 重构。

主要变更：
- 将 `GraphViewModel` 的数据加载模型从无限滚动的 `load_next_page` 更改为支持“上一页/下一页”的传统分页模型 `load_page(page_number)`。
- 引入了 `total_pages`, `current_page` 等状态属性，将分页逻辑完全封装在 ViewModel 内部。
- 添加了 `next_page()` 和 `previous_page()` 便捷方法，以简化 UI 层的调用。
- 同步更新了 `tests/test_view_model.py` 中的测试用例，以确保新 API 的行为符合预期。

这项重构为下一阶段的 TUI 适配工作奠定了坚实的基础。
~~~~~

### 下一步建议
`ViewModel` 的准备工作已全部完成并提交。现在，我们可以安全地进入**阶段三：前端 UI 适配**，开始对 `packages/quipu-cli/src/quipu/cli/tui.py` 进行改造，使其对接新的 `GraphViewModel`。
