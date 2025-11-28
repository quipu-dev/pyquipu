import pytest
import subprocess
from pathlib import Path
from typer.testing import CliRunner

from quipu.core.state_machine import Engine
from quipu.core.git_object_storage import GitObjectHistoryReader, GitObjectHistoryWriter
from quipu.core.git_db import GitDB


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def quipu_workspace(tmp_path):
    """
    创建一个包含 Git 仓库并初始化了 Quipu Engine 的测试环境。
    返回: (work_dir_path, git_db, engine)
    """
    work_dir = tmp_path / "ws"
    work_dir.mkdir()

    # 初始化 Git
    subprocess.run(["git", "init"], cwd=work_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@quipu.dev"], cwd=work_dir, check=True)
    subprocess.run(["git", "config", "user.name", "Quipu Test"], cwd=work_dir, check=True)

    # 初始化 Engine 组件
    git_db = GitDB(work_dir)
    reader = GitObjectHistoryReader(git_db)
    writer = GitObjectHistoryWriter(git_db)
    engine = Engine(work_dir, db=git_db, reader=reader, writer=writer)

    return work_dir, git_db, engine
