from pathlib import Path

import pytest
from pyquipu.acts.refactor import register as register_refactor_acts
from pyquipu.interfaces.exceptions import ExecutionError
from pyquipu.interfaces.types import ActContext
from pyquipu.runtime.executor import Executor


class TestRefactorActs:
    @pytest.fixture(autouse=True)
    def setup_executor(self, executor: Executor):
        register_refactor_acts(executor)

    def test_move_file_success(self, executor: Executor, isolated_vault: Path, mock_runtime_bus):
        src = isolated_vault / "old.txt"
        src.write_text("content")
        dest = isolated_vault / "new.txt"

        func, _, _ = executor._acts["move_file"]
        ctx = ActContext(executor)
        func(ctx, ["old.txt", "new.txt"])

        assert not src.exists()
        assert dest.exists()
        assert dest.read_text() == "content"
        mock_runtime_bus.success.assert_called_with(
            "acts.refactor.success.moved", source="old.txt", destination="new.txt"
        )

    def test_move_file_src_not_found(self, executor: Executor):
        func, _, _ = executor._acts["move_file"]
        ctx = ActContext(executor)
        with pytest.raises(ExecutionError, match="acts.refactor.error.srcNotFound"):
            func(ctx, ["missing.txt", "dest.txt"])

    def test_move_file_permission_error(self, executor: Executor, isolated_vault: Path, monkeypatch):
        src = isolated_vault / "locked.txt"
        src.touch()
        import shutil

        def mock_move(*args):
            raise PermissionError("Access denied")

        monkeypatch.setattr(shutil, "move", mock_move)

        func, _, _ = executor._acts["move_file"]
        ctx = ActContext(executor)
        with pytest.raises(ExecutionError, match="acts.refactor.error.movePermission"):
            func(ctx, ["locked.txt", "dest.txt"])

    def test_delete_file_success(self, executor: Executor, isolated_vault: Path, mock_runtime_bus):
        target = isolated_vault / "trash.txt"
        target.touch()

        func, _, _ = executor._acts["delete_file"]
        ctx = ActContext(executor)
        func(ctx, ["trash.txt"])

        assert not target.exists()
        mock_runtime_bus.success.assert_called_with("acts.refactor.success.deleted", path="trash.txt")

    def test_delete_dir_success(self, executor: Executor, isolated_vault: Path, mock_runtime_bus):
        target_dir = isolated_vault / "trash_dir"
        target_dir.mkdir()
        (target_dir / "file.txt").touch()

        func, _, _ = executor._acts["delete_file"]
        ctx = ActContext(executor)
        func(ctx, ["trash_dir"])

        assert not target_dir.exists()
        mock_runtime_bus.success.assert_called_with("acts.refactor.success.deleted", path="trash_dir")

    def test_delete_skipped(self, executor: Executor, mock_runtime_bus):
        func, _, _ = executor._acts["delete_file"]
        ctx = ActContext(executor)
        func(ctx, ["non_existent.txt"])

        mock_runtime_bus.warning.assert_called_with("acts.refactor.warning.deleteSkipped", path="non_existent.txt")
