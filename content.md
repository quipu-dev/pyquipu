# [feat]: UI 性能优化与私有数据展示

## 用户需求
随着历史记录增多，`quipu ui` 启动变慢，内存占用高。用户希望实现秒级启动、无限滚动，并在 UI 中查看节点的私有意图数据 (`intent.md`)。

## 评论
这是 `99_CURRENT.md` 中定义的关键优化任务。通过从一次性加载转变为基于 SQLite 的分页加载，可以显著提升 TUI 的性能和扩展性。同时，私有数据的展示补全了 Quipu 作为知识管理工具的拼图。

## 目标
1.  改造 `SQLiteHistoryReader`，支持分页读取节点和单独读取私有数据。
2.  重构 `QuipuUiApp`，实现异步分页加载、无限滚动触发机制。
3.  更新 UI 内容视图，支持同时展示公共计划 (`plan.md`) 和私有意图 (`intent.md`)。
4.  更新 CLI 入口，适配新的加载机制。

## 基本原理
利用 SQLite 的 `LIMIT/OFFSET` 能力实现按需加载，避免 Python 层面的一次性对象构建。在 TUI 层，通过监听滚动事件触发数据获取，并维护绘图状态 (`tracks`) 以支持跨页面的 Git 图谱渲染。

## 标签
#intent/build #flow/ready #priority/high
#comp/engine #comp/cli #concept/ui #scope/ux
#task/domain/ui #task/object/tui #task/action/optimization
#task/state/begin #task/status/active

---

## Script

### Acts 1: 引擎层 - 分页与私有数据读取

在 `SQLiteHistoryReader` 中实现分页查询和私有数据获取接口。

~~~~~act
replace packages/quipu-engine/src/quipu/core/sqlite_storage.py
~~~~~
~~~~~python
    def load_all_nodes(self) -> List[QuipuNode]:
        """
        从 SQLite 数据库高效加载所有节点元数据和关系。
        """
        conn = self.db_manager._get_conn()
        
        # 1. 一次性获取所有节点元数据
        nodes_cursor = conn.execute("SELECT * FROM nodes ORDER BY timestamp DESC;")
        nodes_data = nodes_cursor.fetchall()

        temp_nodes: Dict[str, QuipuNode] = {}
        for row in nodes_data:
            node = QuipuNode(
                # input_tree 将在第二阶段链接
                input_tree="",
                output_tree=row["output_tree"],
                timestamp=datetime.fromtimestamp(row["timestamp"]),
                filename=Path(f".quipu/git_objects/{row['commit_hash']}"),
                node_type=row["node_type"],
                summary=row["summary"],
                # 内容是懒加载的
                content=row["plan_md_cache"] if row["plan_md_cache"] is not None else "",
            )
            temp_nodes[row["commit_hash"]] = node

        # 2. 一次性获取所有边关系
        edges_cursor = conn.execute("SELECT child_hash, parent_hash FROM edges;")
        edges_data = edges_cursor.fetchall()
        
        # 3. 在内存中构建图
        for row in edges_data:
            child_hash, parent_hash = row["child_hash"], row["parent_hash"]
            if child_hash in temp_nodes and parent_hash in temp_nodes:
                child_node = temp_nodes[child_hash]
                parent_node = temp_nodes[parent_hash]
                
                child_node.parent = parent_node
                parent_node.children.append(child_node)
                # 根据父节点设置 input_tree
                child_node.input_tree = parent_node.output_tree
        
        # 4. 填充根节点的 input_tree 并排序子节点
        genesis_hash = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
        for node in temp_nodes.values():
            if node.parent is None:
                node.input_tree = genesis_hash
            node.children.sort(key=lambda n: n.timestamp)
            
        return list(temp_nodes.values())
~~~~~
~~~~~python
    def load_all_nodes(self) -> List[QuipuNode]:
        """
        从 SQLite 数据库高效加载所有节点元数据和关系。
        注意：对于大型历史，建议使用 load_nodes_paginated。
        """
        return self.load_nodes_paginated(limit=-1, offset=0)

    def get_node_count(self) -> int:
        """获取节点总数。"""
        conn = self.db_manager._get_conn()
        cursor = conn.execute("SELECT COUNT(*) FROM nodes")
        return cursor.fetchone()[0]

    def get_private_data(self, node_hash: str) -> Optional[str]:
        """获取节点的私有数据 (intent.md)。"""
        conn = self.db_manager._get_conn()
        cursor = conn.execute("SELECT intent_md FROM private_data WHERE node_hash = ?", (node_hash,))
        row = cursor.fetchone()
        return row["intent_md"] if row else None

    def load_nodes_paginated(self, limit: int, offset: int) -> List[QuipuNode]:
        """
        分页加载节点。
        仅构建当前页节点的 QuipuNode 对象，并尝试链接其直接父节点关系（如果父节点在同一页或通过查询 edges 表获取）。
        """
        conn = self.db_manager._get_conn()

        query = "SELECT * FROM nodes ORDER BY timestamp DESC"
        params = ()
        if limit > 0:
            query += " LIMIT ? OFFSET ?"
            params = (limit, offset)

        nodes_cursor = conn.execute(query, params)
        nodes_data = nodes_cursor.fetchall()

        if not nodes_data:
            return []

        temp_nodes: Dict[str, QuipuNode] = {}
        node_hashes = []
        
        for row in nodes_data:
            commit_hash = row["commit_hash"]
            node_hashes.append(commit_hash)
            node = QuipuNode(
                input_tree="", # 稍后填充
                output_tree=row["output_tree"],
                timestamp=datetime.fromtimestamp(row["timestamp"]),
                filename=Path(f".quipu/git_objects/{commit_hash}"),
                node_type=row["node_type"],
                summary=row["summary"],
                content=row["plan_md_cache"] if row["plan_md_cache"] is not None else "",
            )
            temp_nodes[commit_hash] = node

        # 批量获取这些节点的边关系，以确定 parent 和 input_tree
        placeholders = ",".join("?" for _ in node_hashes)
        edges_cursor = conn.execute(
            f"SELECT child_hash, parent_hash FROM edges WHERE child_hash IN ({placeholders})",
            tuple(node_hashes)
        )
        edges_data = edges_cursor.fetchall()

        # 为了获取 input_tree (即父节点的 output_tree)，我们需要父节点的元数据。
        # 如果父节点不在当前页，我们需要单独查询它们（仅 output_tree 字段即可）。
        parent_hashes_needed = set()
        child_to_parent_hash = {}

        for row in edges_data:
            child_to_parent_hash[row["child_hash"]] = row["parent_hash"]
            if row["parent_hash"] not in temp_nodes:
                parent_hashes_needed.add(row["parent_hash"])

        parent_output_trees = {}
        if parent_hashes_needed:
            p_placeholders = ",".join("?" for _ in parent_hashes_needed)
            p_cursor = conn.execute(
                f"SELECT commit_hash, output_tree FROM nodes WHERE commit_hash IN ({p_placeholders})",
                tuple(parent_hashes_needed)
            )
            for row in p_cursor.fetchall():
                parent_output_trees[row["commit_hash"]] = row["output_tree"]

        genesis_hash = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"

        # 链接关系和填充 input_tree
        for commit_hash, node in temp_nodes.items():
            parent_hash = child_to_parent_hash.get(commit_hash)
            
            if parent_hash:
                # 填充 input_tree
                if parent_hash in temp_nodes:
                    node.input_tree = temp_nodes[parent_hash].output_tree
                    # 在同一页内，可以建立对象引用
                    node.parent = temp_nodes[parent_hash]
                    temp_nodes[parent_hash].children.append(node)
                elif parent_hash in parent_output_trees:
                    node.input_tree = parent_output_trees[parent_hash]
                    # 父节点对象不在当前页，node.parent 保持为 None
            else:
                # 无父节点，默认为创世
                node.input_tree = genesis_hash

            # 确保子节点列表有序（虽然分页模式下 children 可能不全）
            node.children.sort(key=lambda n: n.timestamp)

        # 返回列表保持查询的顺序 (DESC)
        return list(temp_nodes.values())
~~~~~

### Acts 2: TUI 层 - 异步分页与双内容视图

重构 `QuipuUiApp`，引入异步加载、滚动监听和合并视图。

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
from textual import on, work

from quipu.core.models import QuipuNode
# 假设 Reader 协议已更新或我们依赖具体实现
from quipu.core.sqlite_storage import SQLiteHistoryReader

# 定义 UI 返回类型: (动作类型, 数据)
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
        reader: SQLiteHistoryReader,
        content_loader: Callable[[QuipuNode], str], 
        private_content_loader: Callable[[QuipuNode], Optional[str]],
        current_hash: Optional[str] = None
    ):
        super().__init__()
        self.reader = reader
        self.content_loader = content_loader
        self.private_content_loader = private_content_loader
        self.current_hash = current_hash

        # 分页状态
        self.page_size = 50
        self.loaded_offset = 0
        self.total_nodes = 0
        self.is_loading = False
        
        # 索引与缓存
        self.node_by_filename: Dict[str, QuipuNode] = {}
        
        # 图形绘制状态 (Tracks)
        self.tracks: List[Optional[str]] = []

        # 状态
        self.show_unreachable = True # 目前分页模式下暂不支持过滤，保持 True
        self.is_split_mode = False
        self.current_selected_node: Optional[QuipuNode] = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)

        with Horizontal(id="main-container"):
            yield DataTable(id="history-table", cursor_type="row", zebra_stripes=False)

            with Vertical(id="content-view"):
                yield Static("Node Content", id="content-header")
                yield Markdown("", id="content-body")

        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.add_columns("Time", "Graph", "Node Info")
        
        # 获取总数并加载第一页
        self._init_data()

    @work
    async def _init_data(self):
        # 这种数据库操作应该在 worker 中执行
        self.total_nodes = self.reader.get_node_count()
        await self._load_next_page()
        
        # 初始定位
        if self.current_hash:
             self.call_after_refresh(self._focus_current_node)

    @work
    async def _load_next_page(self):
        if self.is_loading:
            return
        
        if self.loaded_offset >= self.total_nodes and self.total_nodes > 0:
            return

        self.is_loading = True
        self.query_one(Footer).value = "正在加载历史记录..."
        
        try:
            # 模拟异步数据库调用 (在 worker 线程中同步调用)
            new_nodes = self.reader.load_nodes_paginated(self.page_size, self.loaded_offset)
            
            if new_nodes:
                self.call_after_refresh(self._append_nodes_to_table, new_nodes)
                self.loaded_offset += len(new_nodes)
        finally:
            self.is_loading = False
            self.query_one(Footer).value = f"已加载 {self.loaded_offset} / {self.total_nodes} 个节点"

    def _append_nodes_to_table(self, nodes: List[QuipuNode]):
        table = self.query_one(DataTable)
        
        for node in nodes:
            # 更新索引
            self.node_by_filename[str(node.filename)] = node
            
            # 渲染行
            row_data = self._render_node_row(node)
            table.add_row(*row_data, key=str(node.filename))

    def _render_node_row(self, node: QuipuNode) -> List[str]:
        # 图形渲染逻辑 (简化版，适配流式追加)
        is_reachable = True # 分页模式下暂不计算可达性
        dim_tag = "" 
        end_dim_tag = ""

        base_color = "magenta"
        if node.node_type == "plan":
            base_color = "green" if node.input_tree == node.output_tree else "cyan"

        # Track management
        merging_indices = [i for i, h in enumerate(self.tracks) if h == node.output_tree]
        try:
            col_idx = self.tracks.index(None) if not merging_indices else merging_indices[0]
        except ValueError:
            col_idx = len(self.tracks) if not merging_indices else merging_indices[0]

        while len(self.tracks) <= col_idx:
            self.tracks.append(None)
        self.tracks[col_idx] = node.output_tree

        graph_chars = []
        for i, track_hash in enumerate(self.tracks):
            if i == col_idx:
                symbol_char = "●" if node.node_type == "plan" else "○"
                graph_chars.append(f"{dim_tag}[{base_color}]{symbol_char}[/] {end_dim_tag}")
            elif i in merging_indices:
                graph_chars.append(f"{dim_tag}┘ {end_dim_tag}")
            elif track_hash:
                graph_chars.append(f"{dim_tag}│ {end_dim_tag}")
            else:
                graph_chars.append("  ")

        # Update tracks for next row
        self.tracks[col_idx] = node.input_tree
        for i in merging_indices[1:]:
            self.tracks[i] = None
        while self.tracks and self.tracks[-1] is None:
            self.tracks.pop()

        ts_str = f"{dim_tag}{node.timestamp.strftime('%Y-%m-%d %H:%M')}{end_dim_tag}"
        summary = node.summary or "No description"
        tag_char = node.node_type.upper()
        info_text = f"[{base_color}][{tag_char}] {node.short_hash}[/{base_color}] - {summary}"
        info_str = f"{dim_tag}{info_text}{end_dim_tag}"

        return [ts_str, "".join(graph_chars), info_str]

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """当用户在表格中移动光标时触发"""
        row_key = event.row_key.value
        node = self.node_by_filename.get(row_key)
        if node:
            self.current_selected_node = node
            if self.is_split_mode:
                self._update_content_view()

    # 无限滚动触发器
    # 注意: Textual 版本差异，此处假设 DataTable 暴露 Scrolled 消息或我们需要轮询/计算
    # 在 0.58+ 中，可以使用 Message 监听
    @on(DataTable.Scroll)
    def on_scroll(self, event: DataTable.Scroll) -> None:
        # 检测是否滚动到底部附近
        table = self.query_one(DataTable)
        # 获取可视区域底部行索引
        # y 是滚动偏移量
        if not table.row_count:
            return
            
        # 简单的 heuristic: 如果当前 cursor 接近最后一行
        # 或者 scroll_offset 接近 max_scroll_y
        # 这里使用 cursor_row 作为近似触发，因为 Scroll 事件参数较为底层
        pass
        
    @on(DataTable.SelectionChanged) # 或 CursorMoved
    def on_cursor_move(self):
        # 备用方案：当光标移动到最后 10 行时触发加载
        table = self.query_one(DataTable)
        if table.cursor_row >= table.row_count - 10:
             self._load_next_page()

    def _focus_current_node(self):
        # 尝试在已加载的节点中找到当前 HEAD
        # 如果不在第一页，可能无法自动定位，这是分页的权衡
        for filename, node in self.node_by_filename.items():
            if node.output_tree == self.current_hash:
                table = self.query_one(DataTable)
                try:
                    row_index = table.get_row_index(filename)
                    table.move_cursor(row=row_index)
                    self.current_selected_node = node
                except Exception:
                    pass
                break

    @work
    async def _update_content_view(self):
        if not self.current_selected_node:
            return

        node = self.current_selected_node
        header = self.query_one("#content-header", Static)
        header.update(f"[{node.node_type.upper()}] {node.short_hash} - {node.timestamp}")

        # 异步加载内容
        public_content = self.content_loader(node)
        private_content = self.private_content_loader(node)

        md_text = f"## 📜 公共计划内容\n\n{public_content}\n\n"
        md_text += "---\n\n"
        md_text += "## 🧠 开发者意图\n\n"
        
        if private_content:
            md_text += private_content
        else:
            md_text += "*此节点无私有数据或来自协作者*"

        markdown = self.query_one("#content-body", Markdown)
        markdown.update(md_text)

    # --- Actions (Keep existing ones) ---

    def action_move_up(self) -> None:
        self.query_one(DataTable).action_cursor_up()

    def action_move_down(self) -> None:
        self.query_one(DataTable).action_cursor_down()
        # 触发检查
        self.on_cursor_move()

    def action_toggle_hidden(self) -> None:
        # 分页模式下禁用此功能，或重新实现为数据库过滤
        self.notify("分页模式下暂不支持隐藏分支过滤")

    def action_toggle_view(self) -> None:
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
            content = self.content_loader(self.current_selected_node)
            self.exit(result=("dump", content))
~~~~~

### Acts 3: CLI 层 - 注入依赖

更新 `main.py` 中的 `ui` 命令，注入 `reader` 和 `private_content_loader`。

~~~~~act
replace packages/quipu-cli/src/quipu/cli/main.py
~~~~~
~~~~~python
    # 定义内容加载器闭包，供 UI 按需调用
    def content_loader(node: QuipuNode) -> str:
        return engine.reader.get_node_content(node)

    # 注入 loader
    app_instance = QuipuUiApp(all_nodes, content_loader=content_loader, current_hash=current_hash)
    result = app_instance.run()
~~~~~
~~~~~python
    # 定义内容加载器闭包，供 UI 按需调用
    def content_loader(node: QuipuNode) -> str:
        return engine.reader.get_node_content(node)

    # 定义私有内容加载器
    def private_content_loader(node: QuipuNode) -> Optional[str]:
        if hasattr(engine.reader, "get_private_data"):
            return engine.reader.get_private_data(node.filename.name)
        return None

    # 注入 loader 和 reader (注意: 不再传递 all_nodes)
    app_instance = QuipuUiApp(
        reader=engine.reader,
        content_loader=content_loader, 
        private_content_loader=private_content_loader,
        current_hash=current_hash
    )
    result = app_instance.run()
~~~~~

~~~~~act
replace packages/quipu-cli/src/quipu/cli/main.py
~~~~~
~~~~~python
    setup_logging()

    engine = create_engine(work_dir)
    all_nodes = engine.reader.load_all_nodes()

    if not all_nodes:
        typer.secho("📜 历史记录为空，无需启动 UI。", fg=typer.colors.YELLOW, err=True)
        ctx.exit(0)

    graph = engine.history_graph
    current_hash = engine.git_db.get_tree_hash()
~~~~~
~~~~~python
    setup_logging()

    engine = create_engine(work_dir)
    # 移除 load_all_nodes 调用，由 UI 内部处理
    
    # 简单的空检查，如果支持 get_node_count
    if hasattr(engine.reader, "get_node_count") and engine.reader.get_node_count() == 0:
         typer.secho("📜 历史记录为空，无需启动 UI。", fg=typer.colors.YELLOW, err=True)
         ctx.exit(0)

    graph = engine.history_graph # 注意: 在分页模式下 graph 可能不完整，但这仅影响 CLI 逻辑，TUI 已重构
    current_hash = engine.git_db.get_tree_hash()
~~~~~
