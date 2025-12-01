## [WIP] refactor: 重连 CLI 并适配 Application 包

### 用户需求
完成 Phase 2 的文件移动后，`quipu-cli` 目前处于损坏状态（缺少依赖、引用路径错误）。需要更新 `quipu-cli` 的依赖配置，修复所有因迁移导致的 Import 错误，并将 CLI 特有的 UI 确认逻辑重新适配给 Application 层。

### 目标
1.  在 `packages/quipu-cli/pyproject.toml` 中添加 `pyquipu-application` 依赖。
2.  在 `packages/quipu-cli/src/pyquipu/cli/ui_utils.py` 中实现 `confirmation_handler_for_executor` 适配器。
3.  修复 `run.py`, `axon.py`, `helpers.py`, `remote.py`, `ui.py`, `tui.py` 中的导入路径，指向 `pyquipu.application`。
4.  修改 `run.py` 中的 `run_quipu` 调用，注入 `confirmation_handler`。

### 基本原理
这是重构的收尾阶段。通过更新引用，我们将 CLI 重新连接到底层逻辑，但现在的连接是基于清晰定义的 `pyquipu-application` 接口，实现了架构上的解耦。

### 标签
#intent/refine #flow/ready #priority/high #comp/cli #comp/build #concept/executor #scope/core #ai/refine #task/domain/core #task/object/cli-wiring #task/action/refactor #task/state/end

---

### Script

#### Acts 1: 添加依赖
更新 CLI 的项目配置，引入新的应用包。

~~~~~act
patch_file packages/quipu-cli/pyproject.toml
~~~~~
~~~~~toml
dependencies = [
    "pyquipu-interfaces",
    "pyquipu-engine",
    "pyquipu-runtime",
    "pyquipu-common",
    "typer>=0.9.0",
    "textual>=0.58.0",
]
~~~~~
~~~~~toml
dependencies = [
    "pyquipu-interfaces",
    "pyquipu-engine",
    "pyquipu-runtime",
    "pyquipu-common",
    "pyquipu-application",
    "typer>=0.9.0",
    "textual>=0.58.0",
]
~~~~~

~~~~~act
patch_file packages/quipu-cli/pyproject.toml
~~~~~
~~~~~toml
[tool.uv.sources]
pyquipu-interfaces = { workspace = true }
pyquipu-engine = { workspace = true }
pyquipu-runtime = { workspace = true }
pyquipu-common = { workspace = true }
~~~~~
~~~~~toml
[tool.uv.sources]
pyquipu-interfaces = { workspace = true }
pyquipu-engine = { workspace = true }
pyquipu-runtime = { workspace = true }
pyquipu-common = { workspace = true }
pyquipu-application = { workspace = true }
~~~~~

#### Acts 2: 实现 UI 确认适配器
将原 `controller.py` 中的确认逻辑移动到 `ui_utils.py`，因为这是纯 CLI UI 逻辑。

~~~~~act
patch_file packages/quipu-cli/src/pyquipu/cli/ui_utils.py
~~~~~
~~~~~python
from typing import List, Optional

import click
import typer
from pyquipu.common.messaging import bus


def prompt_for_confirmation(prompt: str, diff_lines: Optional[List[str]] = None, default: bool = False) -> bool:
~~~~~
~~~~~python
from typing import List, Optional

import click
import typer
from pyquipu.common.messaging import bus
from pyquipu.interfaces.exceptions import OperationCancelledError


def confirmation_handler_for_executor(diff_lines: List[str], prompt: str) -> bool:
    """
    为 Executor 的确认处理器契约提供的适配器。
    它调用统一的提示器，并在用户取消时抛出异常。
    对于 'run' 操作，默认行为是继续，除非用户按下 'n'。
    """
    # 原始逻辑是 `char.lower() != "n"`，这相当于默认为 True
    confirmed = prompt_for_confirmation(prompt=prompt, diff_lines=diff_lines, default=True)
    if not confirmed:
        raise OperationCancelledError("User cancelled the operation.")
    # 执行器的处理器不使用布尔返回值，它依赖于异常。
    # 但为保持契约一致性，我们返回 True。
    return True


def prompt_for_confirmation(prompt: str, diff_lines: Optional[List[str]] = None, default: bool = False) -> bool:
~~~~~

#### Acts 3: 修复 `run.py`
更新 `run_quipu` 的导入，并注入 `confirmation_handler`。

~~~~~act
patch_file packages/quipu-cli/src/pyquipu/cli/commands/run.py
~~~~~
~~~~~python
import typer
from pyquipu.common.messaging import bus
from pyquipu.runtime.executor import Executor

from ..config import DEFAULT_ENTRY_FILE, DEFAULT_WORK_DIR
from ..controller import run_quipu
from ..logger_config import setup_logging

logger = logging.getLogger(__name__)
~~~~~
~~~~~python
import typer
from pyquipu.application.controller import run_quipu
from pyquipu.common.messaging import bus
from pyquipu.runtime.executor import Executor

from ..config import DEFAULT_ENTRY_FILE, DEFAULT_WORK_DIR
from ..logger_config import setup_logging
from ..ui_utils import confirmation_handler_for_executor

logger = logging.getLogger(__name__)
~~~~~

~~~~~act
patch_file packages/quipu-cli/src/pyquipu/cli/commands/run.py
~~~~~
~~~~~python
        if list_acts:
            from pyquipu.acts import register_core_acts

            from ..plugin_manager import PluginManager

            executor = Executor(root_dir=work_dir, yolo=True)
            register_core_acts(executor)
~~~~~
~~~~~python
        if list_acts:
            from pyquipu.acts import register_core_acts
            from pyquipu.application.plugin_manager import PluginManager

            executor = Executor(root_dir=work_dir, yolo=True)
            register_core_acts(executor)
~~~~~

~~~~~act
patch_file packages/quipu-cli/src/pyquipu/cli/commands/run.py
~~~~~
~~~~~python
        logger.info(f"已加载指令源: {source_desc}")
        logger.info(f"工作区根目录: {work_dir}")
        if yolo:
            bus.warning("run.warning.yoloEnabled")
        result = run_quipu(content=content, work_dir=work_dir, parser_name=parser_name, yolo=yolo)

        if result.message:
~~~~~
~~~~~python
        logger.info(f"已加载指令源: {source_desc}")
        logger.info(f"工作区根目录: {work_dir}")
        if yolo:
            bus.warning("run.warning.yoloEnabled")
        result = run_quipu(
            content=content,
            work_dir=work_dir,
            parser_name=parser_name,
            yolo=yolo,
            confirmation_handler=confirmation_handler_for_executor,
        )

        if result.message:
~~~~~

#### Acts 4: 修复 `axon.py`
更新 `Executor` 初始化逻辑（现在需要传入 handler），并修复 `PluginManager` 导入。

~~~~~act
patch_file packages/quipu-cli/src/pyquipu/cli/commands/axon.py
~~~~~
~~~~~python
from pyquipu.runtime.parser import detect_best_parser, get_parser

from ..config import DEFAULT_ENTRY_FILE, DEFAULT_WORK_DIR
from ..controller import confirmation_handler_for_executor
from ..logger_config import setup_logging
from ..plugin_manager import PluginManager

logger = logging.getLogger(__name__)
~~~~~
~~~~~python
from pyquipu.application.plugin_manager import PluginManager
from pyquipu.runtime.parser import detect_best_parser, get_parser

from ..config import DEFAULT_ENTRY_FILE, DEFAULT_WORK_DIR
from ..logger_config import setup_logging
from ..ui_utils import confirmation_handler_for_executor

logger = logging.getLogger(__name__)
~~~~~

#### Acts 5: 修复其他命令的导入 (`helpers.py`, `ui.py`, `remote.py`, `tui.py`)
主要涉及 `create_engine` 和 `find_git_repository_root` 的位置变更。

~~~~~act
patch_file packages/quipu-cli/src/pyquipu/cli/commands/helpers.py
~~~~~
~~~~~python
from pyquipu.engine.state_machine import Engine
from pyquipu.interfaces.models import QuipuNode

from ..factory import create_engine
from ..logger_config import setup_logging

logger = logging.getLogger(__name__)
~~~~~
~~~~~python
from pyquipu.application.factory import create_engine
from pyquipu.engine.state_machine import Engine
from pyquipu.interfaces.models import QuipuNode

from ..logger_config import setup_logging

logger = logging.getLogger(__name__)
~~~~~

~~~~~act
patch_file packages/quipu-cli/src/pyquipu/cli/commands/ui.py
~~~~~
~~~~~python
from pyquipu.common.messaging import bus

from ..config import DEFAULT_WORK_DIR, LOG_LEVEL
from ..factory import create_engine
from ..logger_config import configure_file_logging, setup_logging
from .helpers import _execute_visit, engine_context

logger = logging.getLogger(__name__)
~~~~~
~~~~~python
from pyquipu.application.factory import create_engine
from pyquipu.common.messaging import bus

from ..config import DEFAULT_WORK_DIR, LOG_LEVEL
from ..logger_config import configure_file_logging, setup_logging
from .helpers import _execute_visit, engine_context

logger = logging.getLogger(__name__)
~~~~~

~~~~~act
patch_file packages/quipu-cli/src/pyquipu/cli/commands/remote.py
~~~~~
~~~~~python
from pyquipu.engine.config import ConfigManager
from pyquipu.engine.git_db import GitDB

from ..config import DEFAULT_WORK_DIR
from ..logger_config import setup_logging
from ..utils import find_git_repository_root


class SyncMode(str, Enum):
~~~~~
~~~~~python
from pyquipu.application.utils import find_git_repository_root
from pyquipu.engine.config import ConfigManager
from pyquipu.engine.git_db import GitDB

from ..config import DEFAULT_WORK_DIR
from ..logger_config import setup_logging


class SyncMode(str, Enum):
~~~~~

~~~~~act
patch_file packages/quipu-cli/src/pyquipu/cli/tui.py
~~~~~
~~~~~python
from textual.widgets import DataTable, Footer, Header, Markdown, Static

from .factory import create_engine
from .view_model import GraphViewModel

logger = logging.getLogger(__name__)
~~~~~
~~~~~python
from pyquipu.application.factory import create_engine
from textual.widgets import DataTable, Footer, Header, Markdown, Static

from .view_model import GraphViewModel

logger = logging.getLogger(__name__)
~~~~~

### 下一步建议
代码修改已完成。请运行 `quipu run` 执行计划，然后运行测试套件（特别是 CLI 集成测试）以验证重构是否成功。
如果测试通过，就可以开始创建 `pyquipu-webapi` 了。
