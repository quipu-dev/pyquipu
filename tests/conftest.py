import pytest
from pathlib import Path
from core.executor import Executor
from acts.basic import register_basic_acts

@pytest.fixture
def isolated_vault(tmp_path: Path) -> Path:
    """
    创建一个临时的隔离工作区。
    """
    vault = tmp_path / "vault"
    vault.mkdir()
    return vault

@pytest.fixture
def executor(isolated_vault: Path) -> Executor:
    """
    返回一个绑定到临时工作区的执行器实例，并预装了基础 Acts。
    测试期间默认开启 YOLO 模式，跳过交互确认。
    """
    exc = Executor(root_dir=isolated_vault, yolo=True)
    register_basic_acts(exc)
    return exc
