from abc import ABC, abstractmethod
from typing import List, Any
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