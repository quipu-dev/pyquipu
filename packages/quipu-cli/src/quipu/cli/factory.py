import logging
from pathlib import Path
from typing import Optional

from quipu.core.state_machine import Engine

from quipu.core.git_object_storage import GitObjectHistoryReader, GitObjectHistoryWriter
from quipu.core.git_db import GitDB

logger = logging.getLogger(__name__)


def find_project_root(start_path: Path) -> Optional[Path]:
    """向上递归查找包含 .git 的目录作为项目根目录"""
    try:
        current = start_path.resolve()
        for parent in [current] + list(current.parents):
            if (parent / ".git").exists():
                return parent
    except Exception:
        pass
    return None


def create_engine(work_dir: Path) -> Engine:
    """
    实例化完整的 Engine 堆栈。

    会自动向上查找项目根目录 (Git Root) 来初始化 Engine。
    如果找不到 Git Root，则回退到 work_dir。
    """
    # 1. 尝试查找真正的项目根目录 (包含 .git 的目录)
    # 这确保了即使在子目录中运行，GitDB 也能正确找到仓库
    project_root = find_project_root(work_dir)
    if not project_root:
        project_root = work_dir

    # 2. 创建 GitDB 实例，绑定到项目根目录
    git_db = GitDB(project_root)

    # 3. 默认使用 Git Object 存储
    logger.debug("Defaulting to Git Object storage format.")
    reader = GitObjectHistoryReader(git_db)
    writer = GitObjectHistoryWriter(git_db)

    # 4. 注入依赖并实例化 Engine，根目录为项目根目录
    engine = Engine(project_root, reader=reader, writer=writer)
    engine.align()  # 对齐以加载历史图谱

    return engine
