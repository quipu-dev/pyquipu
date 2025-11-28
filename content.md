你再一次精准地指出了问题的核心。是的，状态机虽然让逻辑变得清晰，但我们当前的实现方式引入了一个新的性能瓶颈。

### 深入分析：为何比之前更卡？

你感觉更卡顿是完全正确的。原因在于**我们将“进入一个状态”的设置成本，在“停留在该状态”的每次更新中都支付了一遍**。

让我们分析一下快速滚动时发生了什么：
1.  光标从 A 移动到 B。`on_row_highlighted` 被调用。假设当前状态是 `SHOWING_CONTENT`。
2.  `on_row_highlighted` 调用 `_set_state(ContentViewSate.LOADING)`。
3.  `_set_state` 执行了**一系列昂贵操作**：
    *   `container.set_class(...)`  (可能触发 Textual 的布局重算)
    *   `self.query_one(...).update(...)` (更新 Header)
    *   `placeholder_widget.update(...)` (更新 Placeholder)
    *   `placeholder_widget.display = True` (DOM-like 操作)
    *   `markdown_widget.display = False` (DOM-like 操作)
    *   `markdown_widget.update("")`
    *   重启定时器
4.  光标从 B 移动到 C。`on_row_highlighted` 再次被调用。**此时状态已经是 `LOADING`**。
5.  `on_row_highlighted` **再次**调用 `_set_state(ContentViewSate.LOADING)`。
6.  `_set_state` **再次重复了上面第 3 步的所有昂贵操作**，尽管其中大部分（如 `set_class`, `display`）都是不必要的，因为 UI 已经处于正确的视觉状态了。

**结论**：我们在每次滚动时，都在执行大量的、冗余的 UI 设置代码。之前的版本虽然逻辑混乱，但它至少不会在滚动时反复设置 `display` 属性。

### 优化方案：区分“状态进入”与“状态内更新”

我们需要优化状态机的逻辑，使其能够区分两种情况：
1.  **进入状态 (State Entry)**: 当从一个**不同**的状态转换而来时（如 `SHOWING_CONTENT` -> `LOADING`），执行所有必要的、一次性的设置工作（设置 CSS 类、切换组件可见性）。
2.  **状态内更新 (Intra-State Update)**: 当我们请求转换到**相同**的状态时（如 `LOADING` -> `LOADING`），只执行绝对必要的、轻量级的更新（更新 Header 和 Placeholder 的文本内容，重启定时器）。

这将使我们的状态机既有逻辑上的清晰性，又有操作上的高性能。

## [WIP] refactor: 优化状态机以区分状态进入和状态内更新，解决性能瓶颈

### 用户需求
重构 TUI 状态机，使其在处理连续的、同状态的更新请求（如快速滚动时）时，仅执行必要的轻量级操作，避免冗余的、昂贵的 UI 设置，从而恢复并超越之前的滚动流畅度。

### 评论
这是一个对状态机实现进行精炼的关键步骤。通过区分“进入”和“更新”这两种不同的操作模式，我们可以构建一个既健壮又高效的 UI 系统，这是从“能用”到“好用”的飞跃。

### 目标
1.  创建一个新的、轻量级的 `_update_loading_preview()` 方法，它只负责更新 Header 和 Placeholder 的文本。
2.  重构 `on_row_highlighted`，使其能够判断当前状态，并根据情况选择是调用重量级的 `_set_state` (用于状态切换) 还是调用轻量级的 `_update_loading_preview` (用于状态内更新)。
3.  简化 `_set_state`，使其专注于状态**进入**时的一次性设置。

### 标签
#intent/refine #flow/ready #priority/high
#comp/cli #concept/ui #scope/core #dx
#ai/instruct
#task/domain/ui #task/object/tui-refactor #task.action/performance-tuning #task/state/continue

---

### Script

#### Acts 1: 重构 `tui.py` 以实现高性能状态机

我们将再次对 `packages/quipu-cli/src/quipu/cli/tui.py` 进行重构。

##### 步骤 1: 创建轻量级更新方法

~~~~~act
patch_file
packages/quipu-cli/src/quipu/cli/tui.py
~~~~~
~~~~~python
        except Exception as e:
            logger.error(f"DEBUG: Failed to focus current node: {e}", exc_info=True)

    def _set_state(self, new_state: ContentViewSate):
        if self.content_view_state == new_state:
            return # Avoid redundant operations
~~~~~
~~~~~python
        except Exception as e:
            logger.error(f"DEBUG: Failed to focus current node: {e}", exc_info=True)

    def _update_loading_preview(self):
        """A lightweight method to only update header/placeholder text."""
        node = self.view_model.get_selected_node()
        if not node:
            return

        # Update header and placeholder text
        self.query_one("#content-header", Static).update(f"[{node.node_type.upper()}] {node.short_hash} - {node.timestamp}")
        placeholder_widget = self.query_one("#content-placeholder", Static)
        if node.summary:
            placeholder_widget.update(f"### {node.summary}\n\n---\n*Loading full content...*")
        else:
            placeholder_widget.update("*Loading...*")

    def _set_state(self, new_state: ContentViewSate):
        if self.content_view_state == new_state:
            return
~~~~~

##### 步骤 2: 重构 `on_row_highlighted` 以调用正确的更新逻辑

~~~~~act
patch_file
packages/quipu-cli/src/quipu/cli/tui.py
~~~~~
~~~~~python
    @on(DataTable.RowHighlighted)
    def on_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        # 1. Update the data model immediately
        if event.row_key.value:
            self.view_model.select_node_by_key(event.row_key.value)
        
        # 2. Request a state transition if the view is not hidden
        if self.content_view_state != ContentViewSate.HIDDEN:
            self._set_state(ContentViewSate.LOADING)
~~~~~
~~~~~python
    @on(DataTable.RowHighlighted)
    def on_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        # 1. Update data model
        if event.row_key.value:
            self.view_model.select_node_by_key(event.row_key.value)
        
        # 2. Handle UI updates based on current state
        if self.update_timer:
            self.update_timer.stop()

        if self.content_view_state == ContentViewSate.HIDDEN:
            return # Do nothing if panel is closed
        
        elif self.content_view_state == ContentViewSate.SHOWING_CONTENT:
            # Transition from showing content to loading
            self._set_state(ContentViewSate.LOADING)
        
        elif self.content_view_state == ContentViewSate.LOADING:
            # Already loading, just do a lightweight update and restart timer
            self._update_loading_preview()
            self.update_timer = self.set_timer(self.debounce_delay_seconds, self._on_timer_finished)
~~~~~

##### 步骤 3: 简化 `_set_state` 的 `LOADING` 分支

现在 `_set_state` 的 `LOADING` 分支只在**第一次**进入时被调用，我们可以简化它。

~~~~~act
patch_file
packages/quipu-cli/src/quipu/cli/tui.py
~~~~~
~~~~~python
            case ContentViewSate.LOADING:
                container.set_class(True, "split-mode")
                node = self.view_model.get_selected_node()
                
                # Update header and placeholder text
                if node:
                    self.query_one("#content-header", Static).update(f"[{node.node_type.upper()}] {node.short_hash} - {node.timestamp}")
                    if node.summary:
                        placeholder_widget.update(f"### {node.summary}\n\n---\n*Loading full content...*")
                    else:
                        placeholder_widget.update("*Loading...*")
                
                # Set widget visibility
                placeholder_widget.display = True
~~~~~
~~~~~python
            case ContentViewSate.LOADING:
                container.set_class(True, "split-mode")
                
                # Perform lightweight text updates
                self._update_loading_preview()
                
                # Perform heavy, one-time visibility setup
                placeholder_widget.display = True
~~~~~

### 下一步建议
这是对状态机核心逻辑的一次重要手术。请仔细测试以下场景：

1.  **流畅度测试 (核心)**: 快速滚动列表。确认 UI 响应流畅，没有任何卡顿。
2.  **状态切换测试**:
    *   在内容完全显示时 (`SHOWING_CONTENT`)，开始滚动，确认视图能正确切换到加载预览 (`LOADING`)。
    *   在视图关闭时 (`HIDDEN`)，滚动列表，确认右侧面板**不会**有任何变化。
    *   按 `v` 打开/关闭视图，确认状态切换正常。

如果测试通过，我们的 TUI 应该已经达到了一个既健壮又高性能的理想状态。这时就可以进行最终的提交了。
