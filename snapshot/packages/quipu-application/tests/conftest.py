from pathlib import Path
from unittest.mock import MagicMock

import pytest
from pyquipu.engine.state_machine import Engine
from pyquipu.runtime.executor import Executor


@pytest.fixture
def mock_engine():
    """
    提供一个模拟的 Engine 实例。
    用于测试 Application 层在不触及真实 Git/文件系统的情况下的编排逻辑。
    """
    engine = MagicMock(spec=Engine)

    # 设置基础属性以防止简单的 AttributeError (绕过 spec 检查)
    engine.root_dir = Path("/mock/root")

    # 显式初始化 git_db，因为它是实例属性，spec 可能不包含它
    engine.git_db = MagicMock()

    # 初始化状态属性
    engine.current_node = None
    engine.history_graph = {}

    return engine


@pytest.fixture
def mock_runtime():
    """
    提供一个模拟的 Runtime (Executor) 实例。
    用于验证 Application 层是否正确调用了执行器，而不真正执行 Act。
    """
    runtime = MagicMock(spec=Executor)
    return runtime
