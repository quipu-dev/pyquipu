好的，根据我们确定的“防抖触发异步加载”模型，我制定了以下实施计划。

这个计划将重构 `QuipuUiApp` 的状态管理逻辑，移除导致闪烁的“先清空”操作，并引入基于 `request_id` 的异步协调机制。

## [WIP] feat(cli): 实现防抖触发的异步内容加载以消除 TUI 闪烁

### 用户需求
当前的 TUI 在滚动浏览历史节点时，内容面板会经历“显示 -> 清空 (Loading) -> 显示新内容”的循环，导致视觉上的剧烈闪烁。用户希望优化这一体验，实现平滑、无闪烁的内容切换。

### 评论
这是一个涉及核心交互体验的重要重构。我们采用了“防抖触发 + 异步加载 + ID 协调”的混合模型。这不仅消除了闪烁，还通过仅在用户停止滚动时触发 I/O 操作，显著降低了系统资源消耗，是处理 TUI 列表-详情视图的最佳实践。

### 目标
1.  重构 `pyquipu/cli/tui.py`，移除旧的同步状态机中导致内容被清空的逻辑。
2.  引入 `current_request_id` 计数器，用于协调 UI 线程与后台 Worker。
3.  实现异步 Worker 方法，负责在后台调用 `view_model` 获取内容。
4.  实现原子化的 UI 更新逻辑，仅在 Worker 返回的 ID 与当前 ID 匹配时更新内容面板。

### 基本原理
利用 `textual` 框架提供的 `run_worker` 机制将耗时的 I/O 操作移出主线程。通过在 `on_row_highlighted` 中仅重置计时器（而不触碰 UI），我们实现了“防抖”。当计时器耗尽（用户停止滚动），我们启动 Worker 并分配一个唯一的 `request_id`。当 Worker 完成时，UI 线程比对 ID，确保只有最新的请求会触发 `Markdown` 组件的更新，从而实现内容在视觉上的无缝替换。

### 标签
#intent/refine #flow/ready #priority/high #comp/cli #concept/ui #scope/ux #ai/instruct #task/domain/ui #task/object/tui-async-loader #task/action/refactor #task/state/begin

---

### Script

#### Acts 1: 重构 `tui.py` 实现异步加载模型

由于此次修改涉及 `QuipuUiApp` 类的多个方法（初始化、状态定义、事件处理、定时器回调）的逻辑重写，为了保证代码结构的完整性和正确性，避免多个 `patch_file` 可能带来的上下文错位，我们将重写整个 `tui.py` 文件。

~~~~~act
write_file
packages/quipu-cli/src/pyquipu/cli/tui.py
~~~~~
~~~~~python
import logging
from enum import Enum, auto
from pathlib import Path
from typing import List, Optional, Tuple

from pyquipu.engine.state_machine import Engine
from pyquipu.interfaces.models import QuipuNode
from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.coordinate import Coordinate
from textual.timer import Timer
from textual.widgets import DataTable, Footer, Header, Markdown, Static
from textual.worker import Worker

from .factory import create_engine
from .view_model import GraphViewModel

logger = logging.getLogger(__name__)

# 定义 UI 返回类型: (动作类型, 数据)
UiResult = tuple[str, str]


class ContentViewSate(Enum):
    HIDDEN = auto()
    VISIBLE = auto()


class QuipuUiApp(App[Optional[UiResult]]):
    CSS_PATH = "tui.css"
    TITLE = "Quipu History Explorer"

    BINDINGS = [
        Binding("q", "quit", "退出"),
        Binding("space", "checkout_node", "检出节点"),
        Binding("enter", "checkout_node", "检出节点"),
        Binding("v", "toggle_view", "切换内容视图"),
        Binding("m", "toggle_markdown", "切换 Markdown 渲染"),
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

    def __init__(self, work_dir: Path, initial_raw_mode: bool = False):
        super().__init__()
        self.work_dir = work_dir
        self.engine: Optional[Engine] = None
        self.view_model: Optional[GraphViewModel] = None

        # --- State Machine ---
        self.content_view_state = ContentViewSate.HIDDEN
        self.markdown_enabled = not initial_raw_mode

        # --- Async Loading Control ---
        self.update_timer: Optional[Timer] = None
        self.debounce_delay_seconds: float = 0.2  # 防抖延迟，用户停顿后才加载
        self.current_request_id: int = 0  # 用于协调异步结果的 ID

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="main-container"):
            yield DataTable(id="history-table", cursor_type="row", zebra_stripes=False)
            with Vertical(id="content-view"):
                yield Static("Node Content", id="content-header")
                # 用于 Raw 模式的轻量级显示
                yield Static("", id="content-placeholder", markup=False)
                # 用于 Markdown 模式的渲染显示
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

        # 强制将焦点给到表格
        table.focus()

    def on_unmount(self) -> None:
        logger.debug("TUI: on_unmount called, closing engine.")
        if self.engine:
            self.engine.close()

    def _update_header(self):
        """Centralized method to update the app's title and sub_title."""
        mode = "Markdown" if self.markdown_enabled else "Raw Text"
        self.sub_title = f"Page {self.view_model.current_page} / {self.view_model.total_pages} | View: {mode} (m)"

    def _load_page(self, page_number: int) -> None:
        """Loads and displays a specific page of nodes."""
        logger.debug(f"TUI: Loading page {page_number}")
        self.view_model.load_page(page_number)
        
        table = self.query_one(DataTable)
        table.clear()
        self._populate_table(table, self.view_model.get_nodes_to_render())
        self._focus_current_node(table)
        self._update_header()

    # --- Actions ---

    def action_move_up(self) -> None:
        self.query_one(DataTable).action_cursor_up()

    def action_move_down(self) -> None:
        self.query_one(DataTable).action_cursor_down()

    def action_toggle_hidden(self) -> None:
        self.view_model.toggle_unreachable()
        self._refresh_table()

    def action_toggle_markdown(self) -> None:
        """Toggles the rendering mode between Markdown and raw text."""
        self.markdown_enabled = not self.markdown_enabled
        self._update_header()
        
        # 如果当前面板是可见的，强制刷新一次内容
        if self.content_view_state == ContentViewSate.VISIBLE:
            self._trigger_content_load(immediate=True)

    def action_checkout_node(self) -> None:
        selected_node = self.view_model.get_selected_node()
        if selected_node:
            self.exit(result=("checkout", selected_node.output_tree))

    def action_dump_content(self) -> None:
        selected_node = self.view_model.get_selected_node()
        if selected_node:
            content = self.view_model.get_public_content(selected_node)
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
            
    def action_toggle_view(self) -> None:
        """Handles the 'v' key press to toggle the content view."""
        if self.content_view_state == ContentViewSate.HIDDEN:
            self.content_view_state = ContentViewSate.VISIBLE
            self.query_one("#main-container").set_class(True, "split-mode")
            # 打开面板时，立即加载一次内容
            self._trigger_content_load(immediate=True)
        else:
            self.content_view_state = ContentViewSate.HIDDEN
            self.query_one("#main-container").set_class(False, "split-mode")

    # --- Table Population Helpers ---

    def _refresh_table(self):
        table = self.query_one(DataTable)
        table.clear()
        nodes_to_render = self.view_model.get_nodes_to_render()
        self._populate_table(table, nodes_to_render)
        self._focus_current_node(table)
        self._update_header()

    def _populate_table(self, table: DataTable, nodes: List[QuipuNode]):
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

            info_text = (
                f"{owner_info}[{base_color}][{node.node_type.upper()}] {node.short_hash}[/{base_color}] - {summary}"
            )
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
        if not current_output_tree_hash:
            return

        matching = [n for n in self.view_model.current_page_nodes if n.output_tree == current_output_tree_hash]
        target_node = matching[0] if matching else None
        
        if not target_node:
            return

        try:
            row_key = str(target_node.filename)
            row_index = table.get_row_index(row_key)
            table.cursor_coordinate = Coordinate(row=row_index, column=0)
            self.view_model.select_node_by_key(row_key)
            
            # 初始加载时，如果面板可见，也触发内容更新
            if self.content_view_state == ContentViewSate.VISIBLE:
                self._trigger_content_load(immediate=True)
                
        except LookupError:
            pass
        except Exception as e:
            logger.error(f"Failed to focus current node: {e}", exc_info=True)

    # --- Async Content Loading Logic ---

    @on(DataTable.RowHighlighted)
    def on_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """
        当用户移动光标时触发。
        策略：防抖。只更新 ViewModel 的选中状态，重置计时器，不触碰 UI 内容。
        """
        if event.row_key.value:
            self.view_model.select_node_by_key(event.row_key.value)

        # 如果面板是隐藏的，什么都不做
        if self.content_view_state == ContentViewSate.HIDDEN:
            return

        # 重置防抖计时器
        if self.update_timer:
            self.update_timer.stop()
        
        # 启动新的计时器。只有当计时器走完（用户停止滚动），才会触发 _trigger_content_load
        self.update_timer = self.set_timer(self.debounce_delay_seconds, self._trigger_content_load)

    def _trigger_content_load(self, immediate: bool = False) -> None:
        """
        计时器回调或手动触发。
        生成新的 Request ID，并启动后台 Worker 去加载内容。
        """
        node = self.view_model.get_selected_node()
        if not node:
            return

        # 1. 递增 Request ID，使之前的未完成任务变为"过时"
        self.current_request_id += 1
        req_id = self.current_request_id
        
        # 2. 立即更新轻量级的 Header，提高响应感
        self.query_one("#content-header", Static).update(
            f"[{node.node_type.upper()}] {node.short_hash} - {node.timestamp}"
        )

        # 3. 启动后台 Worker
        self._load_content_in_background(node, req_id)

    @work(exclusive=True)
    def _load_content_in_background(self, node: QuipuNode, req_id: int) -> None:
        """
        后台 Worker 方法。执行 I/O 操作。
        """
        # 这个操作可能耗时 (解压 Git 对象)
        content_bundle = self.view_model.get_content_bundle(node)
        
        # 将结果发送回 UI 线程
        self.post_message(self.ContentLoadFinished(req_id, content_bundle))

    class ContentLoadFinished:
        """内部消息：Worker 完成加载后发送。"""
        def __init__(self, request_id: int, content: str):
            self.request_id = request_id
            self.content = content

    @on(ContentLoadFinished)
    def on_content_load_finished(self, event: ContentLoadFinished) -> None:
        """
        主 UI 线程接收到 Worker 的结果。
        策略：ID 协调。只有 ID 匹配时才执行原子化更新。
        """
        # 核心检查：如果 ID 不匹配，说明这是过时的结果（用户又滚动了），直接丢弃。
        if event.request_id != self.current_request_id:
            return

        # ID 匹配，执行无闪烁更新
        placeholder_widget = self.query_one("#content-placeholder", Static)
        markdown_widget = self.query_one("#content-body", Markdown)

        if self.markdown_enabled:
            markdown_widget.update(event.content)
            markdown_widget.display = True
            placeholder_widget.display = False
        else:
            placeholder_widget.update(event.content)
            placeholder_widget.display = True
            markdown_widget.display = False
~~~~~

### 下一步建议
代码已重构完成。现在 TUI 应该具备了防抖和无闪烁的特性。
请运行 `qd ui` 进行验证：
1.  按 `v` 打开内容面板。
2.  **快速**按住 `j` 或 `k` 键上下滚动列表。
    *   **预期**：右侧内容面板应该保持静止（显示上一个加载的节点内容），或者仅更新顶部的 Header，而 Markdown 主体部分不应出现空白或闪烁。
    *   **预期**：不应感到卡顿。
3.  **停止**滚动。
    *   **预期**：在短暂的延迟后（约 0.2 秒），内容面板应瞬间更新为当前节点的内容。
