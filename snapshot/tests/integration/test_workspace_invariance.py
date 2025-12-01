import subprocess

import pytest
from pyquipu.cli.main import app


@pytest.fixture
def project_with_subdir(tmp_path):
    """
    创建一个标准的 Git 项目结构，包含一个子目录。
    root/
      .git/
      plan.md
      src/
        (empty)
    """
    # 1. 初始化项目根目录和 Git
    root = tmp_path / "project"
    root.mkdir()
    subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@quipu.dev"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Quipu Test"], cwd=root, check=True)

    # 2. 创建子目录和 Plan 文件
    subdir = root / "src"
    subdir.mkdir()

    plan_content = """
```act
write_file
```
```path
result.txt
```
```content
Success from subdir
```
"""
    (root / "plan.md").write_text(plan_content, "utf-8")

    return root, subdir


class TestRootInvariance:
    """
    测试 Quipu 的核心特性：根目录不变性。
    无论用户从项目的哪个子目录运行命令，Quipu 的行为都应该与在项目根目录运行时完全一致。
    """

    def test_run_from_subdir_maintains_root_context(self, runner, project_with_subdir):
        """
        验证：当通过 CLI 指定子目录为工作区时（模拟在子目录执行命令），
        Quipu 应能自动上溯发现项目根，并在根目录下正确记录历史，同时在 CWD 执行操作。
        """
        project_root, subdir = project_with_subdir
        plan_path = project_root / "plan.md"

        # 模拟命令: quipu run ../plan.md -w . (假设当前在 subdir)
        # 或者更直接地：quipu run /path/to/plan.md -w /path/to/subdir
        result = runner.invoke(app, ["run", str(plan_path), "--work-dir", str(subdir), "-y"])

        # 1. 验证 CLI 执行成功
        assert result.exit_code == 0, f"CLI execution failed: {result.stdout}"

        # 2. 验证文件操作发生在 subdir (CWD)
        # Executor 默认在传入的 work_dir 执行，这里传入的是 subdir
        expected_file = subdir / "result.txt"
        assert expected_file.exists(), "文件应该在子目录创建"
        assert expected_file.read_text("utf-8") == "Success from subdir"

        # 3. 验证 Engine 状态记录在 Project Root
        # 检查 .quipu 目录是否在 root 下创建
        assert (project_root / ".quipu").exists(), "历史记录目录应在项目根目录创建"
        assert (project_root / ".quipu" / "HEAD").exists()

        # 确保 subdir 下没有误创建 .quipu
        assert not (subdir / ".quipu").exists(), "子目录不应包含历史记录目录"
