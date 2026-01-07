import pytest
from pyquipu.engine.state_machine import Engine


@pytest.fixture
def nav_workspace(engine_instance: Engine):
    engine = engine_instance
    repo_path = engine.root_dir

    # Helper to create distinct states
    def create_state(content: str) -> str:
        (repo_path / "file.txt").write_text(content)
        return engine.git_db.get_tree_hash()

    return engine, create_state


class TestNavigationEngine:
    def test_basic_back_and_forward(self, nav_workspace):
        engine, create_state = nav_workspace

        hash_a = create_state("A")
        hash_b = create_state("B")

        engine.visit(hash_a)
        engine.visit(hash_b)

        # We are at B, go back to A
        engine.back()
        assert (engine.root_dir / "file.txt").read_text() == "A"

        # We are at A, go forward to B
        engine.forward()
        assert (engine.root_dir / "file.txt").read_text() == "B"

    def test_boundary_conditions(self, nav_workspace):
        engine, create_state = nav_workspace

        hash_a = create_state("A")
        engine.visit(hash_a)

        # At the end, forward should do nothing
        assert engine.forward() is None
        assert (engine.root_dir / "file.txt").read_text() == "A"

        # At the beginning, back should do nothing
        assert engine.back() is None
        assert (engine.root_dir / "file.txt").read_text() == "A"

    def test_history_truncation_on_new_visit(self, nav_workspace):
        engine, create_state = nav_workspace

        hash_a = create_state("A")
        hash_b = create_state("B")
        hash_c = create_state("C")
        hash_d = create_state("D")

        engine.visit(hash_a)
        engine.visit(hash_b)
        engine.visit(hash_c)

        # History: [A, B, C], ptr at C

        # Go back to B
        engine.back()
        # History: [A, B, C], ptr at B

        # Now visit a new state D. This should truncate C.
        engine.visit(hash_d)
        # History: [A, B, D], ptr at D

        # Verify state
        assert (engine.root_dir / "file.txt").read_text() == "D"

        # Verify that forward is now impossible
        assert engine.forward() is None

        # Go back twice to verify the new history
        engine.back()  # -> B
        assert (engine.root_dir / "file.txt").read_text() == "B"
        engine.back()  # -> A
        assert (engine.root_dir / "file.txt").read_text() == "A"

    def test_visit_idempotency(self, nav_workspace):
        engine, create_state = nav_workspace
        hash_a = create_state("A")

        engine.visit(hash_a)
        engine.visit(hash_a)
        engine.visit(hash_a)

        log, _ = engine._read_nav()
        # The log might contain the initial HEAD, so we check the end
        assert log[-1] == hash_a
        assert len([h for h in log if h == hash_a]) <= 1
