import pytest
import subprocess
from pathlib import Path

from pyquipu.engine.state_machine import Engine
from pyquipu.engine.git_object_storage import GitObjectHistoryReader, GitObjectHistoryWriter
from pyquipu.engine.git_db import GitDB
from typer.testing import CliRunner


@pytest.fixture
def runner() -> CliRunner:
    """提供一个可复用的 CliRunner 实例。"""
    return CliRunner()


@pytest.fixture
def git_workspace(tmp_path: Path) -> Path:
    """
    提供一个已初始化 Git 的干净工作区路径。
    这是最基础的环境 fixture。
    """
    repo_path = tmp_path / "test_repo"
    repo_path.mkdir()
    subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@quipu.dev"], cwd=repo_path, check=True)
    subprocess.run(["git", "config", "user.name", "Quipu Test"], cwd=repo_path, check=True)
    return repo_path


@pytest.fixture
def engine_instance(git_workspace: Path) -> Engine:
    """
    提供一个绑定到 git_workspace 的、功能完备的 Engine 实例。
    这是最常用的 fixture，用于所有需要 Engine 核心逻辑的测试。
    """
    git_db = GitDB(git_workspace)
    reader = GitObjectHistoryReader(git_db)
    writer = GitObjectHistoryWriter(git_db)
    engine = Engine(root_dir=git_workspace, db=git_db, reader=reader, writer=writer)
    return engine
