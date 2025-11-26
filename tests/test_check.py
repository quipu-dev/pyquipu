import pytest
from pathlib import Path
from quipu.core.executor import Executor
from quipu.core.exceptions import ExecutionError
from quipu.acts.check import register as register_check_acts
from quipu.core.types import ActContext


class TestCheckActs:
    @pytest.fixture(autouse=True)
    def setup_executor(self, executor: Executor):
        """自动为每个测试注册 check acts"""
        register_check_acts(executor)

    def test_check_files_exist_success(self, executor: Executor, isolated_vault: Path):
        (isolated_vault / "config.json").touch()
        (isolated_vault / "src").mkdir()
        (isolated_vault / "src/main.py").touch()

        file_list = "config.json\nsrc/main.py"
        func, _, _ = executor._acts["check_files_exist"]
        ctx = ActContext(executor)
        func(ctx, [file_list])  # No exception should be raised

    def test_check_files_exist_fail(self, executor: Executor, isolated_vault: Path):
        (isolated_vault / "exists.txt").touch()
        file_list = "exists.txt\nmissing.txt"

        with pytest.raises(ExecutionError) as excinfo:
            func, _, _ = executor._acts["check_files_exist"]
            ctx = ActContext(executor)
            func(ctx, [file_list])

        msg = str(excinfo.value)
        assert "missing.txt" in msg
        assert "exists.txt" not in msg

    def test_check_cwd_match_success(self, executor: Executor, isolated_vault: Path):
        real_path = str(isolated_vault.resolve())
        func, _, _ = executor._acts["check_cwd_match"]
        ctx = ActContext(executor)
        func(ctx, [real_path])  # No exception should be raised

    def test_check_cwd_match_fail(self, executor: Executor):
        wrong_path = "/this/path/does/not/exist"

        with pytest.raises(ExecutionError) as excinfo:
            func, _, _ = executor._acts["check_cwd_match"]
            ctx = ActContext(executor)
            func(ctx, [wrong_path])

        assert "工作区目录不匹配" in str(excinfo.value)
