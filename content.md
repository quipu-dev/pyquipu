# feat: TUI 内容查看与提取

## 用户需求
当前 `quipu ui` 仅显示历史节点的时间、拓扑图和摘要。用户无法查看节点的具体内容 (Plan 详情或 Capture 变更)，也无法将内容提取出来供外部工具使用。

## 评论
这是一个提升 TUI 实用性的关键功能。能够直接在终端预览 Markdown 内容将极大改善浏览历史的体验。

## 目标
1.  在 TUI 中增加“分栏预览模式”，按 `v` 键开启，左侧显示列表，右侧渲染 Markdown 内容。
2.  支持按 `p` 键将当前选中节点的内容输出到 stdout 并退出 TUI。
3.  保持 TUI 的响应速度，仅在需要时懒加载内容。

## 基本原理
*   **布局重构**: 使用 Textual 的 `Horizontal` 容器将主界面分为左右两栏。通过 CSS 的 `display` 属性控制右侧栏的显隐。
*   **懒加载**: 通过向 UI 注入 `content_loader` 回调（闭包包裹 `engine.reader`），避免初始化时加载所有节点的大文本内容。
*   **交互协议**: 扩展 `App.run()` 的返回值协议，从单一的 `Hash` 字符串变为 `(Action, Data)` 元组，以区分“检出”和“导出”操作。

## 标签
#comp/cli #concept/ui #scope/ux

---

## Script

### Acts 1: TUI 核心逻辑改造

重构 `tui.py`，引入分栏布局、内容加载器回调及新的按键绑定。

~~~~~act
write_file packages/quipu-cli/src/quipu/cli/tui.py
~~~~~
~~~~~python
import sys
from datetime import datetime
from typing import List, Optional, Set, Dict, Callable, Tuple
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, DataTable, Markdown, Static
from textual.containers import Horizontal, Vertical
from textual.binding import Binding
from textual.coordinate import Coordinate
from textual import on

from quipu.core.models import QuipuNode

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

    def __init__(
        self, 
        nodes: List[QuipuNode], 
        content_loader: Callable[[QuipuNode], str],
        current_hash: Optional[str] = None
    ):
        super().__init__()
        self.sorted_nodes = sorted(nodes, key=lambda n: n.timestamp, reverse=True)
        self.content_loader = content_loader
        self.current_hash = current_hash
        
        # 索引构建
        self.node_by_filename: Dict[str, QuipuNode] = {str(node.filename): node for node in nodes}
        self.nodes_by_output_hash: Dict[str, List[QuipuNode]] = {}
        for node in nodes:
            self.nodes_by_output_hash.setdefault(node.output_tree, []).append(node)
        
        # 状态
        self.show_unreachable = True
        self.is_split_mode = False
        self.current_selected_node: Optional[QuipuNode] = None
        self.reachable_hashes = self._calculate_reachable_hashes()

    def _calculate_reachable_hashes(self) -> Set[str]:
        if not self.current_hash or self.current_hash not in self.nodes_by_output_hash:
            return set()
        
        start_node = self.nodes_by_output_hash[self.current_hash][-1]
        reachable = {start_node.output_tree}
        curr = start_node
        while curr.parent:
            curr = curr.parent
            reachable.add(curr.output_tree)

        queue = [start_node]
        while queue:
            node = queue.pop(0)
            for child in node.children:
                reachable.add(child.output_tree)
                queue.append(child)
        return reachable

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
        self._refresh_table()

    # --- Actions ---

    def action_move_up(self) -> None:
        self.query_one(DataTable).action_cursor_up()

    def action_move_down(self) -> None:
        self.query_one(DataTable).action_cursor_down()

    def action_toggle_hidden(self) -> None:
        self.show_unreachable = not self.show_unreachable
        self._refresh_table()

    def action_toggle_view(self) -> None:
        """切换分栏预览模式"""
        self.is_split_mode = not self.is_split_mode
        
        container = self.query_one("#main-container")
        if self.is_split_mode:
            container.add_class("split-mode")
        else:
            container.remove_class("split-mode")
            
        # 记录当前行位置以便恢复
        table = self.query_one(DataTable)
        current_cursor_row = table.cursor_row
        
        # 刷新表格（列数会变化）
        self._refresh_table()
        
        # 尝试恢复光标位置
        if current_cursor_row < table.row_count:
            table.move_cursor(row=current_cursor_row)
        
        # 如果开启了预览，立即加载当前选中节点的内容
        if self.is_split_mode:
            self._update_content_view()

    def action_checkout_node(self) -> None:
        if self.current_selected_node:
            self.exit(result=("checkout", self.current_selected_node.output_tree))

    def action_dump_content(self) -> None:
        """退出 UI 并将当前选中节点的内容输出到 stdout"""
        if self.current_selected_node:
            content = self.content_loader(self.current_selected_node)
            self.exit(result=("dump", content))

    # --- UI Logic ---

    def _refresh_table(self):
        table = self.query_one(DataTable)
        table.clear(columns=True)
        
        # 在分栏模式下，隐藏详细信息列以节省空间
        cols = ["Time", "Graph"]
        if not self.is_split_mode:
            cols.append("Node Info")
            
        table.add_columns(*cols)
        self._populate_table(table)
        
        # 初始加载时定位到当前 HEAD
        if table.cursor_row == 0 and self.current_hash and not self.current_selected_node:
             self._focus_current_node(table)

    def _populate_table(self, table: DataTable):
        nodes_to_render = [
            node for node in self.sorted_nodes 
            if self.show_unreachable or node.output_tree in self.reachable_hashes
        ]
        tracks: List[Optional[str]] = []
        for node in nodes_to_render:
            is_reachable = node.output_tree in self.reachable_hashes
            dim_tag = "[dim]" if not is_reachable else ""
            end_dim_tag = "[/dim]" if dim_tag else ""
            
            base_color = "magenta"
            if node.node_type == "plan":
                base_color = "green" if node.input_tree == node.output_tree else "cyan"

            merging_indices = [i for i, h in enumerate(tracks) if h == node.output_tree]
            try: col_idx = tracks.index(None) if not merging_indices else merging_indices[0]
            except ValueError: col_idx = len(tracks) if not merging_indices else merging_indices[0]
            
            while len(tracks) <= col_idx: tracks.append(None)
            tracks[col_idx] = node.output_tree

            graph_chars = []
            for i, track_hash in enumerate(tracks):
                if i == col_idx:
                    symbol_char = "●" if node.node_type == 'plan' else "○"
                    graph_chars.append(f"{dim_tag}[{base_color}]{symbol_char}[/] {end_dim_tag}")
                elif i in merging_indices: graph_chars.append(f"{dim_tag}┘ {end_dim_tag}")
                elif track_hash: graph_chars.append(f"{dim_tag}│ {end_dim_tag}")
                else: graph_chars.append("  ")
            
            tracks[col_idx] = node.input_tree
            for i in merging_indices[1:]: tracks[i] = None
            while tracks and tracks[-1] is None: tracks.pop()

            ts_str = f"{dim_tag}{node.timestamp.strftime('%Y-%m-%d %H:%M')}{end_dim_tag}"
            
            row_data = [ts_str, "".join(graph_chars)]
            
            # 仅在非分栏模式下显示详细信息列
            if not self.is_split_mode:
                summary = self._get_node_summary(node)
                tag_char = node.node_type.upper()
                info_text = f"[{base_color}][{tag_char}] {node.short_hash}[/{base_color}] - {summary}"
                info_str = f"{dim_tag}{info_text}{end_dim_tag}"
                row_data.append(info_str)
            
            # 使用 filename 作为唯一的 key
            table.add_row(*row_data, key=str(node.filename))

    def _get_node_summary(self, node: QuipuNode) -> str:
        return node.summary or "No description"

    def _focus_current_node(self, table: DataTable):
        if not self.current_hash: return
        target_nodes = self.nodes_by_output_hash.get(self.current_hash, [])
        if not target_nodes: return
        latest_node = target_nodes[-1]
        try:
            row_index = table.get_row_index(str(latest_node.filename))
            table.cursor_coordinate = Coordinate(row=row_index, column=0)
            # 初始化选中状态
            self.current_selected_node = latest_node
        except Exception: pass

    @on(DataTable.RowHighlighted)
    def on_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """当用户在表格中移动光标时触发"""
        row_key = event.row_key.value
        node = self.node_by_filename.get(row_key)
        if node:
            self.current_selected_node = node
            # 如果右侧预览已打开，则更新内容
            if self.is_split_mode:
                self._update_content_view()

    def _update_content_view(self):
        if not self.current_selected_node:
            return
        
        # 更新标题栏
        node = self.current_selected_node
        header = self.query_one("#content-header", Static)
        header.update(f"[{node.node_type.upper()}] {node.short_hash} - {node.timestamp}")
        
        # 懒加载并渲染 Markdown 内容
        content = self.content_loader(node)
        markdown = self.query_one("#content-body", Markdown)
        markdown.update(content)
~~~~~

### Acts 2: CLI 控制器适配

修改 `main.py` 以注入内容加载器，并适配 UI 返回的新元组格式。

~~~~~act
replace packages/quipu-cli/src/quipu/cli/main.py
~~~~~
~~~~~python
@app.command()
def ui(
    ctx: typer.Context,
    work_dir: Annotated[
        Path,
        typer.Option(
            "--work-dir", "-w",
            help="操作执行的根目录（工作区）",
            file_okay=False,
            dir_okay=True,
            resolve_path=True
        )
    ] = DEFAULT_WORK_DIR,
):
    """
    以交互式 TUI 模式显示 Axon 历史图谱。
    """
    try:
        from .tui import QuipuUiApp
    except ImportError:
        typer.secho("❌ TUI 依赖 'textual' 未安装。", fg=typer.colors.RED, err=True)
        typer.secho("💡 请运行: pip install 'textual>=0.58.0'", err=True)
        ctx.exit(1)
        
    setup_logging()
    
    engine = create_engine(work_dir)
    all_nodes = engine.reader.load_all_nodes()
    
    if not all_nodes:
        typer.secho("📜 历史记录为空，无需启动 UI。", fg=typer.colors.YELLOW, err=True)
        ctx.exit(0)
        
    graph = engine.history_graph
    current_hash = engine.git_db.get_tree_hash()
    
    app_instance = QuipuUiApp(all_nodes, current_hash=current_hash)
    selected_hash = app_instance.run()

    if selected_hash:
        if selected_hash in graph:
            typer.secho(f"\n> TUI 请求检出到: {selected_hash[:7]}", err=True)
            _execute_visit(ctx, engine, selected_hash, f"正在导航到 TUI 选定节点: {selected_hash[:7]}")
        else:
            typer.secho(f"❌ 错误: 无法在历史图谱中找到目标哈希 {selected_hash[:7]}", fg=typer.colors.RED, err=True)
            ctx.exit(1)
~~~~~
~~~~~python
@app.command()
def ui(
    ctx: typer.Context,
    work_dir: Annotated[
        Path,
        typer.Option(
            "--work-dir", "-w",
            help="操作执行的根目录（工作区）",
            file_okay=False,
            dir_okay=True,
            resolve_path=True
        )
    ] = DEFAULT_WORK_DIR,
):
    """
    以交互式 TUI 模式显示 Axon 历史图谱。
    """
    try:
        from .tui import QuipuUiApp
    except ImportError:
        typer.secho("❌ TUI 依赖 'textual' 未安装。", fg=typer.colors.RED, err=True)
        typer.secho("💡 请运行: pip install 'textual>=0.58.0'", err=True)
        ctx.exit(1)
        
    setup_logging()
    
    engine = create_engine(work_dir)
    all_nodes = engine.reader.load_all_nodes()
    
    if not all_nodes:
        typer.secho("📜 历史记录为空，无需启动 UI。", fg=typer.colors.YELLOW, err=True)
        ctx.exit(0)
        
    graph = engine.history_graph
    current_hash = engine.git_db.get_tree_hash()
    
    # 定义内容加载器闭包，供 UI 按需调用
    def content_loader(node: QuipuNode) -> str:
        return engine.reader.get_node_content(node)
    
    # 注入 loader
    app_instance = QuipuUiApp(all_nodes, content_loader=content_loader, current_hash=current_hash)
    result = app_instance.run()

    # 处理 UI 返回结果
    if result:
        action, data = result
        
        if action == "checkout":
            target_hash = data
            if target_hash in graph:
                typer.secho(f"\n> TUI 请求检出到: {target_hash[:7]}", err=True)
                _execute_visit(ctx, engine, target_hash, f"正在导航到 TUI 选定节点: {target_hash[:7]}")
            else:
                typer.secho(f"❌ 错误: 无法在历史图谱中找到目标哈希 {target_hash[:7]}", fg=typer.colors.RED, err=True)
                ctx.exit(1)
                
        elif action == "dump":
            # 直接将内容打印到 stdout，方便用户通过管道处理 (e.g. quipu ui | less)
            print(data)
            ctx.exit(0)
~~~~~
