import pytest
from pyquipu.acts.shell import register as register_shell_acts
from pyquipu.interfaces.exceptions import ExecutionError
from pyquipu.interfaces.types import ActContext
from pyquipu.runtime.executor import Executor


class TestShellActs:
    @pytest.fixture(autouse=True)
    def setup_executor(self, executor: Executor):
        register_shell_acts(executor)

    def test_run_command_success(self, executor: Executor, mock_runtime_bus):
        func, _, _ = executor._acts["run_command"]
        ctx = ActContext(executor)
        func(ctx, ["echo 'Hello Shell'"])

        mock_runtime_bus.info.assert_called_with("acts.shell.info.executing", command="echo 'Hello Shell'")
        mock_runtime_bus.data.assert_called_with("Hello Shell")

    def test_run_command_multiline_script(self, executor: Executor, isolated_vault, mock_runtime_bus):
        """验证多行脚本可以被正确执行。"""
        script = "touch file_a.txt\nmv file_a.txt file_b.txt"
        func, _, _ = executor._acts["run_command"]
        ctx = ActContext(executor)
        func(ctx, [script])

        assert not (isolated_vault / "file_a.txt").exists()
        assert (isolated_vault / "file_b.txt").exists()
        mock_runtime_bus.info.assert_called_with("acts.shell.info.executing", command=script)

    def test_run_command_does_not_swallow_blocks(self, executor: Executor, mock_runtime_bus):
        """
        验证 run_command 不会吞噬后续指令。
        这是一个更底层的测试，直接使用 executor.execute。
        """
        # 模拟解析器输出两个独立的指令
        statements = [
            {"act": "run_command", "contexts": ["echo 'first'"]},
            {"act": "echo", "contexts": ["second"]},
        ]
        executor.execute(statements)

        # 验证 run_command 的输出
        mock_runtime_bus.data.assert_any_call("first")
        # 验证第二个 echo 指令的输出
        mock_runtime_bus.data.assert_any_call("second")
        assert mock_runtime_bus.data.call_count == 2

    def test_run_command_failure(self, executor: Executor, mock_runtime_bus):
        func, _, _ = executor._acts["run_command"]
        ctx = ActContext(executor)

        # 验证失败返回码
        with pytest.raises(ExecutionError, match="acts.shell.error.failed"):
            func(ctx, ["exit 1"])

    def test_run_command_stderr(self, executor: Executor, mock_runtime_bus):
        # 构造一个向 stderr 输出的命令
        cmd = 'python3 -c "import sys; print(\'error msg\', file=sys.stderr)"'

        func, _, _ = executor._acts["run_command"]
        ctx = ActContext(executor)
        func(ctx, [cmd])

        # 检查是否捕获了 warning
        assert mock_runtime_bus.warning.called
        args, kwargs = mock_runtime_bus.warning.call_args
        assert args[0] == "acts.shell.warning.stderrOutput"
        assert "error msg" in kwargs["output"]

    def test_run_command_missing_args(self, executor: Executor):
        func, _, _ = executor._acts["run_command"]
        ctx = ActContext(executor)
        with pytest.raises(ExecutionError, match="acts.error.missingArgs"):
            func(ctx, [])