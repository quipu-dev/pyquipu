from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Set

from .models import QuipuNode


class HistoryReader(ABC):
    @abstractmethod
    def load_all_nodes(self) -> List[QuipuNode]:
        pass

    @abstractmethod
    def get_node_content(self, node: QuipuNode) -> str:
        pass

    @abstractmethod
    def get_node_blobs(self, commit_hash: str) -> Dict[str, bytes]:
        pass

    @abstractmethod
    def find_nodes(
        self,
        summary_regex: Optional[str] = None,
        node_type: Optional[str] = None,
        limit: int = 10,
    ) -> List[QuipuNode]:
        pass

    @abstractmethod
    def get_node_count(self) -> int:
        pass

    @abstractmethod
    def load_nodes_paginated(self, limit: int, offset: int) -> List[QuipuNode]:
        pass

    @abstractmethod
    def get_ancestor_output_trees(self, start_output_tree_hash: str) -> Set[str]:
        pass

    @abstractmethod
    def get_private_data(self, node_commit_hash: str) -> Optional[str]:
        pass

    @abstractmethod
    def get_descendant_output_trees(self, start_output_tree_hash: str) -> Set[str]:
        pass

    @abstractmethod
    def get_node_position(self, output_tree_hash: str) -> int:
        pass


class HistoryWriter(ABC):
    @abstractmethod
    def create_node(
        self,
        node_type: str,
        input_tree: str,
        output_tree: str,
        content: str,
        **kwargs: Any,
    ) -> QuipuNode:
        pass
