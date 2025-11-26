import pytest
from pathlib import Path
from datetime import datetime
from quipu.core.models import QuipuNode
from quipu.cli.tui import QuipuUiApp


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
        root = QuipuNode("null", "root", datetime(2023, 1, 1), Path("f"), "plan")

        node_a = QuipuNode("root", "a", datetime(2023, 1, 2), Path("f"), "plan")
        node_a.parent = root
        root.children.append(node_a)

        node_b = QuipuNode("root", "b", datetime(2023, 1, 3), Path("f"), "plan")
        node_b.parent = root
        root.children.append(node_b)

        node_current = QuipuNode("a", "curr", datetime(2023, 1, 4), Path("f"), "plan")
        node_current.parent = node_a
        node_a.children.append(node_current)

        # Scenario 1: Focus on 'curr'
        # Reachable should be: curr, a, root (Ancestors) + (Descendants: None)
        # Unreachable: b
        app = QuipuUiApp([root, node_a, node_b, node_current], content_loader=lambda n: "mock", current_hash="curr")
        reachable = app.reachable_hashes

        assert "curr" in reachable
        assert "a" in reachable
        assert "root" in reachable
        assert "b" not in reachable

        # Scenario 2: Focus on 'root'
        # Reachable: root + all descendants (a, b, curr)
        app_root = QuipuUiApp(
            [root, node_a, node_b, node_current], content_loader=lambda n: "mock", current_hash="root"
        )
        reachable_root = app_root.reachable_hashes

        assert "curr" in reachable_root
        assert "b" in reachable_root

    def test_filter_unreachable(self):
        """测试 populate 时的过滤逻辑"""
        # Linear: A -> B
        node_a = QuipuNode("root", "a", datetime(2023, 1, 1), Path("f"), "plan")
        node_b = QuipuNode("a", "b", datetime(2023, 1, 2), Path("f"), "plan")
        # Link them manually as load_history_graph would
        node_b.parent = node_a
        node_a.children.append(node_b)

        # Focus on A.
        # Reachable: A (self), B (descendant).
        # Wait, if focus is A, B is reachable via Redo. Correct.

        # Let's make an unreachable node C (sibling of A)
        node_c = QuipuNode("root", "c", datetime(2023, 1, 3), Path("f"), "plan")

        nodes = [node_a, node_b, node_c]
        app = QuipuUiApp(nodes, content_loader=lambda n: "mock", current_hash="a")

        # 1. Default: Show all, but C is dim (logic handled in rendering string, hard to test here without inspecting Textual widgets deep state)
        # But we can check internal logic
        assert "c" not in app.reachable_hashes

        # 2. Toggle Hide (Directly set property to avoid UI query error in test)
        app.show_unreachable = False

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
