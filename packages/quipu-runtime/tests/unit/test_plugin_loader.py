import sys

import pytest
from pyquipu.application.utils import find_git_repository_root
from pyquipu.runtime.executor import Executor
from pyquipu.runtime.plugin_loader import load_plugins


class TestPluginLoading:
    @pytest.fixture
    def custom_plugin_dir(self, tmp_path):
        plugin_dir = tmp_path / ".quipu" / "acts"
        plugin_dir.mkdir(parents=True)
        return plugin_dir

    def test_load_external_plugin(self, executor: Executor, custom_plugin_dir, mock_runtime_bus):
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

        # 验证消息
        mock_runtime_bus.info.assert_called_with("runtime.plugin.info.loading", plugin_dir=custom_plugin_dir)

        # 验证模块是否被正确隔离加载
        loaded_modules = [m for m in sys.modules.keys() if "quipu_plugin_hello_world" in m]
        assert len(loaded_modules) > 0

    def test_ignore_invalid_files(self, executor: Executor, custom_plugin_dir):
        # 非 py 文件
        (custom_plugin_dir / "readme.md").write_text("# Readme")

        # 无 register 的 py 文件
        (custom_plugin_dir / "helper.py").write_text("def foo(): pass")

        load_plugins(executor, custom_plugin_dir)

        # 应该没有报错，且 acts 列表没有增加
        assert "foo" not in executor._acts

    def test_find_git_repository_root(self, tmp_path):
        root = tmp_path / "my_project"
        root.mkdir()
        (root / ".git").mkdir()

        subdir = root / "src" / "subdir"
        subdir.mkdir(parents=True)

        found = find_git_repository_root(subdir)
        assert found == root.resolve()

        found_root = find_git_repository_root(root)
        assert found_root == root.resolve()

        orphan = tmp_path / "orphan"
        orphan.mkdir()
        assert find_git_repository_root(orphan) is None
