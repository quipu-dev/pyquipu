from abc import ABC, abstractmethod
from typing import List, Any, Optional, Set, Dict
import re
from .models import QuipuNode


class HistoryReader(ABC):
    """
    一个抽象接口，用于从存储后端读取历史图谱。
    """

    @abstractmethod
    def load_all_nodes(self) -> List[QuipuNode]:
        """
        从存储中加载所有历史事件，构建完整的父子关系图，
        并返回所有节点的列表。
        注意：为了性能，实现可能会选择不立即加载节点的 content 内容。
        """
        pass

    @abstractmethod
    def get_node_content(self, node: QuipuNode) -> str:
        """
        获取指定节点的完整内容 (Lazy Loading)。
        如果节点内容已加载，直接返回；否则从存储后端读取。
        """
        pass

    @abstractmethod
    def get_node_blobs(self, commit_hash: str) -> Dict[str, bytes]:
        """获取一个节点内所有文件的原始二进制内容，以字典形式返回 {filename: content_bytes}。"""
        pass

    @abstractmethod
    def find_nodes(
        self,
        summary_regex: Optional[str] = None,
        node_type: Optional[str] = None,
        limit: int = 10,
    ) -> List[QuipuNode]:
        """
        根据条件查找历史节点。
        """
        pass

    @abstractmethod
    def get_node_count(self) -> int:
        """
        获取历史节点总数。
        """
        pass

    @abstractmethod
    def load_nodes_paginated(self, limit: int, offset: int) -> List[QuipuNode]:
        """
        按需加载一页节点数据。
        注意：返回的节点应包含与直接父节点的关系，但不一定构建完整的全量图谱。
        """
        pass

    @abstractmethod
    def get_ancestor_output_trees(self, start_output_tree_hash: str) -> Set[str]:
        """
        获取指定状态节点的所有祖先节点的 output_tree 哈希集合 (用于可达性分析)。
        """
        pass

    @abstractmethod
    def get_private_data(self, node_commit_hash: str) -> Optional[str]:
        """
        获取指定节点的私有数据 (如 intent.md)。
        """
        pass

    @abstractmethod
    def get_descendant_output_trees(self, start_output_tree_hash: str) -> Set[str]:
        """
        获取指定状态节点的所有后代节点的 output_tree 哈希集合。
        """
        pass

    @abstractmethod
    def get_node_position(self, output_tree_hash: str) -> int:
        """
        获取指定节点在按时间倒序排列的全局列表中的索引位置（从 0 开始）。
        如果节点不存在，返回 -1。
        """
        pass


class HistoryWriter(ABC):
    """
    一个抽象接口，用于向历史存储后端写入一个新节点。
    """

    @abstractmethod
    def create_node(
        self,
        node_type: str,
        input_tree: str,
        output_tree: str,
        content: str,
        **kwargs: Any,
    ) -> QuipuNode:
        """
        在存储后端创建并持久化一个新的历史节点。

        Args:
            node_type: 节点的类型，例如 'plan' 或 'capture'。
            input_tree: 输入状态树的哈希。
            output_tree: 输出状态树的哈希。
            content: 节点的主要内容 (例如，Markdown 格式的计划) 。
            **kwargs: 针对特定节点类型的附加元数据，
                      例如 'capture' 节点的 'message'。

        Returns:
            新创建的 QuipuNode 实例。
        """
        pass
