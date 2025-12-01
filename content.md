## [WIP] refactor: 迁移核心逻辑到应用包并解耦 UI

### 用户需求
完成 `pyquipu-application` 包的构建，将 `quipu-cli` 中的核心控制逻辑 (`controller.py`), 工厂模式 (`factory.py`), 插件管理 (`plugin_manager.py`) 和通用工具 (`utils.py`) 迁移到新包中。同时，通过依赖注入的方式剥离 `controller.py` 对 CLI UI (`typer`, `prompt_for_confirmation`) 的直接依赖。

### 目标
1.  在 `packages/quipu-application/src/pyquipu/application/` 中创建 `utils.py`, `plugin_manager.py`, `factory.py`, `controller.py`。
2.  重构 `controller.py`，移除 `ui_utils` 依赖，修改 `QuipuApplication` 和 `run_quipu` 的签名以接受 `confirmation_handler`。
3.  删除 `packages/quipu-cli/src/pyquipu/cli/` 下对应的旧文件（物理移动完成）。

### 基本原理
通过将逻辑移动到独立的 Application 包并反转依赖（IoC），我们确保了核心业务逻辑不再感知具体的 UI 实现（CLI 或 Web）。这为后续让 CLI 和 Web API 共享同一套业务逻辑打下了坚实基础。

### 标签
#intent/refine #flow/ready #priority/high #comp/cli #comp/application #concept/executor #scope/core #ai/refine #task/domain/core #task/object/application-logic #task/action/migration #task/state/continue

---

### Script

#### Acts 1: 迁移 `utils.py`
迁移辅助工具函数。

~~~~~act
write_file packages/quipu-application/src/pyquipu/application/utils.py
~~~~~
~~~~~python
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def find_git_repository_root(start_path: Path) -> Optional[Path]:
    """向上递归查找包含 .git 的目录作为项目根目录"""
    try:
        current = start_path.resolve()
        for parent in [current] + list(current.parents):
            if (parent / ".git").exists():
                return parent
    except Exception:
        pass
    return None
~~~~~

#### Acts 2: 迁移 `plugin_manager.py`
迁移插件管理器，并更新导入路径为相对引用。

~~~~~act
write_file packages/quipu-application/src/pyquipu/application/plugin_manager.py
~~~~~
~~~~~python
import os
from pathlib import Path

from pyquipu.runtime.executor import Executor
from pyquipu.runtime.plugin_loader import load_plugins

from .utils import find_git_repository_root


class PluginManager:
    """负责发现、加载和注册外部插件。"""

    def load_from_sources(self, executor: Executor, work_dir: Path):
        """
        按照层级顺序加载外部插件，高优先级会覆盖低优先级。
        优先级顺序: Project > Env > Home
        """
        plugin_sources = []

        # 优先级由低到高添加，后面的会覆盖前面的
        # 1. User Home (Lowest priority)
        home_acts = Path.home() / ".quipu" / "acts"
        plugin_sources.append(("🏠 Global", home_acts))

        # 2. Config / Env
        env_path = os.getenv("AXON_EXTRA_ACTS_DIR")
        if env_path:
            plugin_sources.append(("🔧 Env", Path(env_path)))

        # 3. Project Root (Highest priority)
        project_root_for_plugins = find_git_repository_root(work_dir)
        if project_root_for_plugins:
            proj_acts = project_root_for_plugins / ".quipu" / "acts"
            plugin_sources.append(("📦 Project", proj_acts))

        seen_paths = set()
        for label, path in plugin_sources:
            if not path.exists() or not path.is_dir():
                continue

            resolved_path = path.resolve()
            if resolved_path in seen_paths:
                continue

            load_plugins(executor, path)
            seen_paths.add(resolved_path)
~~~~~

#### Acts 3: 迁移 `factory.py`
迁移引擎工厂函数，更新 `utils` 导入。

~~~~~act
write_file packages/quipu-application/src/pyquipu/application/factory.py
~~~~~
~~~~~python
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
    """
    实例化完整的 Engine 堆栈。

    会自动向上查找项目根目录 (Git Root) 来初始化 Engine。
    此工厂由配置驱动，以决定使用何种存储后端。

    Args:
        work_dir: 操作的工作区目录。
        lazy: 如果为 True，则不立即加载完整的历史图谱 (不调用 align)。
              这对于需要快速启动并按需加载数据的场景 (如 UI) 至关重要。
    """
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
~~~~~

#### Acts 4: 迁移并重构 `controller.py`
这是核心变更。移除 `ui_utils` 依赖，引入 `confirmation_handler` 依赖注入。

~~~~~act
write_file packages/quipu-application/src/pyquipu/application/controller.py
~~~~~
~~~~~python
import logging
import re
from pathlib import Path
from typing import Callable, List

from pyquipu.acts import register_core_acts
from pyquipu.engine.state_machine import Engine
from pyquipu.interfaces.exceptions import ExecutionError as CoreExecutionError
from pyquipu.interfaces.exceptions import OperationCancelledError
from pyquipu.interfaces.result import QuipuResult
from pyquipu.runtime.executor import Executor
from pyquipu.runtime.parser import detect_best_parser, get_parser

from .factory import create_engine
from .plugin_manager import PluginManager

logger = logging.getLogger(__name__)

# 定义 ConfirmationHandler 类型别名: (diff_lines, prompt) -> bool
# 注意: Executor 期望如果不确认则抛出异常，或者返回 False (取决于 Executor 实现)。
# 为了保持与 CLI 行为一致，调用方传入的 handler 应该在用户拒绝时抛出 OperationCancelledError。
ConfirmationHandler = Callable[[List[str], str], bool]


class QuipuApplication:
    """
    封装了 Quipu 核心业务流程的高层应用对象。
    负责协调 Engine, Parser, Executor。
    """

    def __init__(self, work_dir: Path, confirmation_handler: ConfirmationHandler, yolo: bool = False):
        self.work_dir = work_dir
        self.confirmation_handler = confirmation_handler
        self.yolo = yolo
        self.engine: Engine = create_engine(work_dir)
        logger.info(f"Operation boundary set to: {self.work_dir}")

    def _prepare_workspace(self) -> str:
        """
        检查并准备工作区，处理状态漂移。
        返回执行前的 input_tree_hash。
        """
        current_hash = self.engine.git_db.get_tree_hash()

        # 1. 正常 Clean: current_node 存在且与当前 hash 一致
        is_node_clean = (self.engine.current_node is not None) and (
            self.engine.current_node.output_tree == current_hash
        )

        # 2. 创世 Clean: 历史为空 且 当前是空树 (即没有任何文件被追踪)
        EMPTY_TREE_HASH = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
        is_genesis_clean = (not self.engine.history_graph) and (current_hash == EMPTY_TREE_HASH)

        is_clean = is_node_clean or is_genesis_clean

        if not is_clean:
            self.engine.capture_drift(current_hash)

        if self.engine.current_node:
            return self.engine.current_node.output_tree
        else:
            return current_hash

    def _setup_executor(self) -> Executor:
        """创建、配置并返回一个 Executor 实例，并注入确认处理器。"""

        executor = Executor(
            root_dir=self.work_dir,
            yolo=self.yolo,
            confirmation_handler=self.confirmation_handler,
        )

        # 加载核心 acts
        register_core_acts(executor)

        # 加载外部插件
        plugin_manager = PluginManager()
        plugin_manager.load_from_sources(executor, self.work_dir)

        return executor

    def run(self, content: str, parser_name: str) -> QuipuResult:
        """
        执行一个完整的 Plan。
        """
        # --- Phase 1 & 2: Perception & Decision (Lazy Capture) ---
        input_tree_hash = self._prepare_workspace()

        # --- Phase 3: Action (Execution) ---
        # 3.1 Parser
        final_parser_name = parser_name
        if parser_name == "auto":
            final_parser_name = detect_best_parser(content)
            if final_parser_name != "backtick":
                logger.info(f"🔍 自动检测到解析器: {final_parser_name}")

        parser = get_parser(final_parser_name)
        statements = parser.parse(content)

        if not statements:
            return QuipuResult(
                success=True,  # No failure, just nothing to do
                exit_code=0,
                message="axon.warning.noStatements",
                msg_kwargs={"parser": final_parser_name},
            )

        # 3.2 Executor Setup
        executor = self._setup_executor()

        # 3.3 Execute
        executor.execute(statements)

        # --- Phase 4: Recording (Plan Crystallization) ---
        final_summary = None
        # 优先级 1: 从 Markdown 内容中提取 # 标题
        title_match = re.search(r"^\s*#{1,6}\s+(.*)", content, re.MULTILINE)
        if title_match:
            final_summary = title_match.group(1).strip()
        # 优先级 2: 从第一个 act 指令生成摘要
        elif statements:
            final_summary = executor.summarize_statement(statements[0])

        output_tree_hash = self.engine.git_db.get_tree_hash()

        self.engine.create_plan_node(
            input_tree=input_tree_hash,
            output_tree=output_tree_hash,
            plan_content=content,
            summary_override=final_summary,
        )

        return QuipuResult(success=True, exit_code=0, message="run.success")


def run_quipu(
    content: str,
    work_dir: Path,
    confirmation_handler: ConfirmationHandler,
    parser_name: str = "auto",
    yolo: bool = False
) -> QuipuResult:
    """
    Quipu 核心业务逻辑的入口包装器。

    实例化并运行 QuipuApplication，捕获所有异常并转化为 QuipuResult。
    确保资源被安全释放。
    """
    app = None
    try:
        app = QuipuApplication(work_dir=work_dir, confirmation_handler=confirmation_handler, yolo=yolo)
        return app.run(content=content, parser_name=parser_name)

    except OperationCancelledError as e:
        logger.info(f"🚫 操作已取消: {e}")
        return QuipuResult(
            success=False, exit_code=2, message="run.error.cancelled", msg_kwargs={"error": str(e)}, error=e
        )

    except CoreExecutionError as e:
        logger.error(f"❌ 操作失败: {e}")
        return QuipuResult(
            success=False, exit_code=1, message="run.error.execution", msg_kwargs={"error": str(e)}, error=e
        )

    except Exception as e:
        logger.error(f"运行时错误: {e}", exc_info=True)
        return QuipuResult(
            success=False, exit_code=1, message="run.error.system", msg_kwargs={"error": str(e)}, error=e
        )
    finally:
        # 确保无论成功或失败，引擎资源都被关闭
        if app and hasattr(app, "engine") and app.engine:
            app.engine.close()
~~~~~

#### Acts 5: 清理 CLI 中的旧文件
删除 `quipu-cli` 中的对应文件，完成物理移动。

~~~~~act
delete_file packages/quipu-cli/src/pyquipu/cli/utils.py
~~~~~

~~~~~act
delete_file packages/quipu-cli/src/pyquipu/cli/plugin_manager.py
~~~~~

~~~~~act
delete_file packages/quipu-cli/src/pyquipu/cli/factory.py
~~~~~

~~~~~act
delete_file packages/quipu-cli/src/pyquipu/cli/controller.py
~~~~~

### 下一步建议
执行此计划将导致 CLI 暂时不可用。请立即执行 **阶段三：重新连接 CLI** 的计划，更新 `quipu-cli` 的依赖和代码以使用新的 `pyquipu-application` 包，并修复测试。
