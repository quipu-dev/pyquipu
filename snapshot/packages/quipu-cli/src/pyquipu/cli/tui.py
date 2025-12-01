import logging
from functools import partial
from pathlib import Path
from typing import List, Optional

from pyquipu.engine.state_machine import Engine
from pyquipu.interfaces.models import QuipuNode
from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.coordinate import Coordinate
from textual.timer import Timer
from textual.widgets import DataTable, Footer, Header, Markdown, Static

from .factory import create_engine
from .view_model import GraphViewModel

logger = logging.getLogger(__name__)

# 定义 UI 返回类型: (动作类型, 数据)
# 动作: "checkout" | "dump"
UiResult = tuple[str, str]


class QuipuUiApp(App[Optional[UiResult]]):
    CSS_PATH = "tui.css"
    TITLE = "Quipu History Explorer"

    # 1. 快捷键定义 (包含空格检出)
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

        # --- UI State ---
        self.markdown_enabled = not initial_raw_mode
        self.is_details_visible = False

        # --- Async & Debounce State ---
        self._debounce_timer: Optional[Timer] = None
        self._current_request_id: int = 0
        self._debounce_delay: float = 0.15

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="main-container"):
            yield DataTable(id="history-table", cursor_type="row", zebra_stripes=False)
            with Vertical(id="content-view"):
                yield Static("Node Content", id="content-header")
                # content-raw 用于 Raw 模式，content-body 用于 Markdown 模式
                # 两者在加载期间都不再会被清空
                yield Static("", id="content-raw", markup=False)
                yield Markdown("", id="content-body")
        yield Footer()

    def on_mount(self) -> None:
        """初始化数据并加载第一页"""
        logger.debug("TUI: on_mount started.")
        self.query_one(Header).tall = False

        # Lazy load engine
        self.engine = create_engine(self.work_dir, lazy=True)
        current_output_tree_hash = self.engine.git_db.get_tree_hash()
        self.view_model = GraphViewModel(reader=self.engine.reader, current_output_tree_hash=current_output_tree_hash)
        self.view_model.initialize()

        table = self.query_one(DataTable)
        table.add_columns("Time", "Graph", "Node Info")

        # 计算 HEAD 所在的页码并跳转
        initial_page = self.view_model.calculate_initial_page()
        self._load_page(initial_page)

        # 初始 UI 状态设置
        self._update_header_title()
        self._update_visibility_classes()

        table.focus()

    def on_unmount(self) -> None:
        if self.engine:
            self.engine.close()

    def _update_header_title(self):
        """更新顶部状态栏"""
        mode = "Markdown" if self.markdown_enabled else "Raw Text"
        self.sub_title = f"Page {self.view_model.current_page} / {self.view_model.total_pages} | View: {mode} (m)"

    def _update_visibility_classes(self):
        """根据当前状态控制面板显隐和组件切换"""
        container = self.query_one("#main-container")
        container.set_class(self.is_details_visible, "split-mode")

        raw_widget = self.query_one("#content-raw", Static)
        md_widget = self.query_one("#content-body", Markdown)

        if self.is_details_visible:
            if self.markdown_enabled:
                md_widget.display = True
                raw_widget.display = False
            else:
                md_widget.display = False
                raw_widget.display = True

    # --- Actions ---

    def action_move_up(self) -> None:
        self.query_one(DataTable).action_cursor_up()

    def action_move_down(self) -> None:
        self.query_one(DataTable).action_cursor_down()

    def action_toggle_hidden(self) -> None:
        self.view_model.toggle_unreachable()
        self._refresh_table()

    def action_toggle_markdown(self) -> None:
        self.markdown_enabled = not self.markdown_enabled
        self._update_header_title()
        self._update_visibility_classes()
        # 切换模式后立即触发重载，无需防抖
        if self.is_details_visible:
            self._trigger_content_load(immediate=True)

    def action_toggle_view(self) -> None:
        self.is_details_visible = not self.is_details_visible
        self._update_visibility_classes()
        if self.is_details_visible:
            self._trigger_content_load(immediate=True)

    def action_checkout_node(self) -> None:
        selected_node = self.view_model.get_selected_node()
        if selected_node:
            self.exit(result=("checkout", selected_node.output_tree))

    def action_dump_content(self) -> None:
        """改进后的内容提取：仅输出公共内容 (Cherry-pick)"""
        selected_node = self.view_model.get_selected_node()
        if selected_node:
            # 使用 ViewModel 的新方法 (假设 view_model.py 已更新)
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

    # --- Data & Rendering Logic ---

    def _load_page(self, page_number: int) -> None:
        self.view_model.load_page(page_number)
        self._refresh_table()

    def _refresh_table(self):
        table = self.query_one(DataTable)
        table.clear()
        nodes_to_render = self.view_model.get_nodes_to_render()
        self._populate_table(table, nodes_to_render)
        self._focus_current_node(table)
        self._update_header_title()

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
            
            owner_info = ""
            if node.owner_id:
                owner_info = f"[yellow]({node.owner_id[:12]}) [/yellow]"

            info_text = f"{owner_info}[{base_color}][{node.node_type.upper()}] {node.short_hash}[/{base_color}] - {node.summary or 'No description'}"
            info_str = f"{dim_tag}{info_text}{end_dim_tag}"
            
            table.add_row(ts_str, "".join(graph_chars), info_str, key=str(node.filename))

    def _get_graph_chars(self, tracks: list, node: QuipuNode, base_color: str, dim_tag: str, end_dim_tag: str) -> list[str]:
        # 简化的 Graph 渲染逻辑，保持与原版一致
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

    def _focus_current_node(self, table: DataTable):
        current_hash = self.view_model.current_output_tree_hash
        if not current_hash:
            return

        matching = [n for n in self.view_model.current_page_nodes if n.output_tree == current_hash]
        if not matching:
            return

        try:
            target_node = matching[0]
            row_key = str(target_node.filename)
            row_index = table.get_row_index(row_key)
            table.cursor_coordinate = Coordinate(row=row_index, column=0)
            
            # 手动触发一次选中逻辑，但不带防抖，直接加载
            self.view_model.select_node_by_key(row_key)
            if self.is_details_visible:
                self._trigger_content_load(immediate=True)
        except LookupError:
            pass

    # --- Async Loading & Debounce Logic ---

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
        """
        触发内容加载流程。
        immediate=True: 立即启动 Worker (用于切换视图模式等)
        immediate=False: 启动防抖计时器 (用于快速滚动)
        """
        if self._debounce_timer:
            self._debounce_timer.stop()
            self._debounce_timer = None

        if immediate:
            self._launch_worker()
        else:
            self._debounce_timer = self.set_timer(self._debounce_delay, self._launch_worker)

    def _launch_worker(self):
        """计时器结束，启动后台 Worker"""
        node = self.view_model.get_selected_node()
        if not node:
            return

        # 1. 生成新的请求 ID
        self._current_request_id += 1
        req_id = self._current_request_id

        # 2. 启动独占 Worker
        # 使用 partial 封装函数和参数，而不是直接调用
        worker_func = partial(self._load_content_in_background, node, req_id)
        
        self.run_worker(
            worker_func,
            thread=True,
            group="content_loader",
            exclusive=True
        )

    def _load_content_in_background(self, node: QuipuNode, req_id: int):
        """后台线程：执行耗时的 I/O 操作"""
        # 注意：这里调用 view_model 的方法，它会去读 DB/Git
        try:
            content_bundle = self.view_model.get_content_bundle(node)
            # 调度回主 UI 线程进行更新
            self.call_from_thread(self._update_content_ui, content_bundle, node, req_id)
        except Exception as e:
            logger.error(f"Error loading content for node {node.short_hash}: {e}")

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
