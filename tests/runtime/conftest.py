import pytest
from pathlib import Path
from quipu.runtime.executor import Executor
from quipu.acts.basic import register as register_basic_acts


@pytest.fixture
def executor(tmp_path: Path) -> Executor:
    """
    为运行时测试提供一个隔离的 Executor 实例。
    - 在独立的临时目录 (tmp_path) 中运行。
    - 自动注册基础 acts。
    - 默认以非交互模式 (yolo=True) 运行。
    """
    # yolo=True 避免在测试中出现交互式提示，这对于非 CLI 测试至关重要
    instance = Executor(root_dir=tmp_path, yolo=True)
    # 自动注册基础指令，因为大多数测试都依赖它们
    register_basic_acts(instance)
    return instance


@pytest.fixture
def isolated_vault(executor: Executor) -> Path:
    """
    提供 Executor 实例的根工作目录。
    这是一个便利性的 fixture，用于需要直接操作文件系统的测试。
    """
    return executor.root_dir
