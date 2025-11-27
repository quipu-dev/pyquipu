import math
from typing import List, Optional, Set

from quipu.core.models import QuipuNode
from quipu.core.storage import HistoryReader


class GraphViewModel:
    """
    一个 ViewModel, 用于解耦 TUI (View) 和 HistoryReader (Model)。

    它负责管理分页状态、缓存可达性数据，并为 UI 提供简洁的数据接口。
    """

    def __init__(self, reader: HistoryReader, current_output_tree_hash: Optional[str], page_size: int = 50):
        self.reader = reader
        self.current_output_tree_hash = current_output_tree_hash
        self.page_size = page_size

        # 状态属性
        self.total_nodes: int = 0
        self.total_pages: int = 1
        self.current_page: int = 0  # 页码从 1 开始
        self.ancestor_set: Set[str] = set()

    def initialize(self):
        """
        初始化 ViewModel, 获取总数并计算可达性缓存。
        这是一个快速操作，因为它不加载任何节点内容。
        """
        self.total_nodes = self.reader.get_node_count()
        if self.page_size > 0 and self.total_nodes > 0:
            self.total_pages = math.ceil(self.total_nodes / self.page_size)
        else:
            self.total_pages = 1

        if self.current_output_tree_hash:
            # 后端直接计算祖先，避免在前端加载整个图谱
            self.ancestor_set = self.reader.get_ancestor_output_trees(self.current_output_tree_hash)
            # 当前节点本身也是可达的
            self.ancestor_set.add(self.current_output_tree_hash)

    def is_reachable(self, output_tree_hash: str) -> bool:
        """检查一个节点哈希是否在可达性集合中。"""
        if not self.current_output_tree_hash:
            # 如果没有当前状态 (例如，在创世之前)，将所有内容视为可达，
            # 以避免 UI 显示全灰色。
            return True
        return output_tree_hash in self.ancestor_set

    def load_page(self, page_number: int) -> List[QuipuNode]:
        """
        加载指定页码的数据，更新内部状态，并返回该页的节点列表。
        """
        if not (1 <= page_number <= self.total_pages):
            return []  # 页码无效

        self.current_page = page_number
        offset = (self.current_page - 1) * self.page_size

        nodes = self.reader.load_nodes_paginated(limit=self.page_size, offset=offset)
        return nodes

    def previous_page(self) -> List[QuipuNode]:
        """加载上一页的数据。"""
        return self.load_page(self.current_page - 1)

    def next_page(self) -> List[QuipuNode]:
        """加载下一页的数据。"""
        return self.load_page(self.current_page + 1)

    def get_content_bundle(self, node: QuipuNode) -> str:
        """
        获取节点的公共内容和私有内容，并将它们格式化成一个单一的字符串用于展示。
        """
        public_content = self.reader.get_node_content(node) or ""
        private_content = self.reader.get_private_data(node.commit_hash)

        if not public_content and not private_content:
            return "*此节点无详细内容*"

        # 构建最终的显示内容
        bundle = []
        if public_content:
            bundle.append("== 📜 公共计划内容=========")
            bundle.append(public_content.strip())

        if private_content is not None:
            if public_content:
                bundle.append("\n---\n")
            bundle.append("== 🧠 开发者意图===========")
            bundle.append(private_content.strip())
        elif public_content:
            # 仅当有公共内容时，才显示“无私有数据”的消息
            bundle.append("\n---\n")
            bundle.append("== 🧠 开发者意图===========")
            bundle.append("*此节点无私有数据或来自协作者*")

        return "\n\n".join(bundle)
