import pytest
import sys
from pathlib import Path
from quipu.core.executor import Executor
from quipu.core.plugin_loader import load_plugins
from quipu.cli.utils import find_git_repository_root  # 从 utils 导入辅助函数


class TestPluginLoading:
    @pytest.fixture
    def custom_plugin_dir(self, tmp_path):
        """创建一个模拟的外部插件目录"""
        plugin_dir = tmp_path / ".quipu" / "acts"
        plugin_dir.mkdir(parents=True)
        return plugin_dir

    def test_load_external_plugin(self, executor: Executor, custom_plugin_dir):
        """测试从任意路径加载插件文件"""
        # 1. 创建一个动态插件文件
        plugin_file = custom_plugin_dir / "hello_world.py"
        plugin_content = """
def register(executor):
    executor.register("hello_world", lambda exc, args: print("Hello!"))
"""
        plugin_file.write_text(plugin_content, encoding="utf-8")

        # 2. 执行加载
        load_plugins(executor, custom_plugin_dir)

        # 3. 验证是否注册成功
        assert "hello_world" in executor._acts

        # 验证模块是否被正确隔离加载（检查 sys.modules 中的名称）
        # 我们的 loader 使用了 "quipu_plugin_" 前缀
        loaded_modules = [m for m in sys.modules.keys() if "quipu_plugin_hello_world" in m]
        assert len(loaded_modules) > 0

    def test_ignore_invalid_files(self, executor: Executor, custom_plugin_dir):
        """测试忽略非 Python 文件和无 register 函数的文件"""
        # 非 py 文件
        (custom_plugin_dir / "readme.md").write_text("# Readme")

        # 无 register 的 py 文件
        (custom_plugin_dir / "helper.py").write_text("def foo(): pass")

        load_plugins(executor, custom_plugin_dir)

        # 应该没有报错，且 acts 列表没有增加
        # (executor fixture 默认带有一些 basic acts，所以只要不崩溃且没增加奇怪的东西就行)
        assert "foo" not in executor._acts

    def test_find_git_repository_root(self, tmp_path):
        """测试 Git 项目根目录检测逻辑"""
        # 结构: root/.git, root/src/subdir
        root = tmp_path / "my_project"
        root.mkdir()
        (root / ".git").mkdir()

        subdir = root / "src" / "subdir"
        subdir.mkdir(parents=True)

        # 从子目录查找
        found = find_git_repository_root(subdir)
        assert found == root.resolve()

        # 从根目录查找
        found_root = find_git_repository_root(root)
        assert found_root == root.resolve()

        # 在非 git 目录查找
        orphan = tmp_path / "orphan"
        orphan.mkdir()
        assert find_git_repository_root(orphan) is None
