你的观察非常敏锐。

问题分析

在上一版重构中，为了实现“异步 + 防抖”，我将**所有** UI 更新（包括顶部的节点信息头 `Header` 和下面的内容体 `Body`）都推迟到了后台 Worker 完成之后 (`_update_content_ui`)。

这就导致了你提到的**回归**：
在快速滚动（触发防抖）期间，Worker 被不断推迟，导致**Header 区域（显示 Hash、时间、摘要的部分）也完全停止了更新**。用户感觉界面像“死”了一样，直到停下来才会突然跳出信息。

在旧版本中，虽然内容会清空，但 Header 是跟随光标**即时更新**的。这提供了关键的视觉反馈（“纯文本渲染机制”）。

解决方案

我们需要拆分 UI 更新逻辑：

1.  **同步、即时更新 Header**：`on_row_highlighted` 触发时，立即在主线程更新 Header。这部分只涉及内存中的元数据（Summary, Hash, Timestamp），非常快，不会阻塞滚动，且能找回“跟手”的感觉。
2.  **异步、防抖更新 Body**：保持 Body 内容的异步加载逻辑不变，继续解决闪烁和 I/O 阻塞问题。

## [WIP] fix(cli): 恢复 TUI 滚动时的即时 Header 反馈

### 用户需求
在 TUI 快速滚动列表时，右侧面板顶部的节点信息（Header）应该即时更新，而不是等待防抖计时器结束。

### 目标
1.  在 `pyquipu/cli/tui.py` 中，将 Header 的更新逻辑从 `_update_content_ui`（异步回调）中剥离出来。
2.  在 `on_row_highlighted`（同步事件）中直接调用 Header 更新逻辑。

### 标签
#intent/fix #flow/ready #priority/high #comp/cli #concept/ui #scope/ux #ai/instruct #task/domain/ui #task/object/tui-responsiveness #task/action/bug-fix #task/state/continue

---

### Script

#### Acts 1: 分离 Header 更新逻辑并实现即时反馈

~~~~~act
patch_file
packages/quipu-cli/src/pyquipu/cli/tui.py
~~~~~
~~~~~python
    @on(DataTable.RowHighlighted)
    def on_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """处理行高亮事件：更新 ViewModel 并触发防抖加载"""
        if event.row_key.value:
            self.view_model.select_node_by_key(event.row_key.value)
        
        if self.is_details_visible:
            self._trigger_content_load(immediate=False)

    def _trigger_content_load(self, immediate: bool = False):
~~~~~
~~~~~python
    @on(DataTable.RowHighlighted)
    def on_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """处理行高亮事件：更新 ViewModel 并触发防抖加载"""
        if event.row_key.value:
            node = self.view_model.select_node_by_key(event.row_key.value)
            # 立即更新 Header，提供即时视觉反馈
            if node and self.is_details_visible:
                self._update_header_ui(node)
        
        if self.is_details_visible:
            self._trigger_content_load(immediate=False)

    def _trigger_content_load(self, immediate: bool = False):
~~~~~

~~~~~act
patch_file
packages/quipu-cli/src/pyquipu/cli/tui.py
~~~~~
~~~~~python
    def _update_content_ui(self, content: str, node: QuipuNode, req_id: int):
        """主 UI 线程：原子化更新界面"""
        # 协调机制：如果 ID 不匹配，说明结果已过时，直接丢弃
        if req_id != self._current_request_id:
            logger.debug(f"Ignored stale result for req_id {req_id} (current: {self._current_request_id})")
            return

        # 更新 Header
        header = self.query_one("#content-header", Static)
        header.update(f"[{node.node_type.upper()}] {node.short_hash} - {node.timestamp.strftime('%Y-%m-%d %H:%M')}")

        # 原子化更新内容组件，无中间空白状态
        if self.markdown_enabled:
            self.query_one("#content-body", Markdown).update(content)
        else:
            self.query_one("#content-raw", Static).update(content)
~~~~~
~~~~~python
    def _update_header_ui(self, node: QuipuNode):
        """立即更新 Header 内容"""
        header = self.query_one("#content-header", Static)
        header.update(f"[{node.node_type.upper()}] {node.short_hash} - {node.timestamp.strftime('%Y-%m-%d %H:%M')}")

    def _update_content_ui(self, content: str, node: QuipuNode, req_id: int):
        """主 UI 线程：原子化更新界面"""
        # 协调机制：如果 ID 不匹配，说明结果已过时，直接丢弃
        if req_id != self._current_request_id:
            logger.debug(f"Ignored stale result for req_id {req_id} (current: {self._current_request_id})")
            return

        # Header 已经在 on_row_highlighted 中更新过了，但在 Worker 完成时
        # 再次更新也是安全的，且能确保最终一致性（防止极端的时序问题）
        self._update_header_ui(node)

        # 原子化更新内容组件，无中间空白状态
        if self.markdown_enabled:
            self.query_one("#content-body", Markdown).update(content)
        else:
            self.query_one("#content-raw", Static).update(content)
~~~~~
