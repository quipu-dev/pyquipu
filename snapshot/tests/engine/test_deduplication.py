from pyquipu.engine.state_machine import Engine

from tests.helpers import EMPTY_TREE_HASH


class TestDeduplication:
    def test_idempotent_plan_creation(self, engine_instance: Engine):
        """
        验证当 output_tree == input_tree 时（即操作未产生文件变更），
        Engine 仍然能够生成一个新的 Plan 节点，并在历史图谱中正确链接。
        """
        engine = engine_instance
        root_dir = engine.root_dir

        # 1. State A: Create a file
        (root_dir / "a.txt").write_text("A")
        hash_a = engine.git_db.get_tree_hash()

        # 通过 Engine 创建第一个节点
        node_a = engine.create_plan_node(
            input_tree=EMPTY_TREE_HASH, output_tree=hash_a, plan_content="Create A", summary_override="Plan A"
        )

        # 验证初始状态
        assert len(engine.history_graph) == 1
        assert engine.current_node == node_a

        # 2. State A (Idempotent): No changes
        # 我们再次调用 create_plan_node，传入相同的 hash_a
        node_b = engine.create_plan_node(
            input_tree=hash_a,
            output_tree=hash_a,  # Same as input!
            plan_content="Read A (No Change)",
            summary_override="Plan B (Idempotent)",
        )

        # 3. 验证
        # 图谱中应该有两个节点
        assert len(engine.history_graph) == 2

        # 验证最新的节点
        assert node_b.commit_hash != node_a.commit_hash
        assert node_b.input_tree == hash_a
        assert node_b.output_tree == hash_a
        assert node_b.node_type == "plan"

        # 验证父子关系
        assert node_b.parent == node_a
        assert node_a.children == [node_b]
