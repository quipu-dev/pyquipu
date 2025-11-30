import subprocess
from pathlib import Path

import pytest
from pyquipu.cli.controller import run_quipu


@pytest.fixture
def nested_git_project(tmp_path: Path):
    """
    创建一个嵌套的 Git 项目结构来模拟隔离问题。
    Structure:
        host_project/
            .git/
            <-- .quipu should NOT be created here

            work_dir/
                <-- .quipu SHOULD be created here
    """
    host_project = tmp_path / "host_project"
    host_project.mkdir()
    subprocess.run(["git", "init"], cwd=host_project, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@quipu.dev"], cwd=host_project, check=True)
    subprocess.run(["git", "config", "user.name", "Quipu Test"], cwd=host_project, check=True)

    work_dir = host_project / "work_dir"
    work_dir.mkdir()
    # 必须初始化为嵌套的 git 仓库，因为 Quipu Engine 依赖于 GitDB，
    # 而 GitDB 需要当前目录或父目录是 git 仓库。
    # 为了测试隔离性（不污染 host_project），work_dir 必须自己是一个独立的仓库。
    subprocess.run(["git", "init"], cwd=work_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@quipu.dev"], cwd=work_dir, check=True)
    subprocess.run(["git", "config", "user.name", "Quipu Test"], cwd=work_dir, check=True)

    return host_project, work_dir


class TestWorkDirIsolation:
    def test_history_is_created_in_work_dir_not_host_project(self, nested_git_project):
        """
        验证：当在子目录 work_dir 中运行时，Quipu 的历史记录
        (.quipu) 必须在该子目录中创建，而不是在包含 .git 的父目录中。
        """
        host_project, work_dir = nested_git_project

        # 一个简单的 plan，用于触发历史记录的创建
        plan_content = """
```act
write_file result.txt
```
```content
isolation test
```
"""

        # 关键：调用 run_quipu，将 work_dir 设置为没有 .git 的子目录
        result = run_quipu(content=plan_content, work_dir=work_dir, yolo=True)

        # --- Assertions ---

        assert result.success is True, f"Quipu run failed: {result.message}"

        # 1. 验证文件操作发生在 work_dir
        assert (work_dir / "result.txt").exists()
        assert not (host_project / "result.txt").exists()

        # 2. 验证历史记录 (.quipu) 创建在 work_dir
        assert (work_dir / ".quipu").is_dir()
        assert (work_dir / ".quipu" / "HEAD").exists()

        # 3. 验证宿主项目没有被污染
        assert not (host_project / ".quipu").exists()
