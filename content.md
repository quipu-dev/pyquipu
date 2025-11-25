# fix-test: 修复 TUI 重构后丢失的方法导致的测试失败

## 用户需求
在上次的功能添加中，对 `quipu.cli.tui.py` 的重构意外地移除了 `_get_node_summary` 方法，并过度简化了 `_populate_table` 方法中的图谱渲染逻辑，导致 `test_ui_logic.py` 中的一个测试用例失败。同时，切换显示非关联分支的功能 (`h` 键) 也丢失了。

## 评论
这是一个典型的重构回归 (Regression) 问题。在添加新功能时，破坏了现有功能并通过测试捕获。修复这个问题是保证代码质量的关键步骤。

## 目标
1.  将 `_get_node_summary` 方法重新添加回 `QuipuUiApp` 类中，以修复 `AttributeError`。
2.  恢复 `_populate_table` 方法中完整的、复杂的图谱绘制逻辑，确保分支、合并和非关联节点的视觉效果正确。
3.  恢复 `action_toggle_hidden` 方法及其绑定的 `h` 快捷键，让用户可以再次切换“显示/隐藏非关联分支”。
4.  确保所有新引入的分栏视图功能与恢复的旧功能正确集成。

## 基本原理
问题根源在于上次对 `tui.py` 的 `write_file` 操作中，使用了过度简化的实现，而不是将新旧逻辑仔细合并。本次修复将提供一个完整的、合并了新旧逻辑的 `tui.py` 文件内容，通过一次 `write_file` 操作直接修正所有问题。

## 标签
#comp/cli #comp/tests #concept/ui #scope/dx

---

## Script

### Acts 1: 恢复 TUI 模块的完整功能

我们将使用 `write_file` 覆盖 `packages/quipu-cli/src/quipu/cli/tui.py`，确保其包含所有必需的方法和逻辑。

~~~~~act
write_file packages/quipu-cli/src/quipu/cli/tui.py
~~~~~
~~~~~python
import sys
from datetime import datetime
from typing import List, Optional, Set, Dict, Callable, Tuple, Any

from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, DataTable, Markdown
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.coordinate import Coordinate

from quipu.core.models import QuipuNode

class QuipuUiApp(App):
    CSS_PATH = "tui.tcss"
    BINDINGS = [
        Binding("q", "quit", "退出"),
        Binding("v", "toggle_view", "切换视图"),
        Binding("p", "dump_content", "输出内容"),
        Binding("c", "checkout_node", "检出节点"),
        Binding("enter", "checkout_node", "检出节点"),
        Binding("h", "toggle_hidden", "显隐非关联分支"),
        Binding("tab", "focus_next", "切换焦点", show=False),
        Binding("up,k", "cursor_up", "上移", show=False),
        Binding("down,j", "cursor_down", "下移", show=False),
    ]

    def __init__(self, nodes: List[QuipuNode], current_hash: Optional[str] = None, content_fetcher: Optional[Callable[[QuipuNode], str]] = None):
        super().__init__()
        self.sorted_nodes = sorted(nodes, key=lambda n: n.timestamp, reverse=True)
        self.current_hash = current_hash
        self.content_fetcher = content_fetcher or (lambda n: "No content fetcher provided.")
        
        self.node_by_filename: Dict[str, QuipuNode] = {str(node.filename): node for node in nodes}
        self.nodes_by_output_hash: Dict[str, List[QuipuNode]] = {}
        for node in nodes:
            self.nodes_by_output_hash.setdefault(node.output_tree, []).append(node)
        
        self.show_unreachable = True
        self.reachable_hashes = self._calculate_reachable_hashes()
        
        # Write CSS file to disk for Textual to load
        css_content = """
        Screen {
            overflow: hidden;
        }
        #main-container {
            layout: horizontal;
            overflow: hidden;
        }
        #history-table {
            width: 100%;
            height: 100%;
            border-right: solid $accent-lighten-2;
        }
        #content-view {
            display: none;
            width: 0;
            height: 100%;
            padding: 0 1;
            overflow-y: auto;
        }
        #content-header {
            dock: top;
            width: 100%;
            height: auto;
            padding: 0 1;
            background: $surface-darken-2;
            color: $text-muted;
            text-style: bold;
            margin-bottom: 1;
        }
        #content-body {
            height: 100%;
        }
        Screen.-split-mode #history-table {
            width: 50%;
        }
        Screen.-split-mode #content-view {
            display: block;
            width: 50%;
        }
        """
        try:
            with open("tui.tcss", "w") as f:
                f.write(css_content)
        except Exception:
            pass

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
        with Horizontal(id="main-container"):
            yield DataTable(id="history-table", cursor_type="row", zebra_stripes=False)
            with Vertical(id="content-view"):
                yield Markdown(id="content-header", markdown="*Select a node*")
                yield Markdown(id="content-body")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.add_columns("Time", "Graph", "Node Info")
        self._refresh_table()

    def _get_selected_node(self) -> Optional[QuipuNode]:
        table = self.query_one(DataTable)
        if not table.row_count or not table.cursor_coordinate:
            return None
        try:
            filename_key = table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value
            return self.node_by_filename.get(filename_key)
        except Exception:
            return None

    def _refresh_table(self):
        table = self.query_one(DataTable)
        table.clear()
        self._populate_table(table)
        self._focus_current_node(table)
        self.query_one(DataTable).focus()

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

            ts_str = f"{dim_tag}{node.timestamp.strftime('%Y-%m-%d %H:%M:%S')}{end_dim_tag}"
            summary = self._get_node_summary(node)

            tag_char = node.node_type.upper()
            info_text = f"[{base_color}][{tag_char}] {node.short_hash}[/{base_color}] - {summary}"
            info_str = f"{dim_tag}{info_text}{end_dim_tag}"
            
            table.add_row(ts_str, "".join(graph_chars), info_str, key=str(node.filename))

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
        except Exception: pass
        
    async def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if self.has_class("-split-mode"):
            await self._update_content_view()
            
    async def _update_content_view(self):
        node = self._get_selected_node()
        if node:
            content = self.content_fetcher(node)
            header_md = f"**{node.short_hash}** - _{node.summary}_"
            self.query_one("#content-header", Markdown).update(header_md)
            self.query_one("#content-body", Markdown).update(content)
        else:
            self.query_one("#content-header", Markdown).update("*No node selected*")
            self.query_one("#content-body", Markdown).update("")

    async def action_toggle_view(self) -> None:
        self.screen.toggle_class("-split-mode")
        is_split = self.screen.has_class("-split-mode")
        table = self.query_one(DataTable)
        table.get_column("Node Info").visible = not is_split
        if is_split:
            await self._update_content_view()

    def action_toggle_hidden(self) -> None:
        self.show_unreachable = not self.show_unreachable
        self._refresh_table()

    def action_dump_content(self) -> None:
        node = self._get_selected_node()
        if node:
            content = self.content_fetcher(node)
            self.exit(result=("DUMP", content))

    def action_checkout_node(self) -> None:
        node = self._get_selected_node()
        if node:
            self.exit(result=("CHECKOUT", node.output_tree))

    def action_cursor_up(self) -> None:
        self.query_one(DataTable).action_cursor_up()

    def action_cursor_down(self) -> None:
        self.query_one(DataTable).action_cursor_down()

    def run(self) -> Tuple[Optional[str], Optional[Any]]:
        result = super().run()
        try:
            import os
            if os.path.exists("tui.tcss"):
                os.remove("tui.tcss")
        except Exception:
            pass
        return result or (None, None)
~~~~~
