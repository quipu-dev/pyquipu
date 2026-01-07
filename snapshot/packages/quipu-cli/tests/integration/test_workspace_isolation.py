import subprocess
from pathlib import Path

import pytest
from pyquipu.cli.main import app


@pytest.fixture
def nested_git_project(tmp_path: Path):
    """
    创建一个嵌套的 Git 项目结构来模拟隔离问题。
    Structure:
        host_project/
            .git/
            <-- .quipu should NOT be created here

            work_dir/
                .git/ <-- Nested repo
                <-- .quipu SHOULD be created here
    """
    host_project = tmp_path / "host_project"
    host_project.mkdir()
    subprocess.run(["git", "init"], cwd=host_project, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@quipu.dev"], cwd=host_project, check=True)
    subprocess.run(["git", "config", "user.name", "Quipu Test"], cwd=host_project, check=True)

    work_dir = host_project / "work_dir"
    work_dir.mkdir()
    # 初始化嵌套仓库
    subprocess.run(["git", "init"], cwd=work_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@quipu.dev"], cwd=work_dir, check=True)
    subprocess.run(["git", "config", "user.name", "Quipu Test"], cwd=work_dir, check=True)

    return host_project, work_dir


class TestWorkDirIsolation:
    def test_history_is_created_in_work_dir_not_host_project(self, runner, nested_git_project):
        """
        验证：当在子目录 work_dir 中运行 CLI 时，Quipu 的历史记录
        (.quipu) 必须在该子目录中创建，而不是在包含 .git 的父目录中。
        这确保了嵌套项目之间的隔离。
        """
        host_project, work_dir = nested_git_project

        # 创建一个临时计划文件
        plan_file = work_dir / "plan.md"
        plan_file.write_text(
            """
```act
write_file result.txt
```
```content
isolation test
```
""",
            encoding="utf-8",
        )

        # 运行 CLI: quipu run plan.md -w work_dir
        result = runner.invoke(app, ["run", str(plan_file), "--work-dir", str(work_dir), "-y"])

        # --- Assertions ---

        assert result.exit_code == 0, f"CLI execution failed: {result.stdout}"

        # 1. 验证文件操作发生在 work_dir
        assert (work_dir / "result.txt").exists()
        assert not (host_project / "result.txt").exists()

        # 2. 验证历史记录 (.quipu) 创建在 work_dir
        assert (work_dir / ".quipu").is_dir()
        assert (work_dir / ".quipu" / "HEAD").exists()

        # 3. 验证宿主项目没有被污染
        assert not (host_project / ".quipu").exists()
