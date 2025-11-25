import pytest
from pathlib import Path
from datetime import datetime
from typing import Dict
from quipu.core.history import load_all_history_nodes
from quipu.core.models import QuipuNode

@pytest.fixture
def graph_history_dir(tmp_path: Path) -> Path:
    """
    创建一个模拟的历史目录，包含一个分叉的图结构：
    A -> B
      -> C (C 比 B 新)
    """
    history_dir = tmp_path / "history"
    history_dir.mkdir()
    
    hash_a = "a" * 40
    hash_b = "b" * 40
    hash_c = "c" * 40
    genesis = "_" * 40

    # 节点 A (根)
    (history_dir / f"{genesis}_{hash_a}_20230101000000.md").write_text("---\ntype: plan\n---")
    # 节点 B (A 的子节点)
    (history_dir / f"{hash_a}_{hash_b}_20230101010000.md").write_text("---\ntype: plan\n---")
    # 节点 C (A 的子节点, C is newer than B)
    (history_dir / f"{hash_a}_{hash_c}_20230101020000.md").write_text("---\ntype: plan\n---")
    
    return history_dir


class TestGraphLoader:

    def test_graph_loading_and_linking(self, graph_history_dir: Path):
        # `load_all_history_nodes` is now the main function for loading and linking
        all_nodes = load_all_history_nodes(graph_history_dir)
        
        # Rebuild the graph map for easy lookup, similar to how Engine does it.
        graph: Dict[str, QuipuNode] = {}
        for node in all_nodes:
            if node.output_tree not in graph or node.timestamp > graph[node.output_tree].timestamp:
                graph[node.output_tree] = node

        assert len(graph) == 3
        
        hash_a = "a" * 40
        hash_b = "b" * 40
        hash_c = "c" * 40
        
        node_a = graph[hash_a]
        node_b = graph[hash_b]
        node_c = graph[hash_c]
        
        # 1. 验证父子关系
        assert node_a.parent is None
        assert node_b.parent == node_a
        assert node_c.parent == node_a
        
        # 2. 验证子节点列表
        assert len(node_a.children) == 2
        # 验证子节点已按时间戳排序
        assert node_a.children == [node_b, node_c]
        assert len(node_b.children) == 0
        assert len(node_c.children) == 0
        
        # 3. 验证兄弟关系
        assert node_b.siblings == [node_b, node_c]
        assert node_c.siblings == [node_b, node_c]
        # 根节点没有兄弟
        assert node_a.siblings == [node_a]