import pytest
import subprocess
import shutil
from pathlib import Path
from quipu.core.executor import Executor
from quipu.acts.git import register as register_git_acts


@pytest.mark.skipif(not shutil.which("git"), reason="Git 命令未找到，跳过 Git 测试")
class TestGitActs:
    @pytest.fixture(autouse=True)
    def setup_git_env(self, executor: Executor, isolated_vault: Path):
        """为测试环境自动注册 Git Acts 并进行 git init"""
        register_git_acts(executor)

        # 执行初始化
        func, _, _ = executor._acts["git_init"]
        func(executor, [])

        # 配置测试用的 user，防止 CI/Test 环境报错
        subprocess.run(["git", "config", "user.email", "quipu@test.com"], cwd=isolated_vault, check=True)
        subprocess.run(["git", "config", "user.name", "Quipu Bot"], cwd=isolated_vault, check=True)

    def test_git_workflow(self, executor: Executor, isolated_vault: Path):
        # 1. 创建文件
        target_file = isolated_vault / "README.md"
        target_file.write_text("# Test Repo", encoding="utf-8")

        # 2. Git Add
        git_add, _, _ = executor._acts["git_add"]
        git_add(executor, ["README.md"])

        # 验证状态 (porcelain 输出 ?? 代表未追踪，A 代表已添加)
        status = subprocess.check_output(["git", "status", "--porcelain"], cwd=isolated_vault, text=True)
        assert "A  README.md" in status

        # 3. Git Commit
        git_commit, _, _ = executor._acts["git_commit"]
        git_commit(executor, ["Initial commit"])

        # 验证提交日志
        log = subprocess.check_output(["git", "log", "--oneline"], cwd=isolated_vault, text=True)
        assert "Initial commit" in log

    # This test is obsolete after redirecting git_status output to stdout
    # and has been removed. The behavior is now correctly tested by
    # test_git_status_output_stream.

    def test_git_init_idempotent(self, executor: Executor, caplog):
        # setup_git_env 已经 init 过了，再次 init 应该提示跳过
        import logging

        caplog.set_level(logging.INFO)

        func, _, _ = executor._acts["git_init"]
        func(executor, [])
        assert "Git 仓库已存在" in caplog.text

    def test_git_status_output_stream(self, executor: Executor, isolated_vault: Path, capsys, caplog):
        """
        验证 git_status 的输出流是否正确。
        - 结果数据 (git status 内容) 应在 stdout。
        - 执行日志 (e.g., "Executing operation...") 应在 stderr (通过 logging)。
        """
        import logging

        caplog.set_level(logging.INFO)

        # 1. 制造一些状态变更
        (isolated_vault / "untracked.txt").write_text("new file")

        # 2. 我们通过 executor.execute 来模拟完整的执行流程
        stmts = [{"act": "git_status", "contexts": []}]
        executor.execute(stmts)

        # 3. 捕获并验证输出
        # 使用 capsys 捕获 stdout
        captured_streams = capsys.readouterr()

        # 验证 stdout 包含 git status 的核心内容
        assert "Untracked files" in captured_streams.out
        assert "untracked.txt" in captured_streams.out

        # 验证 stderr (原始流) 不包含 git status 的内容
        assert "Untracked files" not in captured_streams.err

        # 使用 caplog 捕获日志记录
        # 验证日志中确实包含了执行信息
        assert "Executing operation" in caplog.text
        assert "git_status" in caplog.text
