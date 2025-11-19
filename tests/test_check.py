import pytest
from pathlib import Path
from core.executor import Executor, ExecutionError
from acts.check import register_check_acts

class TestCheckActs:
    @pytest.fixture(autouse=True)
    def setup_executor(self, executor: Executor):
        """自动为每个测试注册 check acts"""
        register_check_acts(executor)

    def test_check_files_exist_success(self, executor: Executor, isolated_vault: Path):
        # 准备环境
        (isolated_vault / "config.json").touch()
        (isolated_vault / "src").mkdir()
        (isolated_vault / "src/main.py").touch()
        
        # 执行检查
        file_list = """
        config.json
        src/main.py
        """
        executor._acts['check_files_exist'](executor, [file_list])

    def test_check_files_exist_fail(self, executor: Executor, isolated_vault: Path):
        (isolated_vault / "exists.txt").touch()
        
        file_list = """
        exists.txt
        missing.txt
        """
        
        with pytest.raises(ExecutionError) as excinfo:
            executor._acts['check_files_exist'](executor, [file_list])
        
        msg = str(excinfo.value)
        assert "missing.txt" in msg
        assert "exists.txt" not in msg # 存在的文不应该报错

    def test_check_cwd_match_success(self, executor: Executor, isolated_vault: Path):
        # 获取当前测试 vault 的绝对路径
        real_path = str(isolated_vault.resolve())
        
        executor._acts['check_cwd_match'](executor, [real_path])

    def test_check_cwd_match_fail(self, executor: Executor):
        wrong_path = "/this/path/does/not/exist"
        
        with pytest.raises(ExecutionError) as excinfo:
            executor._acts['check_cwd_match'](executor, [wrong_path])
            
        assert "工作区目录不匹配" in str(excinfo.value)
