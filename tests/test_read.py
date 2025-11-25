import pytest
import shutil
import logging
from pathlib import Path
from quipu.core.executor import Executor, ExecutionError
from quipu.acts.read import register as register_read_acts
from quipu.core.types import ActContext

class TestReadActs:
    @pytest.fixture(autouse=True)
    def setup_executor(self, executor: Executor):
        register_read_acts(executor)

    def test_search_python_fallback(self, executor: Executor, isolated_vault: Path, caplog, capsys, monkeypatch):
        monkeypatch.setattr(shutil, "which", lambda x: None)
        target_file = isolated_vault / "config.py"
        target_file.write_text('SECRET_KEY = "123456"', encoding='utf-8')
        (isolated_vault / "readme.md").write_text("Nothing here", encoding='utf-8')

        caplog.set_level(logging.INFO)
        search_func, _, _ = executor._acts['search_files']
        ctx = ActContext(executor)
        search_func(ctx, ["SECRET_KEY"])

        assert "Using Python native search" in caplog.text
        captured = capsys.readouterr()
        assert "config.py" in captured.out
        assert 'SECRET_KEY = "123456"' in captured.out

    @pytest.mark.skipif(not shutil.which("rg"), reason="Ripgrep (rg) 未安装，跳过集成测试")
    def test_search_with_ripgrep(self, executor: Executor, isolated_vault: Path, caplog, capsys):
        (isolated_vault / "main.rs").write_text('fn main() { println!("Hello Quipu"); }', encoding='utf-8')

        caplog.set_level(logging.INFO)
        search_func, _, _ = executor._acts['search_files']
        ctx = ActContext(executor)
        search_func(ctx, ['println!'])

        assert "Using 'rg' (ripgrep)" in caplog.text
        captured = capsys.readouterr()
        assert "main.rs" in captured.out
        assert 'println!("Hello Quipu")' in captured.out

    def test_search_scoped_path(self, executor: Executor, isolated_vault: Path, caplog, capsys, monkeypatch):
        monkeypatch.setattr(shutil, "which", lambda x: None)
        (isolated_vault / "target.txt").write_text("target_function", encoding='utf-8')
        src_dir = isolated_vault / "src"
        src_dir.mkdir()
        (src_dir / "inner.txt").write_text("target_function", encoding='utf-8')

        caplog.set_level(logging.INFO)
        search_func, _, _ = executor._acts['search_files']
        ctx = ActContext(executor)
        search_func(ctx, ["target_function", "--path", "src"])

        captured = capsys.readouterr()
        stdout = captured.out
        
        # After the fix, the path should be relative to the root
        assert str(Path("src") / "inner.txt") in stdout
        assert str(isolated_vault / "target.txt") not in stdout
        assert "target.txt:1:target_function" not in stdout

    def test_search_no_match(self, executor: Executor, isolated_vault: Path, caplog, monkeypatch):
        monkeypatch.setattr(shutil, "which", lambda x: None)
        (isolated_vault / "file.txt").write_text("some content", encoding='utf-8')
        caplog.set_level(logging.INFO)
        search_func, _, _ = executor._acts['search_files']
        ctx = ActContext(executor)
        search_func(ctx, ["non_existent_pattern"])
        assert "No matches found" in caplog.text

    def test_search_binary_file_resilience(self, executor: Executor, isolated_vault: Path, monkeypatch):
        monkeypatch.setattr(shutil, "which", lambda x: None)
        binary_file = isolated_vault / "data.bin"
        binary_file.write_bytes(b'\x80\x81\xff')
        search_func, _, _ = executor._acts['search_files']
        ctx = ActContext(executor)
        try:
            search_func(ctx, ["pattern"])
        except Exception as e:
            pytest.fail(f"搜索过程因二进制文件崩溃: {e}")

    def test_search_args_error(self, executor: Executor):
        search_func, _, _ = executor._acts['search_files']
        ctx = ActContext(executor)
        with pytest.raises(ExecutionError) as exc:
            search_func(ctx, ["pattern", "--unknown-flag"])
        assert "参数解析错误" in str(exc.value)