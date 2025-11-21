import pytest
import subprocess
import shutil
from pathlib import Path
from core.executor import Executor
from acts.git import register_git_acts

@pytest.mark.skipif(not shutil.which("git"), reason="Git 命令未找到，跳过 Git 测试")
class TestGitActs:
    @pytest.fixture(autouse=True)
    def setup_git_env(self, executor: Executor, isolated_vault: Path):
        """为测试环境自动注册 Git Acts 并进行 git init"""
        register_git_acts(executor)
        
        # 执行初始化
        executor._acts['git_init'](executor, [])
        
        # 配置测试用的 user，防止 CI/Test 环境报错
        subprocess.run(["git", "config", "user.email", "axon@test.com"], cwd=isolated_vault, check=True)
        subprocess.run(["git", "config", "user.name", "Axon Bot"], cwd=isolated_vault, check=True)

    def test_git_workflow(self, executor: Executor, isolated_vault: Path):
        # 1. 创建文件
        target_file = isolated_vault / "README.md"
        target_file.write_text("# Test Repo", encoding="utf-8")
        
        # 2. Git Add
        git_add = executor._acts['git_add']
        git_add(executor, ["README.md"])
        
        # 验证状态 (porcelain 输出 ?? 代表未追踪，A 代表已添加)
        status = subprocess.check_output(["git", "status", "--porcelain"], cwd=isolated_vault, text=True)
        assert "A  README.md" in status
        
        # 3. Git Commit
        git_commit = executor._acts['git_commit']
        git_commit(executor, ["Initial commit"])
        
        # 验证提交日志
        log = subprocess.check_output(["git", "log", "--oneline"], cwd=isolated_vault, text=True)
        assert "Initial commit" in log

    def test_git_status_display(self, executor: Executor, caplog):
        # 只是运行一下看是否报错，并通过 caplog 检查日志
        import logging
        caplog.set_level(logging.INFO)
        
        git_status = executor._acts['git_status']
        git_status(executor, [])
        
        assert "Git Status" in caplog.text

    def test_git_init_idempotent(self, executor: Executor, caplog):
        # setup_git_env 已经 init 过了，再次 init 应该提示跳过
        import logging
        caplog.set_level(logging.INFO)
        
        executor._acts['git_init'](executor, [])
        assert "Git 仓库已存在" in caplog.text