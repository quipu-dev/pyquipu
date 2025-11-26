# refactor: 解耦 CLI, Engine 与 Runtime 的核心耦合

## 用户需求
根据之前的代码审查，当前 `quipu-cli` 包与 `engine` 和 `runtime` 存在严重耦合，主要体现在 `controller.py` 和 `factory.py` 中。这使得代码难以维护和扩展，例如，添加新的存储后端或修改插件加载逻辑都需要改动 `cli` 包的核心流程。

你需要执行重构，解决这个核心耦合问题。

## 评论
这是一个关键的架构重构。通过引入配置驱动、依赖注入和更高层次的应用对象，可以显著提高系统的模块化程度、可测试性和可扩展性，为未来的功能迭代（如支持 SQLite 存储）奠定基础。

## 目标
1.  `factory.py` 中的 `create_engine` 函数不再硬编码 `GitObject` 存储，而是根据配置动态选择。
2.  插件加载逻辑从 `controller.py` 中剥离，由独立的 `PluginManager` 负责。
3.  `controller.py` 中的 `run_quipu` 函数逻辑被封装进一个新的 `QuipuApplication` 类，实现职责分离。

## 基本原理
本次重构遵循以下设计原则：
1.  **依赖倒置原则**：高层模块 (`cli`) 不应依赖于低层模块 (`engine` 的具体实现) 的细节，两者都应依赖于抽象 (`HistoryReader`/`Writer` 接口)。我们通过配置驱动的工厂来实现这一点。
2.  **单一职责原则**：将插件管理这一独立的关注点从核心业务流程中分离出来，封装到 `PluginManager` 类中。
3.  **封装与抽象**：将过程式的业务编排逻辑封装到 `QuipuApplication` 对象中，对外提供简洁的接口，隐藏内部的复杂协调过程。

## 标签
#intent/refine #flow/ready #priority/high
#comp/cli #comp/engine #comp/runtime #concept/state #concept/executor
#scope/core
#ai/instruct

---

## Script

### Acts 1: 创建通用工具与插件管理器

首先，我们将重复的 `find_project_root` 逻辑提取到一个通用的 `utils.py` 文件中，然后创建新的 `PluginManager` 来封装插件加载逻辑。

~~~~~act
write_file packages/quipu-cli/src/quipu/cli/utils.py
~~~~~
~~~~~python
import logging
from pathlib import Path
from typing import Optional

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
~~~~~

~~~~~act
write_file packages/quipu-cli/src/quipu/cli/plugin_manager.py
~~~~~
~~~~~python
import os
from pathlib import Path

from quipu.core.executor import Executor
from quipu.core.plugin_loader import load_plugins
from .utils import find_project_root


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
        project_root_for_plugins = find_project_root(work_dir)
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

### Acts 2: 改造工厂与配置

接下来，我们将修改 `config.py` 以包含存储配置的默认值，并重构 `factory.py` 使其变为配置驱动。同时，更新 `main.py` 以从新的 `utils` 模块导入 `find_project_root`。

~~~~~act
replace packages/quipu-engine/src/quipu/core/config.py
~~~~~
~~~~~python
# 默认配置，为所有可能的设置提供一个基础
DEFAULTS = {
    "sync": {
        "remote_name": "origin",
        "persistent_ignores": [".idea", ".vscode", ".envs", "__pycache__", "node_modules", "o.md"],
    },
    "list_files": {"ignore_patterns": [".git", "__pycache__", ".idea", ".vscode", "node_modules", ".quipu"]},
}
~~~~~
~~~~~python
# 默认配置，为所有可能的设置提供一个基础
DEFAULTS = {
    "storage": {
        "type": "git_object",
    },
    "sync": {
        "remote_name": "origin",
        "persistent_ignores": [".idea", ".vscode", ".envs", "__pycache__", "node_modules", "o.md"],
    },
    "list_files": {"ignore_patterns": [".git", "__pycache__", ".idea", ".vscode", "node_modules", ".quipu"]},
}
~~~~~

~~~~~act
write_file packages/quipu-cli/src/quipu/cli/factory.py
~~~~~
~~~~~python
import logging
from pathlib import Path
from typing import Optional

from quipu.core.state_machine import Engine
from quipu.core.git_object_storage import GitObjectHistoryReader, GitObjectHistoryWriter
from quipu.core.git_db import GitDB
from quipu.core.config import ConfigManager
from .utils import find_project_root

logger = logging.getLogger(__name__)


def create_engine(work_dir: Path) -> Engine:
    """
    实例化完整的 Engine 堆栈。

    会自动向上查找项目根目录 (Git Root) 来初始化 Engine。
    如果找不到 Git Root，则回退到 work_dir。
    此工厂现在由配置驱动，以决定使用何种存储后端。
    """
    # 1. 尝试查找真正的项目根目录 (包含 .git 的目录)
    project_root = find_project_root(work_dir)
    if not project_root:
        project_root = work_dir

    # 2. 加载配置
    config = ConfigManager(project_root)
    storage_type = config.get("storage.type", "git_object")

    # 3. 创建 GitDB 实例，这是多种存储格式可能共用的基础
    git_db = GitDB(project_root)

    # 4. 根据配置选择存储后端
    if storage_type == "git_object":
        logger.debug("Using Git Object storage format.")
        reader = GitObjectHistoryReader(git_db)
        writer = GitObjectHistoryWriter(git_db)
    else:
        # 未来可以扩展其他类型，例如 file_system, sqlite
        raise NotImplementedError(f"Storage type '{storage_type}' is not supported.")

    # 5. 注入依赖并实例化 Engine
    engine = Engine(project_root, reader=reader, writer=writer)
    engine.align()  # 对齐以加载历史图谱

    return engine
~~~~~

~~~~~act
replace packages/quipu-cli/src/quipu/cli/main.py
~~~~~
~~~~~python
from .logger_config import setup_logging
from .controller import run_quipu
from .config import DEFAULT_WORK_DIR, DEFAULT_ENTRY_FILE, PROJECT_ROOT
from .factory import create_engine, find_project_root  # 导入工厂方法
from quipu.core.plugin_loader import load_plugins
~~~~~
~~~~~python
from .logger_config import setup_logging
from .controller import run_quipu
from .config import DEFAULT_WORK_DIR, DEFAULT_ENTRY_FILE, PROJECT_ROOT
from .factory import create_engine
from .utils import find_project_root
from quipu.core.plugin_loader import load_plugins
~~~~~

### Acts 3: 重构核心控制器

最后，也是最关键的一步：重构 `controller.py`。我们将引入 `QuipuApplication` 类来封装业务流程，使 `run_quipu` 成为一个简洁的入口。

~~~~~act
write_file packages/quipu-cli/src/quipu/cli/controller.py
~~~~~
~~~~~python
import logging
from pathlib import Path

from quipu.core.exceptions import ExecutionError as CoreExecutionError
from quipu.core.executor import Executor
from quipu.core.parser import detect_best_parser, get_parser
from quipu.core.result import QuipuResult
from quipu.core.state_machine import Engine
from quipu.acts import register_core_acts
from .factory import create_engine
from .plugin_manager import PluginManager

logger = logging.getLogger(__name__)


class QuipuApplication:
    """
    封装了 Quipu 核心业务流程的高层应用对象。
    负责协调 Engine, Parser, Executor。
    """

    def __init__(self, work_dir: Path, yolo: bool = False):
        self.work_dir = work_dir
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
        is_node_clean = (self.engine.current_node is not None) and (self.engine.current_node.output_tree == current_hash)

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
        """创建、配置并返回一个 Executor 实例。"""
        executor = Executor(root_dir=self.work_dir, yolo=self.yolo)

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
                success=False,
                exit_code=0,
                message=f"⚠️  使用 '{final_parser_name}' 解析器未找到任何有效的 'act' 操作块。",
            )

        # 3.2 Executor Setup
        executor = self._setup_executor()

        # 3.3 Execute
        executor.execute(statements)

        # --- Phase 4: Recording (Plan Crystallization) ---
        smart_summary = None
        if statements:
            smart_summary = executor.summarize_statement(statements[0])

        output_tree_hash = self.engine.git_db.get_tree_hash()

        self.engine.create_plan_node(
            input_tree=input_tree_hash,
            output_tree=output_tree_hash,
            plan_content=content,
            summary_override=smart_summary,
        )

        return QuipuResult(success=True, exit_code=0, message="✨ 执行成功")


def run_quipu(content: str, work_dir: Path, parser_name: str = "auto", yolo: bool = False) -> QuipuResult:
    """
    Quipu 核心业务逻辑的入口包装器。

    实例化并运行 QuipuApplication，捕获所有异常并转化为 QuipuResult。
    """
    try:
        app = QuipuApplication(work_dir=work_dir, yolo=yolo)
        return app.run(content=content, parser_name=parser_name)

    except CoreExecutionError as e:
        # 预期的执行错误 (如文件找不到，Git 冲突等)
        logger.error(f"❌ 操作失败: {e}")
        return QuipuResult(success=False, exit_code=1, message=str(e), error=e)

    except Exception as e:
        # 意外的运行时错误
        logger.error(f"运行时错误: {e}", exc_info=True)
        return QuipuResult(success=False, exit_code=1, message=f"系统错误: {e}", error=e)
~~~~~

