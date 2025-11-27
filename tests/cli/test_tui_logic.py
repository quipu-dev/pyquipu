import pytest
from pathlib import Path
from datetime import datetime

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


class TestUiLogic:
    def test_graph_renderer_simple_linear(self, view_model_factory):
        """Smoke test for simple linear history rendering."""
        node_a = QuipuNode("root", "a", datetime(2023, 1, 1), Path("f1"), "plan")
        node_b = QuipuNode("a", "b", datetime(2023, 1, 2), Path("f2"), "plan")
        node_c = QuipuNode("b", "c", datetime(2023, 1, 3), Path("f3"), "plan")

        view_model = view_model_factory([node_a, node_b, node_c])
        app = QuipuUiApp(view_model=view_model)

        # This is a smoke test to ensure that instantiation and basic data processing
        # do not crash. With the new architecture, detailed rendering logic is harder
        # to assert without running the full Textual app.
        assert app.view_model.total_nodes == 3

    def test_graph_renderer_branching(self, view_model_factory):
        """Smoke test for branching history rendering."""
        node_a = QuipuNode("root", "a", datetime(2023, 1, 1), Path("f1"), "plan")
        node_b = QuipuNode("a", "b", datetime(2023, 1, 2), Path("f2"), "plan")
        node_c = QuipuNode("a", "c", datetime(2023, 1, 3), Path("f3"), "plan")

        view_model = view_model_factory([node_a, node_b, node_c])
        app = QuipuUiApp(view_model=view_model)

        # Smoke test
        assert app.view_model.total_nodes == 3

    def test_get_node_summary(self, view_model_factory):
        """
        Tests if the TUI correctly uses the pre-loaded summary field.
        """
        view_model = view_model_factory([])
        app = QuipuUiApp(view_model=view_model)

        # Case 1: Node with a pre-set summary
        node_with_summary = QuipuNode(
            "a", "b", datetime.now(), Path("f1"), "plan", summary="This is a pre-calculated summary."
        )
        assert app._get_node_summary(node_with_summary) == "This is a pre-calculated summary."

        # Case 2: Node with an empty summary
        node_without_summary = QuipuNode(
            "c",
            "d",
            datetime.now(),
            Path("f2"),
            "capture",
            summary="",  # Explicitly empty
        )
        assert app._get_node_summary(node_without_summary) == "No description"