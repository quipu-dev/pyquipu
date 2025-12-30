import logging
from pathlib import Path

from pyquipu.engine.config import ConfigManager
from pyquipu.engine.git_db import GitDB
from pyquipu.engine.git_object_storage import GitObjectHistoryReader, GitObjectHistoryWriter
from pyquipu.engine.state_machine import Engine

from .utils import find_git_repository_root

# 迟延导入以避免循环依赖
try:
    from pyquipu.engine.sqlite_db import DatabaseManager
    from pyquipu.engine.sqlite_storage import SQLiteHistoryReader, SQLiteHistoryWriter
except ImportError:
    DatabaseManager = None
    SQLiteHistoryWriter = None
    SQLiteHistoryReader = None


logger = logging.getLogger(__name__)


def create_engine(work_dir: Path, lazy: bool = False) -> Engine:
    project_root = find_git_repository_root(work_dir) or work_dir
    config = ConfigManager(project_root)
    storage_type = config.get("storage.type", "git_object")
    logger.debug(f"Engine factory configured with storage type: '{storage_type}'")
    git_db = GitDB(project_root)
    db_manager = None

    # 默认和备用后端
    reader = GitObjectHistoryReader(git_db)
    writer = GitObjectHistoryWriter(git_db)

    if storage_type == "sqlite":
        if not DatabaseManager or not SQLiteHistoryWriter or not SQLiteHistoryReader:
            raise ImportError("SQLite dependencies could not be loaded. Please check your installation.")

        logger.debug("Using SQLite storage format for reads and writes.")
        db_manager = DatabaseManager(project_root)
        db_manager.init_schema()

        # 切换到 SQLite 后端
        reader = SQLiteHistoryReader(db_manager=db_manager, git_db=git_db)
        writer = SQLiteHistoryWriter(git_writer=writer, db_manager=db_manager)

    elif storage_type != "git_object":
        raise NotImplementedError(f"Storage type '{storage_type}' is not supported.")

    # 将所有资源注入 Engine
    engine = Engine(project_root, db=git_db, reader=reader, writer=writer, db_manager=db_manager)
    if not lazy:
        engine.align()

    return engine
