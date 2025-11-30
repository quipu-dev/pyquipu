from pathlib import Path

from pyquipu.cli.controller import run_quipu


class TestIdempotentNode:
    def test_idempotent_plan_creation(self, tmp_path: Path):
        """验证无文件变更的操作也能生成历史节点"""
        # 1. 初始化环境
        workspace = tmp_path / "ws"
        workspace.mkdir()
        import subprocess

        subprocess.run(["git", "init"], cwd=workspace, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@quipu.dev"], cwd=workspace, check=True)
        subprocess.run(["git", "config", "user.name", "Quipu Test"], cwd=workspace, check=True)

        # 2. 先执行一个会产生变更的操作 (State A)
        plan_1 = "```act\nwrite_file a.txt\n```\n```content\nA\n```"
        run_quipu(plan_1, workspace, yolo=True)

        # 使用正确的 Engine 设置来验证
        from pyquipu.cli.factory import create_engine

        engine1 = create_engine(workspace)
        nodes1 = engine1.reader.load_all_nodes()
        assert len(nodes1) >= 1

        # 3. 执行一个无变更的操作 (State A -> State A)
        plan_2 = "```act\nread_file a.txt\n```"
        result = run_quipu(plan_2, workspace, yolo=True)

        assert result.success is True

        # 4. 验证是否生成了新节点
        engine2 = create_engine(workspace)
        nodes2 = sorted(engine2.reader.load_all_nodes(), key=lambda n: n.timestamp)
        assert len(nodes2) == len(nodes1) + 1

        # 验证新节点的 input == output
        latest_node = nodes2[-1]
        assert latest_node.input_tree == latest_node.output_tree
        assert latest_node.node_type == "plan"
