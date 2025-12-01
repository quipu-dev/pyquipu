## [WIP] refactor: 优化 TUI 内容渲染的“双缓冲”机制

### 上下文与问题分析
当前 `quipu ui` 在从纯文本预览切换到 Markdown 富文本显示时，存在视觉上的卡顿或瞬间空白。这是因为 `Markdown.update()` 是一个昂贵的同步操作，如果在组件可见的状态下调用，或者在调用前过早隐藏了占位符，就会导致用户感知到渲染延迟。

我们需要引入“双缓冲”策略：利用 `Static` 组件作为前台缓冲区（显示纯文本），利用不可见的 `Markdown` 组件作为后台缓冲区（进行渲染计算）。只有当 Markdown 渲染准备就绪后，才进行原子的可见性切换。

### 用户需求
应用“双缓冲”方案，具体包括：
1.  调整 `_set_state` 的 `LOADING` 状态：立即更新并显示 `Static` 占位符，隐藏 `Markdown` 组件，并启动计时器。
2.  调整 `_set_state` 的 `SHOWING_CONTENT` 状态：先在**隐藏**状态下更新 `Markdown` 内容，待更新调用返回后，执行原子化的“显隐切换”（Show Markdown / Hide Static）。

### 评论
这是一个针对 TUI 交互体验的精细化性能优化。通过解耦“数据准备”和“视觉呈现”，可以显著提升用户感知的流畅度，消除闪烁。

### 目标
1.  重构 `packages/quipu-cli/src/pyquipu/cli/tui.py` 中的 `_set_state` 方法。
2.  确保 `compose` 方法中的组件结构支持这种并列切换（当前结构已支持，主要通过逻辑控制显隐）。

### 基本原理
Textual 的 `display` 属性切换是瞬时的（CSS 类变更）。而 `Markdown.update()` 包含解析和布局计算。通过在 `display=False` 的状态下执行 `update()`，我们让昂贵的计算过程对用户不可见，而在上一帧内容（Static 预览）的掩护下完成。

### 标签
#intent/refine #flow/ready #priority/medium #comp/cli #concept/ui #scope/ux #ai/instruct #task/domain/ui #task/object/content-view #task/action/refactor #task/state/continue

---

### Script

#### Acts 1: 重构 `tui.py` 的状态切换逻辑

我们将使用 `patch_file` 替换整个 `_set_state` 方法，以严格遵循新的双缓冲流程。同时，我们会将原先分散在 `_update_loading_preview` 中的逻辑内联到 `LOADING` 状态中，使状态转换逻辑更加内聚和清晰。

~~~~~act
patch_file
packages/quipu-cli/src/pyquipu/cli/tui.py
~~~~~
~~~~~python
    def _update_loading_preview(self):
        """A lightweight method to only update header/placeholder text."""
        node = self.view_model.get_selected_node()
        if not node:
            return

        # Update header and placeholder text
        self.query_one("#content-header", Static).update(
            f"[{node.node_type.upper()}] {node.short_hash} - {node.timestamp}"
        )

        # Always get the full content bundle for consistent information display.
        # The Static widget is in markup=False mode, so it's fast and safe.
        content_bundle = self.view_model.get_content_bundle(node)
        self.query_one("#content-placeholder", Static).update(content_bundle)

    def _set_state(self, new_state: ContentViewSate):
        # Allow re-entering SHOWING_CONTENT to force a re-render after toggling markdown
        if self.content_view_state == new_state and new_state != ContentViewSate.SHOWING_CONTENT:
            return

        self.content_view_state = new_state

        container = self.query_one("#main-container")
        placeholder_widget = self.query_one("#content-placeholder", Static)
        markdown_widget = self.query_one("#content-body", Markdown)

        if self.update_timer:
            self.update_timer.stop()

        match new_state:
            case ContentViewSate.HIDDEN:
                container.set_class(False, "split-mode")

            case ContentViewSate.LOADING:
                container.set_class(True, "split-mode")

                # Perform lightweight text updates
                self._update_loading_preview()

                # Perform heavy, one-time visibility setup
                placeholder_widget.display = True
                markdown_widget.display = False
                markdown_widget.update("")  # Prevent ghosting

                # Start timer for next state transition
                self.update_timer = self.set_timer(self.debounce_delay_seconds, self._on_timer_finished)

            case ContentViewSate.SHOWING_CONTENT:
                container.set_class(True, "split-mode")
                node = self.view_model.get_selected_node()

                if node:
                    content = self.view_model.get_content_bundle(node)
                    # Update header
                    self.query_one("#content-header", Static).update(
                        f"[{node.node_type.upper()}] {node.short_hash} - {node.timestamp}"
                    )

                    if self.markdown_enabled:
                        markdown_widget.update(content)
                        placeholder_widget.display = False
                        markdown_widget.display = True
                    else:
                        placeholder_widget.update(content)
                        placeholder_widget.display = True
                        markdown_widget.display = False
~~~~~
~~~~~python
    def _set_state(self, new_state: ContentViewSate):
        # Allow re-entering SHOWING_CONTENT to force a re-render after toggling markdown
        if self.content_view_state == new_state and new_state != ContentViewSate.SHOWING_CONTENT:
            return

        self.content_view_state = new_state

        container = self.query_one("#main-container")
        placeholder_widget = self.query_one("#content-placeholder", Static)
        markdown_widget = self.query_one("#content-body", Markdown)

        if self.update_timer:
            self.update_timer.stop()

        match new_state:
            case ContentViewSate.HIDDEN:
                container.set_class(False, "split-mode")

            case ContentViewSate.LOADING:
                container.set_class(True, "split-mode")

                # --- 1. 获取即时数据 (Get immediate data) ---
                node = self.view_model.get_selected_node()
                content_bundle = self.view_model.get_content_bundle(node) if node else ""

                if node:
                    self.query_one("#content-header", Static).update(
                        f"[{node.node_type.upper()}] {node.short_hash} - {node.timestamp}"
                    )

                # --- 2. 更新并显示预览 (Update and show preview) ---
                # 将纯文本内容更新到 Static 组件，并确保其可见
                placeholder_widget.update(content_bundle)
                placeholder_widget.display = True

                # 确保 Markdown 组件不可见 (后台)
                markdown_widget.display = False
                markdown_widget.update("")  # 清理旧内容防止鬼影

                # --- 3. 启动防抖计时器 (Start debounce timer) ---
                self.update_timer = self.set_timer(self.debounce_delay_seconds, self._on_timer_finished)

            case ContentViewSate.SHOWING_CONTENT:
                container.set_class(True, "split-mode")
                node = self.view_model.get_selected_node()

                if node:
                    content = self.view_model.get_content_bundle(node)
                    self.query_one("#content-header", Static).update(
                        f"[{node.node_type.upper()}] {node.short_hash} - {node.timestamp}"
                    )

                    if self.markdown_enabled:
                        # --- 1. 在后台更新 Markdown (Update Markdown in background) ---
                        # 关键：此时 Markdown 组件仍然是 display=False
                        markdown_widget.update(content)

                        # --- 2. 原子化切换视图 (Atomic switch) ---
                        # update() 完成后，瞬时切换显隐状态
                        markdown_widget.display = True
                        placeholder_widget.display = False
                    else:
                        # Raw text mode
                        placeholder_widget.update(content)
                        placeholder_widget.display = True
                        markdown_widget.display = False
~~~~~

#### Acts 2: 移除不再需要的 `_update_loading_preview`

由于我们将逻辑内联到了 `_set_state` 中以保证流程的清晰和原子性，这个辅助方法现在是多余的。

~~~~~act
patch_file
packages/quipu-cli/src/pyquipu/cli/tui.py
~~~~~
~~~~~python
    def _focus_current_node(self, table: DataTable):
        current_output_tree_hash = self.view_model.current_output_tree_hash
~~~~~
~~~~~python
    def _update_loading_preview(self):
        """A lightweight method to only update header/placeholder text."""
        node = self.view_model.get_selected_node()
        if not node:
            return

        # Update header and placeholder text
        self.query_one("#content-header", Static).update(
            f"[{node.node_type.upper()}] {node.short_hash} - {node.timestamp}"
        )

        # Always get the full content bundle for consistent information display.
        # The Static widget is in markup=False mode, so it's fast and safe.
        content_bundle = self.view_model.get_content_bundle(node)
        self.query_one("#content-placeholder", Static).update(content_bundle)

    def _focus_current_node(self, table: DataTable):
        current_output_tree_hash = self.view_model.current_output_tree_hash
~~~~~

#### Acts 3: 清理 `on_row_highlighted` 中的旧调用

因为我们移除了 `_update_loading_preview`，我们需要更新调用它的地方。

~~~~~act
patch_file
packages/quipu-cli/src/pyquipu/cli/tui.py
~~~~~
~~~~~python
        elif self.content_view_state == ContentViewSate.LOADING:
            # Already loading, just do a lightweight update and restart timer
            self._update_loading_preview()
            self.update_timer = self.set_timer(self.debounce_delay_seconds, self._on_timer_finished)
~~~~~
~~~~~python
        elif self.content_view_state == ContentViewSate.LOADING:
            # Already loading, just restart timer.
            # The preview is already updated by the previous transition or will be updated
            # if we trigger a new state transition. Since we are in LOADING, we might want
            # to refresh the preview text if the user moves fast.
            # Re-invoking _set_state(LOADING) handles the text update efficiently.
            self._set_state(ContentViewSate.LOADING)
~~~~~

### 下一步建议
- 启动 `quipu ui`，快速上下移动光标，验证右侧预览区域是否先显示纯文本，然后在停止移动 0.5 秒后平滑且无闪烁地切换为 Markdown 渲染。
