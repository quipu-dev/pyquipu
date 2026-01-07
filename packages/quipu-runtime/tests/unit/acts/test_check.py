from pathlib import Path

import pytest
from pyquipu.acts.check import register as register_check_acts
from pyquipu.interfaces.exceptions import ExecutionError
from pyquipu.interfaces.types import ActContext
from pyquipu.runtime.executor import Executor


class TestCheckActs:
    @pytest.fixture(autouse=True)
    def setup_executor(self, executor: Executor):
        register_check_acts(executor)

    def test_check_files_exist_success(self, executor: Executor, isolated_vault: Path, mock_runtime_bus):
        (isolated_vault / "config.json").touch()
        (isolated_vault / "src").mkdir()
        (isolated_vault / "src/main.py").touch()

        file_list = "config.json\nsrc/main.py"
        func, _, _ = executor._acts["check_files_exist"]
        ctx = ActContext(executor)
        func(ctx, [file_list])

        mock_runtime_bus.success.assert_called_with("acts.check.success.filesExist")

    def test_check_files_exist_fail(self, executor: Executor, isolated_vault: Path):
        (isolated_vault / "exists.txt").touch()
        file_list = "exists.txt\nmissing.txt"

        # 断言 msg_id
        with pytest.raises(ExecutionError, match="acts.check.error.filesMissing"):
            func, _, _ = executor._acts["check_files_exist"]
            ctx = ActContext(executor)
            func(ctx, [file_list])

    def test_check_cwd_match_success(self, executor: Executor, isolated_vault: Path, mock_runtime_bus):
        real_path = str(isolated_vault.resolve())
        func, _, _ = executor._acts["check_cwd_match"]
        ctx = ActContext(executor)
        func(ctx, [real_path])

        mock_runtime_bus.success.assert_called_with("acts.check.success.cwdMatched", path=isolated_vault.resolve())

    def test_check_cwd_match_fail(self, executor: Executor):
        wrong_path = "/this/path/does/not/exist"

        with pytest.raises(ExecutionError, match="acts.check.error.cwdMismatch"):
            func, _, _ = executor._acts["check_cwd_match"]
            ctx = ActContext(executor)
            func(ctx, [wrong_path])
