from unittest.mock import ANY, patch

import pytest
from pyquipu.application.controller import run_quipu
from pyquipu.interfaces.exceptions import ExecutionError


class TestControllerUnit:
    """
    对 Application 层 Controller 的纯单元测试。
    使用 Mock 替代真实的 Engine 和 Runtime，仅验证编排逻辑。
    """

    def test_run_quipu_success(self, tmp_path, mock_engine, mock_runtime):
        """测试正常执行流程：应正确初始化组件并按顺序调用。"""
        # 模拟 Parser 解析结果不为空，以避免 noStatements 警告
        # 注意：run_quipu 内部会调用 get_parser，这里为了简单，我们让 execute 被调用即可
        # 如果 run_quipu 内部有 parser 逻辑，我们假设 parser 是纯函数，不需要 mock，
        # 只要传入有效的 markdown 内容即可。

        plan_content = """
```act
echo
```
```text
hello
```
"""
        # Patch 工厂函数以返回我们的 Mock 对象
        with patch("pyquipu.application.controller.create_engine", return_value=mock_engine) as mk_eng_fac, \
             patch("pyquipu.application.controller.create_executor", return_value=mock_runtime) as mk_exec_fac:

            # 模拟 Engine 初始状态
            mock_engine.align.return_value = "CLEAN"

            # 执行
            result = run_quipu(
                content=plan_content,
                work_dir=tmp_path,  # 提供一个路径即可，不需要真实 Git 仓库
                yolo=True,
                confirmation_handler=lambda *a: True
            )

            # 验证结果
            assert result.success is True
            assert result.exit_code == 0

            # 验证交互
            mk_eng_fac.assert_called_once_with(tmp_path)
            mk_exec_fac.assert_called_once()
            
            # 验证编排顺序：Align -> Capture (Pre) -> Execute -> Capture (Post)
            mock_engine.align.assert_called()
            mock_runtime.execute.assert_called_once()
            # 至少调用一次 capture_drift (通常是两次，执行前和执行后，或者根据实现可能有变化)
            # 这里我们只断言它被调用了，作为副作用的记录
            assert mock_engine.capture_drift.called

    def test_run_quipu_execution_error(self, tmp_path, mock_engine, mock_runtime):
        """测试执行器抛出异常时的错误处理流程。"""
        plan_content = """
```act
fail_act
```
"""
        with patch("pyquipu.application.controller.create_engine", return_value=mock_engine), \
             patch("pyquipu.application.controller.create_executor", return_value=mock_runtime):

            # 模拟 Runtime 抛出业务异常
            mock_runtime.execute.side_effect = ExecutionError("Task failed successfully")

            result = run_quipu(
                content=plan_content,
                work_dir=tmp_path,
                yolo=True,
                confirmation_handler=lambda *a: True
            )

            # 验证错误被捕获并封装到 Result 中
            assert result.success is False
            assert result.exit_code == 1
            assert result.message == "run.error.execution"
            assert isinstance(result.error, ExecutionError)
            assert "Task failed successfully" in str(result.error)

    def test_run_quipu_empty_plan(self, tmp_path, mock_engine, mock_runtime):
        """测试空计划的处理。"""
        plan_content = "Just some text, no acts."

        with patch("pyquipu.application.controller.create_engine", return_value=mock_engine), \
             patch("pyquipu.application.controller.create_executor", return_value=mock_runtime):

            result = run_quipu(
                content=plan_content,
                work_dir=tmp_path,
                yolo=True,
                confirmation_handler=lambda *a: True
            )

            # 空计划通常不算失败，但也没有副作用
            assert result.success is True
            assert result.exit_code == 0
            assert result.message == "axon.warning.noStatements"
            
            # 验证没有调用 execute
            mock_runtime.execute.assert_not_called()