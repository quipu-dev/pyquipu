import sys
from datetime import datetime
from typing import List, Optional, Set, Dict
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, DataTable
from textual.binding import Binding
from textual.coordinate import Coordinate

from quipu.core.models import QuipuNode

class QuipuUiApp(App):
    CSS = """
    DataTable { height: 100%; background: $surface; border: none; }
    """
    BINDINGS = [
        Binding("q", "quit", "退出"),
        Binding("c", "checkout_node", "检出节点"),
        Binding("enter", "checkout_node", "检出节点"),
        Binding("h", "toggle_hidden", "显隐非关联分支"),
        Binding("up", "cursor_up", "上移", show=False),
        Binding("down", "cursor_down", "下移", show=False),
        Binding("k", "move_up", "上移", show=False),
        Binding("j", "move_down", "下移", show=False),
    ]

    def action_move_up(self) -> None:
        """在 DataTable 中上移光标。"""
        self.query_one(DataTable).action_cursor_up()

    def action_move_down(self) -> None:
        """在 DataTable 中下移光标。"""
        self.query_one(DataTable).action_cursor_down()

    def __init__(self, nodes: List[QuipuNode], current_hash: Optional[str] = None):
        super().__init__()
        self.sorted_nodes = sorted(nodes, key=lambda n: n.timestamp, reverse=True)
        self.current_hash = current_hash
        
        # 关键变更: 创建多个查找映射
        self.node_by_filename: Dict[str, QuipuNode] = {str(node.filename): node for node in nodes}
        self.nodes_by_output_hash: Dict[str, List[QuipuNode]] = {}
        for node in nodes:
            self.nodes_by_output_hash.setdefault(node.output_tree, []).append(node)
        
        self.show_unreachable = True
        self.reachable_hashes = self._calculate_reachable_hashes()

    def _calculate_reachable_hashes(self) -> Set[str]:
        if not self.current_hash or self.current_hash not in self.nodes_by_output_hash:
            return set()
        
        # 关键：一个 hash 可能对应多个节点，我们必须从最新的那个开始追溯
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
        yield DataTable(cursor_type="row", zebra_stripes=False)
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.add_columns("Time", "Graph", "Node Info")
        self._refresh_table()

    def action_toggle_hidden(self) -> None:
        self.show_unreachable = not self.show_unreachable
        self._refresh_table()

    def _refresh_table(self):
        table = self.query_one(DataTable)
        table.clear()
        self._populate_table(table)
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

            ts_str = f"{dim_tag}{node.timestamp.strftime('%Y-%m-%d %H:%M:%S')}{end_dim_tag}"
            summary = self._get_node_summary(node)

            # 修复: 明确关闭标签，避免 MarkupError
            tag_char = node.node_type.upper()
            # 1. 先创建内部的有色文本
            info_text = f"[{base_color}][{tag_char}] {node.short_hash}[/{base_color}] - {summary}"
            # 2. 然后安全地用 dim 标签包裹
            info_str = f"{dim_tag}{info_text}{end_dim_tag}"
            
            # 使用 filename 作为唯一的行 key
            table.add_row(ts_str, "".join(graph_chars), info_str, key=str(node.filename))

    def _get_node_summary(self, node: QuipuNode) -> str:
        content = node.content.strip()
        lines = content.split('\n')
        summary = "No description"
        if node.node_type == 'plan':
            for line in lines:
                clean_line = line.strip()
                if clean_line.startswith(('~~~', '```')): continue
                if clean_line: summary = clean_line; break
        elif node.node_type == 'capture':
            summary = next((line.strip() for line in lines if line.strip() and not line.startswith(('#', '`', '-', "###"))), "Workspace Snapshot")
        return (summary[:60] + '...') if len(summary) > 60 else summary

    def _focus_current_node(self, table: DataTable):
        if not self.current_hash: return
        # 关键修复: 根据 hash 找到最新的节点, 然后用该节点的 filename 来定位行
        target_nodes = self.nodes_by_output_hash.get(self.current_hash, [])
        if not target_nodes: return
        
        latest_node = target_nodes[-1] # 列表已按时间排序
        try:
            row_index = table.get_row_index(str(latest_node.filename))
            table.cursor_coordinate = Coordinate(row=row_index, column=0)
        except Exception: pass

    def action_checkout_node(self) -> None:
        table = self.query_one(DataTable)
        if not table.row_count: return
        try:
            # 关键修复: 从 filename key 映射回 output_tree hash
            filename_key = table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value
            selected_node = self.node_by_filename.get(filename_key)
            if selected_node:
                self.exit(result=selected_node.output_tree)
        except Exception: pass
