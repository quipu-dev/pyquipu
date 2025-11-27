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
        vm = GraphViewModel(reader, current_hash=current_hash)
        vm.initialize()
        return vm

    return _factory


class TestUiReachability:
    def test_ui_uses_view_model_for_reachability(self, view_model_factory):
        """
        Tests that the UI correctly queries the ViewModel to check reachability.
        """
        # We define a simple graph where only 'a' and 'curr' are ancestors.
        # The ViewModel will be initialized with this information.
        node_root = QuipuNode("null", "root", datetime(2023, 1, 1), Path("f_root"), "plan")
        node_a = QuipuNode("root", "a", datetime(2023, 1, 2), Path("f_a"), "plan")
        node_b = QuipuNode("root", "b", datetime(2023, 1, 3), Path("f_b"), "plan")
        node_curr = QuipuNode("a", "curr", datetime(2023, 1, 4), Path("f_curr"), "plan")

        ancestors = {"curr", "a", "root"}
        view_model = view_model_factory(
            [node_root, node_a, node_b, node_curr], current_hash="curr", ancestors=ancestors
        )
        app = QuipuUiApp(view_model=view_model)

        # The app should now use the view_model's ancestor set to determine reachability.
        # Directly check the results from the ViewModel's method that the UI uses.
        assert app.view_model.is_reachable("curr") is True
        assert app.view_model.is_reachable("a") is True
        assert app.view_model.is_reachable("root") is True
        assert app.view_model.is_reachable("b") is False

    def test_filter_unreachable_nodes_in_populate(self, view_model_factory):
        """
        Tests the filtering logic within the _populate_table method.
        """
        # Graph: root -> a, root -> b (unreachable)
        node_root = QuipuNode("null", "root", datetime(2023, 1, 1), Path("f_root"), "plan")
        node_a = QuipuNode("root", "a", datetime(2023, 1, 2), Path("f_a"), "plan")
        node_b = QuipuNode("root", "b", datetime(2023, 1, 3), Path("f_b"), "plan")

        # 'b' is not in the ancestor set, so it's unreachable.
        ancestors = {"a", "root"}
        view_model = view_model_factory([node_root, node_a, node_b], current_hash="a", ancestors=ancestors)
        app = QuipuUiApp(view_model=view_model)
        app.show_unreachable = False  # Set to hide unreachable nodes

        # Simulate the loop from _populate_table to see which nodes would be rendered
        nodes_on_page = view_model.load_page(1)
        rendered_nodes = [
            node for node in nodes_on_page if app.show_unreachable or app.view_model.is_reachable(node.output_tree)
        ]

        # The nodes are sorted by timestamp desc, so page 1 is [b, a, root]
        assert node_b not in rendered_nodes
        assert node_a in rendered_nodes
        assert node_root in rendered_nodes