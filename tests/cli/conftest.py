import pytest
from pyquipu.engine.state_machine import Engine

# runner fixture is now in the root conftest.py, so it's removed from here.


@pytest.fixture
def quipu_workspace(engine_instance: Engine):
    """
    为 CLI 测试提供 Engine 实例及其工作目录，保持原有返回结构以兼容现有测试。
    返回: (work_dir_path, git_db, engine)
    """
    return engine_instance.root_dir, engine_instance.git_db, engine_instance
