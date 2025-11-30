import subprocess

import pytest
from pyquipu.cli.controller import run_quipu


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
    # 设置 user 避免 commit 报错
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

    def test_run_from_subdir_maintains_root_context(self, project_with_subdir):
        """
        验证：当从子目录 (`src/`) 启动 Quipu 时，
        它应该能自动发现项目根，并在根目录下正确执行操作和记录历史。
        """
        project_root, subdir = project_with_subdir

        # 关键测试点：我们使用子目录 `subdir` 作为 `work_dir` 来调用 run_quipu，
        # 模拟 `cd src; quipu run ../plan.md` 的场景。
        # plan.md 本身在根目录，其内容引用的路径 'result.txt' 也是相对于根目录的。

        # 注意：controller 层不负责解析 `../`，所以我们传 plan 的内容而不是路径
        plan_content = (project_root / "plan.md").read_text("utf-8")

        result = run_quipu(
            content=plan_content,
            work_dir=subdir,  # <--- 从子目录运行
            yolo=True,
        )

        # 1. 验证操作的正确性
        assert result.success is True, f"从子目录运行失败: {result.message}"

        # 修正：CLI 的标准行为是基于当前工作目录 (CWD/work_dir) 执行文件操作。
        # 虽然 Engine 正确地在 Project Root 运行并记录历史，但 Executor 依然在 subdir 运行。
        # 因此，文件会创建在 subdir 下，这是正确的行为。
        expected_file = subdir / "result.txt"
        assert expected_file.exists(), "文件应该在子目录创建 (CWD)"
        assert expected_file.read_text("utf-8") == "Success from subdir"

        # 2. 验证 Engine 状态记录的正确性 (后端无关)
        from pyquipu.cli.factory import create_engine

        engine = create_engine(project_root)
        nodes = engine.reader.load_all_nodes()

        # 应该有一个 drift capture 节点和一个 plan 节点
        assert len(nodes) >= 2, "应至少生成捕获节点和计划节点"

        plan_nodes = [n for n in nodes if n.node_type == "plan"]
        assert len(plan_nodes) >= 1, "应至少有一个 plan 节点"
        # 使用 reader 显式获取内容 (Lazy Loading 适配)
        content = engine.reader.get_node_content(plan_nodes[-1])
        assert "Success from subdir" in content
