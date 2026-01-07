from unittest.mock import MagicMock, patch

from pyquipu.application.controller import run_quipu
from pyquipu.interfaces.exceptions import ExecutionError


class TestControllerUnit:
    """
    对 Application 层 Controller 的纯单元测试。
    使用 Mock 替代真实的 Engine 和 Runtime，仅验证编排逻辑。
    """

    def test_run_quipu_success(self, tmp_path, mock_engine, mock_runtime):
        """测试正常执行流程：应正确初始化组件并按顺序调用。"""

        plan_content = """
```act
echo
```
```text
hello
```
"""
        # 配置 Mock Engine 的状态以通过 _prepare_workspace 检查
        # 模拟当前是干净状态 (clean)
        mock_engine.git_db.get_tree_hash.return_value = "hash_123"
        mock_node = MagicMock()
        mock_node.output_tree = "hash_123"
        mock_engine.current_node = mock_node
        mock_engine.history_graph = {"hash_123": mock_node}

        # Patch 工厂函数和 Executor 类
        # 注意：controller 直接导入了 Executor 类，所以我们要 patch 这个类
        with (
            patch("pyquipu.application.controller.create_engine", return_value=mock_engine) as mk_eng_fac,
            patch("pyquipu.application.controller.Executor", return_value=mock_runtime) as mk_exec_cls,
        ):
            # 执行
            result = run_quipu(content=plan_content, work_dir=tmp_path, yolo=True, confirmation_handler=lambda *a: True)

            # 验证结果
            assert result.success is True
            assert result.exit_code == 0

            # 验证交互
            mk_eng_fac.assert_called_once_with(tmp_path)
            # Executor 类被实例化
            mk_exec_cls.assert_called_once()

            # 验证编排顺序
            # 1. _prepare_workspace 调用了 get_tree_hash
            mock_engine.git_db.get_tree_hash.assert_called()

            # 2. Executor 执行
            mock_runtime.execute.assert_called_once()

            # 3. 最后生成 Plan Node
            mock_engine.create_plan_node.assert_called_once()

    def test_run_quipu_execution_error(self, tmp_path, mock_engine, mock_runtime):
        """测试执行器抛出异常时的错误处理流程。"""
        plan_content = """
```act
fail_act
```
"""
        # 配置 Mock Engine
        mock_engine.git_db.get_tree_hash.return_value = "hash_123"
        mock_engine.current_node = MagicMock()
        mock_engine.current_node.output_tree = "hash_123"

        with (
            patch("pyquipu.application.controller.create_engine", return_value=mock_engine),
            patch("pyquipu.application.controller.Executor", return_value=mock_runtime),
        ):
            # 模拟 Runtime 抛出业务异常
            mock_runtime.execute.side_effect = ExecutionError("Task failed successfully")

            result = run_quipu(content=plan_content, work_dir=tmp_path, yolo=True, confirmation_handler=lambda *a: True)

            # 验证错误被捕获并封装到 Result 中
            assert result.success is False
            assert result.exit_code == 1
            assert result.message == "run.error.execution"
            assert isinstance(result.error, ExecutionError)
            assert "Task failed successfully" in str(result.error)

    def test_run_quipu_empty_plan(self, tmp_path, mock_engine, mock_runtime):
        """测试空计划的处理。"""
        plan_content = "Just some text, no acts."

        # 配置 Mock Engine
        mock_engine.git_db.get_tree_hash.return_value = "hash_123"
        mock_engine.current_node = MagicMock()
        mock_engine.current_node.output_tree = "hash_123"

        with (
            patch("pyquipu.application.controller.create_engine", return_value=mock_engine),
            patch("pyquipu.application.controller.Executor", return_value=mock_runtime),
        ):
            result = run_quipu(content=plan_content, work_dir=tmp_path, yolo=True, confirmation_handler=lambda *a: True)

            # 空计划通常不算失败，但也没有副作用
            assert result.success is True
            assert result.exit_code == 0
            assert result.message == "axon.warning.noStatements"

            # 验证没有调用 execute
            mock_runtime.execute.assert_not_called()
