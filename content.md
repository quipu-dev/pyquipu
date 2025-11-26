## fix: 适配 UI 层以使用 GraphViewModel 实现分页与按需加载

### 用户需求
用户需要优化 Quipu UI 的启动性能，支持大规模历史记录的秒级启动和无限滚动，并能展示节点的私有数据（开发者意图）。

### 评论
这是一个涉及 UI 核心逻辑重构的高风险任务。我们将 `QuipuUiApp` 从“全量数据持有者”转变为“视图控制器”，将数据管理委托给 `GraphViewModel`。这将彻底解决启动慢和内存占用高的问题。

### 目标
1.  重构 `QuipuUiApp` 以使用 `GraphViewModel`。
2.  实现异步分页加载 (`load_more_data`) 和无限滚动。
3.  实现增量式 Git 图谱渲染。
4.  在 UI 中展示合并后的公共/私有内容。

### 基本原理
通过 MVVM 模式解耦视图和数据。`tui.py` 不再直接操作数据库或持有完整节点列表，而是向 `GraphViewModel` 请求数据。图谱渲染逻辑由全量重绘改为增量追加 (`self.tracks` 状态持久化)。

### 标签
#intent/refine #flow/ready #priority/high
#comp/cli #concept/ui #scope/ux
#ai/refine
#task/domain/ui #task/object/tui #task/action/refactor
#task/state/continue #task/status/active

---

### Script

#### Acts 1: 重写 tui.py 以适配 ViewModel

我们将使用 `write_file` 重写 `tui.py`，因为改动涉及类的初始化签名、核心渲染循环和事件处理结构，`patch_file` 过于脆弱。

主要变更点：
1.  **引入 `GraphViewModel`**：取代原有的 `nodes` 列表和 `content_loader`。
2.  **增量渲染**：维护 `self.tracks` 状态，`_populate_table` 改为追加模式。
3.  **异步加载**：使用 `worker` 进行数据加载，避免阻塞 UI。
4.  **滚动监听**：监听 `DataTable.Scroll` 事件触发下一页加载。

~~~~~act
write_file packages/quipu-cli/src/quipu/cli/tui.py
~~~~~
~~~~~content
import sys
from typing import List, Optional, Tuple
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, DataTable, Markdown, Static
from textual.containers import Horizontal, Vertical
from textual.binding import Binding
from textual.coordinate import Coordinate
from textual import on, work
from textual.worker import Worker, WorkerState

from quipu.core.models import QuipuNode
from .view_model import GraphViewModel

# 定义 UI 返回类型: (动作类型, 数据)
# 动作: "checkout" | "dump"
UiResult = Tuple[str, str]


class QuipuUiApp(App[Optional[UiResult]]):
    CSS = """
    #main-container {
        height: 100%;
    }
    
    DataTable { 
        height: 100%; 
        background: $surface; 
        border: none; 
    }

    /* Split Mode Styles */
    .split-mode #history-table {
        width: 50%;
    }

    #content-view {
        display: none; /* 默认隐藏右侧内容区 */
        width: 50%;
        height: 100%;
        border-left: solid $primary;
        background: $surface;
    }
    
    .split-mode #content-view {
        display: block;
    }

    #content-header {
        height: 1;
        background: $primary;
        color: $text;
        text-align: center;
        text-style: bold;
    }

    #content-body {
        height: 1fr;
        padding: 1;
        overflow-y: auto;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "退出"),
        Binding("c", "checkout_node", "检出节点"),
        Binding("enter", "checkout_node", "检出节点"),
        Binding("v", "toggle_view", "切换内容视图"),
        Binding("p", "dump_content", "输出内容(stdout)"),
        Binding("h", "toggle_hidden", "显隐非关联分支"),
        # Vim 风格导航
        Binding("k", "move_up", "上移", show=False),
        Binding("j", "move_down", "下移", show=False),
        Binding("up", "move_up", "上移", show=False),
        Binding("down", "move_down", "下移", show=False),
    ]

    def __init__(self, view_model: GraphViewModel):
        super().__init__()
        self.view_model = view_model
        
        # UI State
        self.is_split_mode = False
        self.current_selected_node: Optional[QuipuNode] = None
        self.show_unreachable = True  # 暂时保留此标记，虽然 VM 处理了可达性，但 UI 可能仍需控制过滤
        
        # Graph Rendering State (Incremental)
        self.tracks: List[Optional[str]] = []
        
        # Pagination State
        self.is_loading = False
        
        # Cache for row lookups
        self.node_by_filename = {}

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)

        # 使用 Horizontal 容器包裹列表和内容预览
        with Horizontal(id="main-container"):
            yield DataTable(id="history-table", cursor_type="row", zebra_stripes=False)

            with Vertical(id="content-view"):
                yield Static("Node Content", id="content-header")
                yield Markdown("", id="content-body")

        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        # 初始化列
        table.add_columns("Time", "Graph", "Node Info")
        
        # 初始化 VM 并加载第一页
        self.view_model.initialize()
        self.load_more_data()

    # --- Data Loading ---

    @work(exclusive=True)
    async def load_more_data(self) -> None:
        """异步加载更多数据"""
        if self.is_loading or not self.view_model.has_more_data():
            return

        self.is_loading = True
        self.query_one(Footer).value = "正在加载更多历史记录..."
        
        try:
            # 在后台线程加载数据
            new_nodes = self.view_model.load_next_page(size=50)
            
            # 回到主线程更新 UI
            if new_nodes:
                self.call_from_thread(self._append_nodes, new_nodes)
        finally:
            self.is_loading = False
            self.query_one(Footer).value = ""

    def _append_nodes(self, new_nodes: List[QuipuNode]):
        """将新节点追加到表格中"""
        table = self.query_one(DataTable)
        
        for node in new_nodes:
            # 更新本地查找缓存
            self.node_by_filename[str(node.filename)] = node
            
            # 渲染行
            row_data = self._render_node_row(node)
            table.add_row(*row_data, key=str(node.filename))

        # 如果是第一次加载，尝试聚焦到 HEAD
        if table.cursor_row == 0 and self.view_model.current_hash:
             self._focus_current_node(table)

    def _render_node_row(self, node: QuipuNode) -> List[str]:
        """增量渲染单行数据"""
        is_reachable = self.view_model.is_reachable(node.output_tree)
        dim_tag = "[dim]" if not is_reachable else ""
        end_dim_tag = "[/dim]" if dim_tag else ""

        base_color = "magenta"
        if node.node_type == "plan":
            base_color = "green" if node.input_tree == node.output_tree else "cyan"

        # --- Graph Logic (Incremental) ---
        tracks = self.tracks
        
        merging_indices = [i for i, h in enumerate(tracks) if h == node.output_tree]
        try:
            col_idx = tracks.index(None) if not merging_indices else merging_indices[0]
        except ValueError:
            col_idx = len(tracks) if not merging_indices else merging_indices[0]

        while len(tracks) <= col_idx:
            tracks.append(None)
        tracks[col_idx] = node.output_tree

        graph_chars = []
        for i, track_hash in enumerate(tracks):
            if i == col_idx:
                symbol_char = "●" if node.node_type == "plan" else "○"
                graph_chars.append(f"{dim_tag}[{base_color}]{symbol_char}[/] {end_dim_tag}")
            elif i in merging_indices:
                graph_chars.append(f"{dim_tag}┘ {end_dim_tag}")
            elif track_hash:
                graph_chars.append(f"{dim_tag}│ {end_dim_tag}")
            else:
                graph_chars.append("  ")

        # 更新 tracks 状态以供下一行使用
        tracks[col_idx] = node.input_tree
        for i in merging_indices[1:]:
            tracks[i] = None
        while tracks and tracks[-1] is None:
            tracks.pop()
        
        # --- End Graph Logic ---

        ts_str = f"{dim_tag}{node.timestamp.strftime('%Y-%m-%d %H:%M')}{end_dim_tag}"
        graph_str = "".join(graph_chars)
        
        summary = node.summary or "No description"
        tag_char = node.node_type.upper()
        info_text = f"[{base_color}][{tag_char}] {node.short_hash}[/{base_color}] - {summary}"
        info_str = f"{dim_tag}{info_text}{end_dim_tag}"

        return [ts_str, graph_str, info_str]

    # --- Actions ---

    def action_move_up(self) -> None:
        self.query_one(DataTable).action_cursor_up()

    def action_move_down(self) -> None:
        self.query_one(DataTable).action_cursor_down()

    def action_toggle_hidden(self) -> None:
        # TODO: 由于现在是增量加载，简单的隐藏逻辑可能不再适用或需要重新实现过滤
        # 暂时只做标记反转，未来可以在 VM 中实现过滤
        self.show_unreachable = not self.show_unreachable
        # 提示用户
        status = "显示" if self.show_unreachable else "隐藏"
        self.notify(f"已切换不可达节点显示: {status} (需刷新生效，功能开发中)")

    def action_toggle_view(self) -> None:
        """切换分栏预览模式"""
        self.is_split_mode = not self.is_split_mode
        container = self.query_one("#main-container")
        
        if self.is_split_mode:
            container.add_class("split-mode")
            self._update_content_view()
        else:
            container.remove_class("split-mode")

    def action_checkout_node(self) -> None:
        if self.current_selected_node:
            self.exit(result=("checkout", self.current_selected_node.output_tree))

    def action_dump_content(self) -> None:
        if self.current_selected_node:
            content = self.view_model.get_content_bundle(self.current_selected_node)
            self.exit(result=("dump", content))

    # --- Event Handlers ---

    @on(DataTable.RowHighlighted)
    def on_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        row_key = event.row_key.value
        node = self.node_by_filename.get(row_key)
        if node:
            self.current_selected_node = node
            if self.is_split_mode:
                self._update_content_view()

    @on(DataTable.Scroll)
    def on_data_table_scroll(self, event: DataTable.Scroll) -> None:
        """监听滚动事件实现无限加载"""
        # 当滚动位置接近底部 (倒数 10 行) 时触发加载
        table = self.query_one(DataTable)
        if table.row_count > 0:
            # event.y 是滚动位置，table.size.height 是可视区域高度
            # 简单的判断：如果 (total_rows - scroll_y) < buffer
            # 注意：DataTable 的滚动计算比较复杂，这里使用简化阈值
            
            # 使用 table.scroll_offset 获取精确滚动坐标
            scroll_y = table.scroll_offset.y
            visible_height = table.size.height
            total_height = table.row_count # 假设行高为 1
            
            if (total_height - scroll_y - visible_height) < 10:
                self.load_more_data()

    def _focus_current_node(self, table: DataTable):
        if not self.view_model.current_hash:
            return
            
        # 尝试在已加载的节点中找到 current_hash
        # 注意：由于现在节点是动态加载的，current_hash 可能尚未加载
        # 这里只在其出现在第一页时有效
        for key, node in self.node_by_filename.items():
            if node.output_tree == self.view_model.current_hash:
                try:
                    row_index = table.get_row_index(key)
                    table.cursor_coordinate = Coordinate(row=row_index, column=0)
                    self.current_selected_node = node
                except Exception:
                    pass
                break

    def _update_content_view(self):
        if not self.current_selected_node:
            return

        node = self.current_selected_node
        header = self.query_one("#content-header", Static)
        header.update(f"[{node.node_type.upper()}] {node.short_hash} - {node.timestamp}")

        # 使用 Worker 异步加载内容，避免 UI 卡顿
        self._load_content_async(node)

    @work(exclusive=True)
    async def _load_content_async(self, node: QuipuNode):
        markdown_widget = self.query_one("#content-body", Markdown)
        markdown_widget.update("Loading content...")
        
        # 在 VM 中获取内容 bundle
        content = self.view_model.get_content_bundle(node)
        
        # 回到 UI 线程更新
        self.call_from_thread(markdown_widget.update, content)

~~~~~

### 下一步建议
现在 `tui.py` 已经准备好使用 `GraphViewModel`。下一步必须执行 **Phase 4: 集成与测试**，特别是更新 `packages/quipu-cli/src/quipu/cli/main.py` 以正确实例化新的 `QuipuUiApp` 并注入 `GraphViewModel`，否则 `quipu ui` 命令将无法运行。
