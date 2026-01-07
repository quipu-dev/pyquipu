import shutil
import subprocess
from pathlib import Path

import pytest
from pyquipu.acts.git import register as register_git_acts
from pyquipu.runtime.executor import Executor


@pytest.mark.skipif(not shutil.which("git"), reason="Git 命令未找到，跳过 Git 测试")
class TestGitActs:
    @pytest.fixture(autouse=True)
    def setup_git_env(self, executor: Executor, isolated_vault: Path):
        register_git_acts(executor)

        # 执行初始化
        func, _, _ = executor._acts["git_init"]
        func(executor, [])

        # 配置测试用的 user，防止 CI/Test 环境报错
        subprocess.run(["git", "config", "user.email", "quipu@test.com"], cwd=isolated_vault, check=True)
        subprocess.run(["git", "config", "user.name", "Quipu Bot"], cwd=isolated_vault, check=True)

    def test_git_workflow(self, executor: Executor, isolated_vault: Path, mock_runtime_bus):
        # 1. 创建文件
        target_file = isolated_vault / "README.md"
        target_file.write_text("# Test Repo", encoding="utf-8")

        # 2. Git Add
        git_add, _, _ = executor._acts["git_add"]
        git_add(executor, ["README.md"])
        mock_runtime_bus.success.assert_called_with("acts.git.success.added", targets=["README.md"])

        # 验证状态 (porcelain 输出 ?? 代表未追踪，A 代表已添加)
        status = subprocess.check_output(["git", "status", "--porcelain"], cwd=isolated_vault, text=True)
        assert "A  README.md" in status

        # 3. Git Commit
        git_commit, _, _ = executor._acts["git_commit"]
        git_commit(executor, ["Initial commit"])
        mock_runtime_bus.success.assert_called_with("acts.git.success.committed", message="Initial commit")

        # 验证提交日志
        log = subprocess.check_output(["git", "log", "--oneline"], cwd=isolated_vault, text=True)
        assert "Initial commit" in log

    def test_git_init_idempotent(self, executor: Executor, mock_runtime_bus):
        # setup_git_env 已经 init 过了，再次 init 应该提示跳过
        func, _, _ = executor._acts["git_init"]
        func(executor, [])
        mock_runtime_bus.warning.assert_called_with("acts.git.warning.repoExists")

    def test_git_status_output_stream(self, executor: Executor, isolated_vault: Path, mock_runtime_bus):
        # 1. 制造一些状态变更
        (isolated_vault / "untracked.txt").write_text("new file")

        # 2. 我们通过 executor.execute 来模拟完整的执行流程
        stmts = [{"act": "git_status", "contexts": []}]
        executor.execute(stmts)

        # 3. 验证 bus 调用
        # 验证执行器日志
        mock_runtime_bus.info.assert_any_call(
            "runtime.executor.info.executing", current=1, total=1, act_name="git_status", mode="exclusive", arg_count=0
        )

        # 验证数据输出
        # args[0] 应该是 status 字符串，包含 untracked.txt
        assert mock_runtime_bus.data.called
        data_arg = mock_runtime_bus.data.call_args[0][0]
        assert "Untracked files" in data_arg
        assert "untracked.txt" in data_arg
