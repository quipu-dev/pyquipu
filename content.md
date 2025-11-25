这是一个细致的 UI 优化需求。我们将引入“可达性分析”逻辑，并在 `AxonUiApp` 中添加状态过滤功能。

### 1. 修改 `ui/tui.py`

我们需要做以下改动：
1.  **计算可达集 (`reachable_hashes`)**: 包含当前节点的所有祖先（Undo 路径）和所有后代（Redo 路径）。
2.  **样式变暗**: 在渲染时，如果节点不在可达集中，使用 `[dim]` 样式。
3.  **切换显隐**: 添加 `h` 快捷键，切换是否完全隐藏不可达节点。

~~~act
write_file
~~~
~~~path
ui/tui.py
~~~
~~~python
import sys
from datetime import datetime
from typing import List, Optional, Set
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, DataTable
from textual.binding import Binding

# 确保能从上级目录导入 core 模块
sys.path.append('..')
from core.models import AxonNode

class AxonUiApp(App):
    """
    Axon Timeline Explorer
    一个基于 DataTable 的时间轴历史浏览器，支持分支视图、状态高亮和可达性过滤。
    """

    CSS = """
    DataTable {
        height: 100%;
        background: $surface;
        border: none;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "退出"),
        Binding("c", "checkout_node", "检出节点"),
        Binding("enter", "checkout_node", "检出节点"),
        Binding("h", "toggle_hidden", "显隐非关联分支"), # New binding
        Binding("up", "cursor_up", "上移", show=False),
        Binding("down", "cursor_down", "下移", show=False),
    ]

    def __init__(self, nodes: List[AxonNode], current_hash: Optional[str] = None):
        super().__init__()
        self.nodes = nodes # Keep original unsorted list for graph reconstruction if needed
        self.sorted_nodes = sorted(nodes, key=lambda n: n.timestamp, reverse=True)
        self.current_hash = current_hash
        self.node_map = {node.output_tree: node for node in nodes}
        
        # 状态控制
        self.show_unreachable = True # 默认显示但变暗
        
        # 计算可达性集合 (Undo/Redo 路径上的所有节点)
        self.reachable_hashes = self._calculate_reachable_hashes()

    def _calculate_reachable_hashes(self) -> Set[str]:
        """
        计算从当前节点出发，通过 Undo (祖先) 或 Redo (后代) 可达的所有节点哈希。
        """
        if not self.current_hash or self.current_hash not in self.node_map:
            return set()

        current_node = self.node_map[self.current_hash]
        reachable = {current_node.output_tree}

        # 1. 向上追溯 (Ancestors / Undo Path)
        curr = current_node
        while curr.parent:
            curr = curr.parent
            reachable.add(curr.output_tree)

        # 2. 向下扩散 (Descendants / Redo Path)
        # 使用 BFS 遍历所有后代
        queue = [current_node]
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
        """切换是否隐藏不可达节点"""
        self.show_unreachable = not self.show_unreachable
        self._refresh_table()

    def _refresh_table(self):
        """清空并重新填充表格"""
        table = self.query_one(DataTable)
        table.clear()
        self._populate_table(table)
        self._focus_current_node(table)

    def _populate_table(self, table: DataTable):
        """
        构建时间轴视图。
        """
        # 筛选需要显示的节点
        nodes_to_render = []
        for node in self.sorted_nodes:
            is_reachable = node.output_tree in self.reachable_hashes
            if not self.show_unreachable and not is_reachable:
                continue
            nodes_to_render.append(node)

        # 轨道追踪逻辑
        tracks: List[Optional[str]] = []

        for node in nodes_to_render:
            node_hash = node.output_tree
            parent_hash = node.input_tree
            is_reachable = node_hash in self.reachable_hashes

            # 确定样式前缀
            # 如果不可达，且模式为显示所有(即Dim模式)，则添加 [dim]
            # 注意：如果 self.show_unreachable 为 False，不可达节点根本不会进入此循环
            dim_tag = "[dim]" if (self.show_unreachable and not is_reachable) else ""
            end_dim_tag = "[/dim]" if dim_tag else ""

            # --- 1. 轨道分配 ---
            merging_indices = [i for i, h in enumerate(tracks) if h == node_hash]
            
            if merging_indices:
                col_idx = merging_indices[0]
            else:
                try:
                    col_idx = tracks.index(None)
                    tracks[col_idx] = node_hash
                except ValueError:
                    tracks.append(node_hash)
                    col_idx = len(tracks) - 1
                    
            # --- 2. 生成图形 ---
            graph_chars = []
            for i, track_hash in enumerate(tracks):
                if track_hash is None:
                    graph_chars.append("  ")
                    continue
                
                # 确定基础符号
                if i == col_idx:
                    symbol = "●" if node.node_type == 'plan' else "○"
                    # 基础颜色
                    color = "cyan" if node.node_type == 'plan' else "magenta"
                    symbol = f"[{color}]{symbol}[/]"
                    
                    # 组合: Dim + Color + Symbol
                    # 例如 [dim][cyan]●[/][/dim]
                    cell_str = f"{dim_tag}{symbol} {end_dim_tag}"
                    graph_chars.append(cell_str)
                    
                elif i in merging_indices:
                    graph_chars.append(f"{dim_tag}┘ {end_dim_tag}") 
                else:
                    graph_chars.append(f"{dim_tag}│ {end_dim_tag}")

            graph_str = "".join(graph_chars)

            # --- 3. 更新轨道 ---
            tracks[col_idx] = parent_hash
            for i in merging_indices[1:]:
                tracks[i] = None
            while tracks and tracks[-1] is None:
                tracks.pop()

            # --- 4. 文本信息 ---
            ts_str = node.timestamp.strftime("%Y-%m-%d %H:%M:%S")
            # 时间戳也应用 dim
            ts_str = f"{dim_tag}{ts_str}{end_dim_tag}"
            
            node_type_code = "[P]" if node.node_type == "plan" else "[C]"
            short_hash = node.short_hash
            summary = self._get_node_summary(node)
            
            # Info 列颜色逻辑
            base_color = "cyan" if node.node_type == "plan" else "magenta"
            
            # 组合 Info 字符串
            # 结构: [dim] [color][P] hash[/] - summary [/dim]
            info_str = f"{dim_tag}[{base_color}]{node_type_code} {short_hash}[/] - {summary}{end_dim_tag}"

            table.add_row(ts_str, graph_str, info_str, key=node.output_tree)

    def _get_node_summary(self, node: AxonNode) -> str:
        content = node.content.strip()
        lines = content.split('\n')
        summary = "No description"
        if node.node_type == 'plan':
            for line in lines:
                clean_line = line.strip()
                if clean_line.startswith(('~~~', '```')): continue
                if clean_line: summary = clean_line; break
        elif node.node_type == 'capture':
            user_msg = ""
            for line in lines:
                if "### 💬 备注:" in line: continue
                if line.strip() and not line.startswith(('#', '`', '-')): user_msg = line.strip(); break
            summary = user_msg if user_msg else "Workspace Snapshot"
        return (summary[:60] + '...') if len(summary) > 60 else summary

    def _focus_current_node(self, table: DataTable):
        if not self.current_hash: return
        try:
            row_index = table.get_row_index(self.current_hash)
            table.move_cursor(row=row_index)
        except Exception: pass

    def action_checkout_node(self) -> None:
        table = self.query_one(DataTable)
        try:
            selected_hash = table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value
            if selected_hash: self.exit(result=selected_hash)
        except Exception: pass
~~~

### 2. 更新测试

我们需要更新测试逻辑，验证“可达性计算”是否正确。

~~~act
write_file
~~~
~~~path
tests/test_ui_reachability.py
~~~
~~~python
import pytest
from pathlib import Path
from datetime import datetime
from core.models import AxonNode
from ui.tui import AxonUiApp

class TestUiReachability:
    
    def test_calculate_reachable(self):
        """
        测试可达性计算逻辑:
        Tree Structure:
              Root
             /    \
            A      B
           /
        Current
        """
        root = AxonNode("null", "root", datetime(2023,1,1), Path("f"), "plan")
        
        node_a = AxonNode("root", "a", datetime(2023,1,2), Path("f"), "plan")
        node_a.parent = root
        root.children.append(node_a)
        
        node_b = AxonNode("root", "b", datetime(2023,1,3), Path("f"), "plan")
        node_b.parent = root
        root.children.append(node_b)
        
        node_current = AxonNode("a", "curr", datetime(2023,1,4), Path("f"), "plan")
        node_current.parent = node_a
        node_a.children.append(node_current)
        
        # Scenario 1: Focus on 'curr'
        # Reachable should be: curr, a, root (Ancestors) + (Descendants: None)
        # Unreachable: b
        app = AxonUiApp([root, node_a, node_b, node_current], current_hash="curr")
        reachable = app.reachable_hashes
        
        assert "curr" in reachable
        assert "a" in reachable
        assert "root" in reachable
        assert "b" not in reachable
        
        # Scenario 2: Focus on 'root'
        # Reachable: root + all descendants (a, b, curr)
        app_root = AxonUiApp([root, node_a, node_b, node_current], current_hash="root")
        reachable_root = app_root.reachable_hashes
        
        assert "curr" in reachable_root
        assert "b" in reachable_root
        
    def test_filter_unreachable(self):
        """测试 populate 时的过滤逻辑"""
        # Linear: A -> B
        node_a = AxonNode("root", "a", datetime(2023,1,1), Path("f"), "plan")
        node_b = AxonNode("a", "b", datetime(2023,1,2), Path("f"), "plan")
        # Link them manually as load_history_graph would
        node_b.parent = node_a
        node_a.children.append(node_b)
        
        # Focus on A. 
        # Reachable: A (self), B (descendant). 
        # Wait, if focus is A, B is reachable via Redo. Correct.
        
        # Let's make an unreachable node C (sibling of A)
        node_c = AxonNode("root", "c", datetime(2023,1,3), Path("f"), "plan")
        
        nodes = [node_a, node_b, node_c]
        app = AxonUiApp(nodes, current_hash="a")
        
        # 1. Default: Show all, but C is dim (logic handled in rendering string, hard to test here without inspecting Textual widgets deep state)
        # But we can check internal logic
        assert "c" not in app.reachable_hashes
        
        # 2. Toggle Hide
        app.action_toggle_hidden()
        assert app.show_unreachable is False
        
        # If we populate now, C should be skipped
        # We can simulate the loop from _populate_table
        rendered_nodes = []
        for n in app.sorted_nodes:
            is_reachable = n.output_tree in app.reachable_hashes
            if not app.show_unreachable and not is_reachable:
                continue
            rendered_nodes.append(n)
            
        assert node_a in rendered_nodes
        assert node_b in rendered_nodes
        assert node_c not in rendered_nodes
~~~