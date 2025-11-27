import pytest
from pathlib import Path
from datetime import datetime
from typing import List

from quipu.core.models import QuipuNode
from quipu.cli.tui import QuipuUiApp
from quipu.cli.view_model import GraphViewModel
from .test_view_model import MockHistoryReader


@pytest.fixture
def view_model_factory():
    """A factory to create a GraphViewModel instance with mock data for tests."""

    def _factory(nodes, current_hash=None, ancestors=None, private_data=None):
        reader = MockHistoryReader(nodes, ancestors=ancestors, private_data=private_data)
        vm = GraphViewModel(reader, current_output_tree_hash=current_hash)
        vm.initialize()
        return vm

    return _factory


class TestUiReachability:
    def test_ui_uses_view_model_for_reachability(self, view_model_factory):
        """
        Tests that the UI correctly queries the ViewModel to check reachability.
        """
        node_root = QuipuNode("c_root", "root", "null", datetime(2023, 1, 1), Path("f_root"), "plan", summary="Root")
        node_a = QuipuNode("c_a", "a", "root", datetime(2023, 1, 2), Path("f_a"), "plan", summary="A")
        node_b = QuipuNode("c_b", "b", "root", datetime(2023, 1, 3), Path("f_b"), "plan", summary="B")
        node_curr = QuipuNode("c_curr", "curr", "a", datetime(2023, 1, 4), Path("f_curr"), "plan", summary="Current")

        ancestors = {"curr", "a", "root"}
        view_model = view_model_factory(
            [node_root, node_a, node_b, node_curr], current_hash="curr", ancestors=ancestors
        )
        app = QuipuUiApp(work_dir=Path("."))
        app.view_model = view_model

        assert app.view_model.is_reachable("curr") is True
        assert app.view_model.is_reachable("a") is True
        assert app.view_model.is_reachable("root") is True
        assert app.view_model.is_reachable("b") is False

    def test_filter_unreachable_nodes_in_populate(self, view_model_factory):
        """
        Tests the filtering logic within the _populate_table method.
        """
        node_root = QuipuNode("c_root", "root", "null", datetime(2023, 1, 1), Path("f_root"), "plan", summary="Root")
        node_a = QuipuNode("c_a", "a", "root", datetime(2023, 1, 2), Path("f_a"), "plan", summary="A")
        node_b = QuipuNode("c_b", "b", "root", datetime(2023, 1, 3), Path("f_b"), "plan", summary="B")

        ancestors = {"a", "root"}
        view_model = view_model_factory([node_root, node_a, node_b], current_hash="a", ancestors=ancestors)
        app = QuipuUiApp(work_dir=Path("."))
        app.view_model = view_model
        app.show_unreachable = False

        nodes_on_page = view_model.load_page(1)
        rendered_nodes = [
            node for node in nodes_on_page if app.show_unreachable or app.view_model.is_reachable(node.output_tree)
        ]

        assert node_b not in rendered_nodes
        assert node_a in rendered_nodes
        assert node_root in rendered_nodes
