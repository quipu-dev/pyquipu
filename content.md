You are absolutely right to point this out. My apologies, the previous fix was incomplete. Your new traceback provides the crucial clue.

### 错误分析
The error `MarkupError: Expected markup value (found '=False, dir_okay=True, resolve_path=True\n').` reveals that the issue is more fundamental than just unclosed tags.

1.  **Root Cause**: The `Static` widget, by default, has its `markup` property enabled. This means it *always* tries to interpret its content as Rich markup.
2.  **Incomplete Fix**: My previous solution using `rich.markup.escape` correctly handles explicit tag characters like `[` by converting them to `\[`. However, the Rich markup parser is complex. It can still get confused by strings that *look like* parts of a tag's value definition, especially when they contain `=` signs and quotes, as seen in the Python code arguments (`dir_okay=True`).
3.  **The Correct Approach**: Instead of trying to sanitize every possible string that could confuse the parser (an endless task), the correct and much more robust solution is to tell the `Static` widget to **completely disable markup parsing**. We want it to behave as a plain text viewer, and it has a constructor argument specifically for this purpose: `markup=False`.

By setting this, we switch the widget's mode from "smart rich text renderer" to "dumb plain text display," which is exactly what's needed for this fast preview feature. This eliminates the entire class of `MarkupError` exceptions.

I will now generate a new plan that implements this correct, more fundamental fix. It will involve reverting the previous `escape` change (as it's now unnecessary) and setting `markup=False` on the widget.

## [WIP] fix: 彻底禁用 TUI 预览的 markup 解析以防止崩溃

### 错误分析
The `Static` widget used for content previews (`content-placeholder`) was initialized with its default setting of `markup=True`. While the previous fix attempted to escape the input content using `rich.markup.escape`, this was insufficient. The Rich markup parser can still be erroneously triggered by complex strings within code snippets (e.g., Python keyword arguments like `dir_okay=True`), leading to a `MarkupError` and a TUI crash. The fundamental problem was that the widget was in the wrong mode, not just that the input was occasionally malformed.

### 用户需求
The TUI's scrolling preview must be completely robust and never crash, regardless of the text content of the history nodes.

### 评论
This is a much more robust and correct fix. Instead of patching the symptoms (sanitizing input), we are addressing the root cause by configuring the component to operate in the desired plain-text mode. This prevents an entire category of potential parsing errors and ensures UI stability.

### 目标
1.  Modify `packages/quipu-cli/src/quipu/cli/tui.py`.
2.  When creating the `Static` widget with `id="content-placeholder"`, pass the `markup=False` argument to its constructor.
3.  Remove the now-redundant `rich.markup.escape` import and its usage, as the widget will no longer be parsing markup at all.

### 基本原理
By initializing the `Static` widget as `Static(..., markup=False)`, we explicitly instruct Textual's rendering engine to treat any string passed to its `.update()` method as pure, literal text. No parsing of `[` or any other special characters will occur. This is the most direct and foolproof way to display arbitrary text content without risking rendering errors.

### 标签
#intent/fix #flow/ready #priority/critical #comp/cli #concept/ui #scope/ux #ai/instruct #task/domain/ui #task/object/tui-performance #task/action/optimization #task/state/continue

---

### Script

#### Acts 1: Reconfigure Static widget and remove unused code

We will perform a single, comprehensive update to `tui.py` to apply the correct fix and clean up the previous, ineffective one. Using `write_file` is the safest way to ensure the final state is exactly as intended.

~~~~~act
write_file
packages/quipu-cli/src/quipu/cli/tui.py
~~~~~
~~~~~python
import sys
import logging
from enum import Enum, auto
from pathlib import Path
from typing import List, Optional

from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, DataTable, Markdown, Static
from textual.containers import Horizontal, Vertical
from textual.binding import Binding
from textual.coordinate import Coordinate
from textual import on
from textual.timer import Timer

from quipu.core.models import QuipuNode
from quipu.core.state_machine import Engine
from .view_model import GraphViewModel
from .factory import create_engine

logger = logging.getLogger(__name__)

# 定义 UI 返回类型: (动作类型, 数据)
# 动作: "checkout" | "dump"
UiResult = tuple[str, str]


class ContentViewSate(Enum):
    HIDDEN = auto()
    LOADING = auto()
    SHOWING_CONTENT = auto()


class QuipuUiApp(App[Optional[UiResult]]):
    CSS_PATH = "tui.css"
    TITLE = "Quipu History Explorer"

    BINDINGS = [
        Binding("q", "quit", "退出"),
        Binding("c", "checkout_node", "检出节点"),
        Binding("enter", "checkout_node", "检出节点"),
        # Re-map 'v' to the new debounced action handler
        Binding("v", "toggle_view", "切换内容视图"),
        Binding("p", "dump_content", "输出内容(stdout)"),
        Binding("t", "toggle_hidden", "显隐非关联分支"),
        Binding("k", "move_up", "上移", show=False),
        Binding("j", "move_down", "下移", show=False),
        Binding("up", "move_up", "上移", show=False),
        Binding("down", "move_down", "下移", show=False),
        Binding("h", "previous_page", "上一页", show=False),
        Binding("left", "previous_page", "上一页"),
        Binding("l", "next_page", "下一页", show=False),
        Binding("right", "next_page", "下一页"),
    ]

    def __init__(self, work_dir: Path):
        super().__init__()
        self.work_dir = work_dir
        self.engine: Optional[Engine] = None
        self.view_model: Optional[GraphViewModel] = None
        
        # --- State Machine ---
        self.content_view_state = ContentViewSate.HIDDEN
        self.update_timer: Optional[Timer] = None
        self.debounce_delay_seconds: float = 0.15

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="main-container"):
            yield DataTable(id="history-table", cursor_type="row", zebra_stripes=False)
            with Vertical(id="content-view"):
                yield Static("Node Content", id="content-header")
                # Add a lightweight placeholder that we can update quickly
                yield Static("", id="content-placeholder", markup=False)
                # The expensive Markdown widget
                yield Markdown("", id="content-body")
        yield Footer()

    def on_mount(self) -> None:
        """Loads the first page of data."""
        logger.debug("TUI: on_mount started.")
        self.query_one(Header).tall = False

        self.engine = create_engine(self.work_dir, lazy=True)
        current_output_tree_hash = self.engine.git_db.get_tree_hash()
        self.view_model = GraphViewModel(reader=self.engine.reader, current_output_tree_hash=current_output_tree_hash)
        self.view_model.initialize()

        table = self.query_one(DataTable)
        table.add_columns("Time", "Graph", "Node Info")

        # 计算 HEAD 所在的页码并跳转
        initial_page = self.view_model.calculate_initial_page()
        logger.debug(f"TUI: HEAD is on page {initial_page}. Loading...")
        self._load_page(initial_page)

        # 强制将焦点给到表格，确保高亮可见且键盘可用
        table.focus()

    def on_unmount(self) -> None:
        logger.debug("TUI: on_unmount called, closing engine.")
        if self.engine:
            self.engine.close()

    def _update_header(self):
        """Centralized method to update the app's title and sub_title."""
        self.sub_title = f"Page {self.view_model.current_page} / {self.view_model.total_pages}"

    def _load_page(self, page_number: int) -> None:
        """Loads and displays a specific page of nodes."""
        logger.debug(f"TUI: Loading page {page_number}")
        self.view_model.load_page(page_number)
        logger.debug(f"TUI: Page {page_number} loaded with {len(self.view_model.current_page_nodes)} nodes.")

        table = self.query_one(DataTable)
        table.clear()
        # 从 ViewModel 获取过滤后的节点列表进行渲染
        self._populate_table(table, self.view_model.get_nodes_to_render())
        self._focus_current_node(table)
        self._update_header()

    def action_move_up(self) -> None:
        self.query_one(DataTable).action_cursor_up()

    def action_move_down(self) -> None:
        self.query_one(DataTable).action_cursor_down()

    def action_toggle_hidden(self) -> None:
        self.view_model.toggle_unreachable()
        self._refresh_table()

    def action_toggle_view(self) -> None:
        self.is_split_mode = not self.is_split_mode
        container = self.query_one("#main-container")
        container.set_class(self.is_split_mode, "split-mode")
        if self.is_split_mode:
            self._update_content_view()

    def action_checkout_node(self) -> None:
        selected_node = self.view_model.get_selected_node()
        if selected_node:
            self.exit(result=("checkout", selected_node.output_tree))

    def action_dump_content(self) -> None:
        selected_node = self.view_model.get_selected_node()
        if selected_node:
            content = self.view_model.get_content_bundle(selected_node)
            self.exit(result=("dump", content))

    def action_previous_page(self) -> None:
        if self.view_model.current_page > 1:
            self._load_page(self.view_model.current_page - 1)
        else:
            self.bell()

    def action_next_page(self) -> None:
        if self.view_model.current_page < self.view_model.total_pages:
            self._load_page(self.view_model.current_page + 1)
        else:
            self.bell()

    def _refresh_table(self):
        table = self.query_one(DataTable)
        table.clear()
        # 从 ViewModel 获取要渲染的节点
        nodes_to_render = self.view_model.get_nodes_to_render()
        self._populate_table(table, nodes_to_render)
        self._focus_current_node(table)
        self._update_header()

    def _populate_table(self, table: DataTable, nodes: List[QuipuNode]):
        # 移除了过滤逻辑，因为 ViewModel 已经处理
        tracks: list[Optional[str]] = []

        for node in nodes:
            is_reachable = self.view_model.is_reachable(node.output_tree)
            dim_tag = "[dim]" if not is_reachable else ""
            end_dim_tag = "[/dim]" if dim_tag else ""
            base_color = "magenta"
            if node.node_type == "plan":
                base_color = "green" if node.input_tree == node.output_tree else "cyan"
            graph_chars = self._get_graph_chars(tracks, node, base_color, dim_tag, end_dim_tag)
            ts_str = f"{dim_tag}{node.timestamp.strftime('%Y-%m-%d %H:%M')}{end_dim_tag}"
            summary = self._get_node_summary(node)

            owner_info = ""
            if node.owner_id:
                owner_display = node.owner_id[:12]
                owner_info = f"[yellow]({owner_display}) [/yellow]"

            info_text = f"{owner_info}[{base_color}][{node.node_type.upper()}] {node.short_hash}[/{base_color}] - {summary}"
            info_str = f"{dim_tag}{info_text}{end_dim_tag}"
            table.add_row(ts_str, "".join(graph_chars), info_str, key=str(node.filename))

    def _get_graph_chars(
        self, tracks: list, node: QuipuNode, base_color: str, dim_tag: str, end_dim_tag: str
    ) -> list[str]:
        merging_indices = [i for i, h in enumerate(tracks) if h == node.output_tree]
        try:
            col_idx = tracks.index(None) if not merging_indices else merging_indices[0]
        except ValueError:
            col_idx = len(tracks)
        while len(tracks) <= col_idx:
            tracks.append(None)
        tracks[col_idx] = node.output_tree
        graph_chars = []
        for i, track_hash in enumerate(tracks):
            if i == col_idx:
                symbol = "●" if node.node_type == "plan" else "○"
                graph_chars.append(f"{dim_tag}[{base_color}]{symbol}[/] {end_dim_tag}")
            elif i in merging_indices:
                graph_chars.append(f"{dim_tag}┘ {end_dim_tag}")
            elif track_hash:
                graph_chars.append(f"{dim_tag}│ {end_dim_tag}")
            else:
                graph_chars.append("  ")
        tracks[col_idx] = node.input_tree
        for i in merging_indices[1:]:
            tracks[i] = None
        while tracks and tracks[-1] is None:
            tracks.pop()
        return graph_chars

    def _get_node_summary(self, node: QuipuNode) -> str:
        return node.summary or "No description"

    def _focus_current_node(self, table: DataTable):
        current_output_tree_hash = self.view_model.current_output_tree_hash
        logger.debug(f"DEBUG: Attempting focus. HEAD={current_output_tree_hash}")

        if not current_output_tree_hash:
            logger.debug("DEBUG: No HEAD hash, skipping.")
            return

        # 查找当前页面中匹配 HEAD 的所有节点
        matching = [
            n for n in self.view_model.current_page_nodes if n.output_tree == current_output_tree_hash
        ]
        logger.debug(f"DEBUG: Found {len(matching)} matching nodes in current page map.")

        target_node = matching[0] if matching else None
        if not target_node:
            logger.debug("DEBUG: Target node not found in current page.")
            return

        try:
            row_key = str(target_node.filename)
            logger.debug(f"DEBUG: Target row key: {row_key}")

            # Textual 的 DataTable API 中，get_row_index 会在 key 不存在时抛出 KeyError
            # 或者 RowKeyError，具体取决于版本，但 KeyError 是基类
            try:
                row_index = table.get_row_index(row_key)
                logger.debug(f"DEBUG: Row index found: {row_index}. Setting cursor.")

                # 1. 设置视觉光标
                table.cursor_coordinate = Coordinate(row=row_index, column=0)

                # 2. Sync data model state
                self.view_model.select_node_by_key(row_key)
                
                # 3. Force-update the header on initial load, regardless of view mode.
                # The state machine will handle the rest of the UI.
                header = self.query_one("#content-header", Static)
                header.update(f"[{target_node.node_type.upper()}] {target_node.short_hash} - {target_node.timestamp}")

            except LookupError:
                # LookupError 捕获 RowKeyError 等
                logger.warning(f"DEBUG: Row key {row_key} not found in DataTable.")

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

        # Prioritize showing the raw public content if it's already loaded in the node object.
        # This provides a very fast preview while scrolling.
        if node.content and node.content.strip():
            placeholder_widget.update(node.content)
        # Fallback to summary if content isn't loaded or is empty.
        elif node.summary:
            placeholder_widget.update(f"### {node.summary}\n\n---\n*Loading full content...*")
        else:
            placeholder_widget.update("*Loading...*")

    def _set_state(self, new_state: ContentViewSate):
        if self.content_view_state == new_state:
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
                markdown_widget.update("") # Prevent ghosting

                # Start timer for next state transition
                self.update_timer = self.set_timer(self.debounce_delay_seconds, self._on_timer_finished)

            case ContentViewSate.SHOWING_CONTENT:
                container.set_class(True, "split-mode")
                node = self.view_model.get_selected_node()
                
                if node:
                    # Update header
                    self.query_one("#content-header", Static).update(f"[{node.node_type.upper()}] {node.short_hash} - {node.timestamp}")
                    # Update markdown content
                    content = self.view_model.get_content_bundle(node)
                    markdown_widget.update(content)
                
                # Set widget visibility
                placeholder_widget.display = False
                markdown_widget.display = True

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

    def _on_timer_finished(self) -> None:
        """Callback for the debounce timer."""
        # The timer finished, so we are ready to show content
        self._set_state(ContentViewSate.SHOWING_CONTENT)
    
    def action_toggle_view(self) -> None:
        """Handles the 'v' key press to toggle the content view."""
        if self.content_view_state == ContentViewSate.HIDDEN:
            # If a node is selected, transition to loading, otherwise do nothing
            if self.view_model.get_selected_node():
                self._set_state(ContentViewSate.LOADING)
        else:
            self._set_state(ContentViewSate.HIDDEN)
~~~~~

### 下一步建议
这应该就是最终的、正确的修复了。请再次运行 `qd ui` 进行测试。在确认稳定后，我们可以将这一系列的 TUI 性能优化和 bug 修复工作打包成一个 `[COMMIT]`，正式结束这个任务。
