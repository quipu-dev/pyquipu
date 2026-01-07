import shutil
from pathlib import Path

import pytest
from pyquipu.acts.read import register as register_read_acts
from pyquipu.interfaces.types import ActContext
from pyquipu.runtime.executor import ExecutionError, Executor


class TestReadActs:
    @pytest.fixture(autouse=True)
    def setup_executor(self, executor: Executor):
        register_read_acts(executor)

    def test_search_python_fallback(self, executor: Executor, isolated_vault: Path, monkeypatch, mock_runtime_bus):
        monkeypatch.setattr(shutil, "which", lambda x: None)
        target_file = isolated_vault / "config.py"
        target_file.write_text('SECRET_KEY = "123456"', encoding="utf-8")
        (isolated_vault / "readme.md").write_text("Nothing here", encoding="utf-8")

        search_func, _, _ = executor._acts["search_files"]
        ctx = ActContext(executor)
        search_func(ctx, ["SECRET_KEY"])

        mock_runtime_bus.info.assert_any_call("acts.read.info.usePythonSearch")

        # 验证数据输出
        assert mock_runtime_bus.data.called
        data_out = mock_runtime_bus.data.call_args[0][0]
        assert "config.py" in data_out
        assert 'SECRET_KEY = "123456"' in data_out

    @pytest.mark.skipif(not shutil.which("rg"), reason="Ripgrep (rg) 未安装，跳过集成测试")
    def test_search_with_ripgrep(self, executor: Executor, isolated_vault: Path, mock_runtime_bus):
        (isolated_vault / "main.rs").write_text('fn main() { println!("Hello Quipu"); }', encoding="utf-8")

        search_func, _, _ = executor._acts["search_files"]
        ctx = ActContext(executor)
        search_func(ctx, ["println!"])

        mock_runtime_bus.info.assert_any_call("acts.read.info.useRipgrep")

        assert mock_runtime_bus.data.called
        data_out = mock_runtime_bus.data.call_args[0][0]
        assert "main.rs" in data_out
        assert 'println!("Hello Quipu")' in data_out

    def test_search_scoped_path(self, executor: Executor, isolated_vault: Path, monkeypatch, mock_runtime_bus):
        monkeypatch.setattr(shutil, "which", lambda x: None)
        (isolated_vault / "target.txt").write_text("target_function", encoding="utf-8")
        src_dir = isolated_vault / "src"
        src_dir.mkdir()
        (src_dir / "inner.txt").write_text("target_function", encoding="utf-8")

        search_func, _, _ = executor._acts["search_files"]
        ctx = ActContext(executor)
        search_func(ctx, ["target_function", "--path", "src"])

        assert mock_runtime_bus.data.called
        stdout = mock_runtime_bus.data.call_args[0][0]

        # After the fix, the path should be relative to the root
        assert str(Path("src") / "inner.txt") in stdout
        assert "target.txt" not in stdout

    def test_search_no_match(self, executor: Executor, isolated_vault: Path, monkeypatch, mock_runtime_bus):
        monkeypatch.setattr(shutil, "which", lambda x: None)
        (isolated_vault / "file.txt").write_text("some content", encoding="utf-8")

        search_func, _, _ = executor._acts["search_files"]
        ctx = ActContext(executor)
        search_func(ctx, ["non_existent_pattern"])

        mock_runtime_bus.info.assert_called_with("acts.read.info.noMatchPython")

    def test_search_binary_file_resilience(self, executor: Executor, isolated_vault: Path, monkeypatch):
        monkeypatch.setattr(shutil, "which", lambda x: None)
        binary_file = isolated_vault / "data.bin"
        binary_file.write_bytes(b"\x80\x81\xff")
        search_func, _, _ = executor._acts["search_files"]
        ctx = ActContext(executor)
        try:
            search_func(ctx, ["pattern"])
        except Exception as e:
            pytest.fail(f"搜索过程因二进制文件崩溃: {e}")

    def test_search_args_error(self, executor: Executor):
        search_func, _, _ = executor._acts["search_files"]
        ctx = ActContext(executor)
        with pytest.raises(ExecutionError) as exc:
            search_func(ctx, ["pattern", "--unknown-flag"])
        assert "参数解析错误" in str(exc.value)

    def test_read_file_not_found(self, executor: Executor):
        func, _, _ = executor._acts["read_file"]
        ctx = ActContext(executor)
        with pytest.raises(ExecutionError, match="acts.read.error.targetNotFound"):
            func(ctx, ["ghost.txt"])

    def test_read_file_is_dir(self, executor: Executor, isolated_vault: Path):
        (isolated_vault / "subdir").mkdir()
        func, _, _ = executor._acts["read_file"]
        ctx = ActContext(executor)
        with pytest.raises(ExecutionError, match="acts.read.error.targetIsDir"):
            func(ctx, ["subdir"])
