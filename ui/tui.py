import sys
from typing import List
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Tree
from textual.widgets.tree import TreeNode

# 确保能从上级目录导入 core 模块
sys.path.append('..')
from core.models import AxonNode

class AxonUiApp(App):
    """一个用于浏览 Axon 历史图谱的 Textual 应用。"""

    BINDINGS = [
        ("q", "quit", "退出"),
        ("c", "checkout_node", "检出选中节点"),
        ("enter", "checkout_node", "检出选中节点"),
    ]
    
    CSS = """
    Tree {
        width: 100%;
        height: 100%;
        background: $surface;
        padding: 1;
        border: tall $background-lighten-2;
    }
    """

    def __init__(self, graph_root_nodes: List[AxonNode]):
        super().__init__()
        self.root_nodes = graph_root_nodes

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Tree("🌳 Axon 历史图谱")
        yield Footer()

    def on_mount(self) -> None:
        """挂载时填充树状组件。"""
        tree = self.query_one(Tree)
        tree.show_root = False
        for root_node in self.root_nodes:
            self._populate_tree(tree.root, root_node)
        tree.root.expand_all()
        tree.focus()

    def _populate_tree(self, parent_treenode: TreeNode, axon_node: AxonNode):
        """递归地从 AxonNode 数据构建 TUI 树。"""
        node_type = axon_node.node_type.upper()
        icon = "⚡" if node_type == "PLAN" else "📸"
        
        label = f"{icon} [{node_type}] {axon_node.short_hash} - {axon_node.timestamp.strftime('%Y-%m-%d %H:%M')}"
        
        # 将 AxonNode 对象直接附加到 TUI 节点的数据上
        new_treenode = parent_treenode.add(label, data=axon_node)
        
        for child in axon_node.children:
            self._populate_tree(new_treenode, child)

    def action_checkout_node(self) -> None:
        """当用户按下 'c' 或 Enter 键时触发。"""
        tree = self.query_one(Tree)
        selected_axon_node: AxonNode = tree.cursor_node.data
        
        if selected_axon_node:
            # 退出应用，并返回选中的哈希值给主进程
            self.exit(result=selected_axon_node.output_tree)