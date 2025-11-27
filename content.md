## fix: enable file-based debug logging for TUI troubleshooting

### 错误分析
症状“屏幕闪烁后卡住”通常是 TUI 应用（Textual）与标准控制台输出（stdout/stderr）冲突的典型表现。
1.  当前 `setup_logging()` 配置为向 `stderr` 输出日志。
2.  Textual 启动后接管了终端控制权。
3.  如果底层组件（如 Engine 初始化或 SQLite 连接）产生日志输出，或者因为错误尝试打印 traceback 到 stderr，会破坏 TUI 的渲染缓冲区，甚至导致 I/O 死锁。
4.  此外，由于看不到日志，无法确定是否是因为 SQLite 锁等待导致的挂起。

### 用户需求
用户需要“创建 debug 日志用于排查错误”，并且需要解决 TUI 卡死的问题。

### 评论
将日志重定向到文件是 TUI 开发的最佳实践。这不仅解决了 I/O 冲突，还能捕获启动过程中的详细调试信息。

### 目标
1.  修改 `logger_config.py`: 增加 `configure_file_logging` 函数，用于将日志切换到文件。
2.  修改 `main.py`: 在 `ui` 命令启动前，强制开启文件日志（`.quipu/tui.debug.log`），并设置为 DEBUG 级别。
3.  修改 `tui.py`: 在关键生命周期节点（`on_mount`, `_load_page`）添加详细的 debug 日志埋点。

### 基本原理
**I/O Stream Isolation**: TUI 应用独占 Console 用于绘制 UI，所有非 UI 的文本输出（日志、错误堆栈）必须重定向到文件，以保证界面渲染线程不被阻塞或破坏。

### 标签
#intent/fix #flow/ready #priority/high
#comp/cli #concept/ui #concept/config
#scope/dx
#task/domain/ui #task/object/logging #task/action/debug #task/state/continue

---

### Script

#### Acts 1: 增强日志配置能力

修改 `logger_config.py`，添加文件日志配置功能。

~~~~~act
patch_file
~~~~~
~~~~~path
packages/quipu-cli/src/quipu/cli/logger_config.py
~~~~~
~~~~~old_string
import logging
import sys
from .config import LOG_LEVEL


def setup_logging():
    """配置全局日志记录器"""
    # 配置根记录器，确保所有模块(acts.*, core.*)的日志都能被捕获
    root_logger = logging.getLogger()
    root_logger.setLevel(LOG_LEVEL)

    # 避免重复添加 handler
    if not root_logger.handlers:
        # 关键修改: 将日志输出到 stderr，防止污染管道 stdout
        handler = logging.StreamHandler(sys.stderr)
        formatter = logging.Formatter(
            fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
        )
        handler.setFormatter(formatter)
        root_logger.addHandler(handler)

    return root_logger
~~~~~
~~~~~new_string
import logging
import sys
from pathlib import Path
from .config import LOG_LEVEL


def setup_logging():
    """配置全局日志记录器 (默认 stderr)"""
    root_logger = logging.getLogger()
    root_logger.setLevel(LOG_LEVEL)

    if not root_logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        formatter = logging.Formatter(
            fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
        )
        handler.setFormatter(formatter)
        root_logger.addHandler(handler)

    return root_logger


def configure_file_logging(log_path: Path):
    """
    将日志重定向到文件，专为 TUI 模式设计。
    强制使用 DEBUG 级别以捕获详细信息。
    """
    root_logger = logging.getLogger()
    
    # 移除所有现有的 handler (通常是 stderr stream handler)
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # 确保父目录存在
    if not log_path.parent.exists():
        log_path.parent.mkdir(parents=True, exist_ok=True)

    file_handler = logging.FileHandler(log_path, mode='w', encoding='utf-8')
    formatter = logging.Formatter(
        fmt="%(asctime)s.%(msecs)03d - %(name)s - %(levelname)s - %(message)s", 
        datefmt="%H:%M:%S"
    )
    file_handler.setFormatter(formatter)
    
    root_logger.addHandler(file_handler)
    root_logger.setLevel(logging.DEBUG)  # TUI 调试模式强制 DEBUG
    
    logging.info(f"🚀 Logging redirected to file: {log_path}")
~~~~~

#### Acts 2: 在 CLI 入口启用文件日志

修改 `main.py` 的 `ui` 命令，在启动前切换日志模式。

~~~~~act
patch_file
~~~~~
~~~~~path
packages/quipu-cli/src/quipu/cli/main.py
~~~~~
~~~~~old_string
from typing import Annotated, Optional, Dict

from .logger_config import setup_logging
from .controller import run_quipu
from .config import DEFAULT_WORK_DIR, DEFAULT_ENTRY_FILE, PROJECT_ROOT
~~~~~
~~~~~new_string
from typing import Annotated, Optional, Dict

from .logger_config import setup_logging, configure_file_logging
from .controller import run_quipu
from .config import DEFAULT_WORK_DIR, DEFAULT_ENTRY_FILE, PROJECT_ROOT
~~~~~

~~~~~act
patch_file
~~~~~
~~~~~path
packages/quipu-cli/src/quipu/cli/main.py
~~~~~
~~~~~old_string
        typer.secho("💡 请运行: pip install 'textual>=0.58.0'", err=True)
        ctx.exit(1)

    setup_logging()

    # 1. 预检查阶段：使用临时 Engine 快速检查历史是否为空
    temp_engine = create_engine(work_dir, lazy=True)
~~~~~
~~~~~new_string
        typer.secho("💡 请运行: pip install 'textual>=0.58.0'", err=True)
        ctx.exit(1)

    # 在 TUI 模式下，强制将日志重定向到文件，防止 stderr 干扰 UI 渲染
    log_file = work_dir / ".quipu" / "tui.debug.log"
    configure_file_logging(log_file)
    logging.info("Starting Quipu UI command...")

    # 1. 预检查阶段：使用临时 Engine 快速检查历史是否为空
    logging.debug("Creating temporary engine for pre-check...")
    temp_engine = create_engine(work_dir, lazy=True)
~~~~~

~~~~~act
patch_file
~~~~~
~~~~~path
packages/quipu-cli/src/quipu/cli/main.py
~~~~~
~~~~~old_string
    try:
        if temp_engine.reader.get_node_count() == 0:
            typer.secho("📜 历史记录为空，无需启动 UI。", fg=typer.colors.YELLOW, err=True)
            ctx.exit(0)
    finally:
        temp_engine.close()

    # 2. 启动 UI 阶段：资源由 UI 内部独立管理
    app_instance = QuipuUiApp(work_dir=work_dir)
    result = app_instance.run()

    # 3. 处理结果阶段：此时 UI 已关闭，我们需要重新获取 Engine 来执行业务操作
~~~~~
~~~~~new_string
    try:
        count = temp_engine.reader.get_node_count()
        logging.debug(f"Pre-check complete. Node count: {count}")
        if count == 0:
            typer.secho("📜 历史记录为空，无需启动 UI。", fg=typer.colors.YELLOW, err=True)
            ctx.exit(0)
    finally:
        logging.debug("Closing temporary engine.")
        temp_engine.close()

    # 2. 启动 UI 阶段：资源由 UI 内部独立管理
    logging.info("Launching QuipuUiApp...")
    app_instance = QuipuUiApp(work_dir=work_dir)
    result = app_instance.run()
    logging.info(f"QuipuUiApp finished with result: {result}")

    # 3. 处理结果阶段：此时 UI 已关闭，我们需要重新获取 Engine 来执行业务操作
~~~~~

#### Acts 3: 在 TUI 内部埋点

修改 `tui.py`，在关键路径添加日志。

~~~~~act
patch_file
~~~~~
~~~~~path
packages/quipu-cli/src/quipu/cli/tui.py
~~~~~
~~~~~old_string
import sys
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Set, Dict, Callable, Tuple
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, DataTable, Markdown, Static
~~~~~
~~~~~new_string
import sys
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Set, Dict, Callable, Tuple
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, DataTable, Markdown, Static
~~~~~

~~~~~act
patch_file
~~~~~
~~~~~path
packages/quipu-cli/src/quipu/cli/tui.py
~~~~~
~~~~~old_string
from .factory import create_engine

# 定义 UI 返回类型: (动作类型, 数据)
# 动作: "checkout" | "dump"
UiResult = Tuple[str, str]
~~~~~
~~~~~new_string
from .factory import create_engine

logger = logging.getLogger(__name__)

# 定义 UI 返回类型: (动作类型, 数据)
# 动作: "checkout" | "dump"
UiResult = Tuple[str, str]
~~~~~

~~~~~act
patch_file
~~~~~
~~~~~path
packages/quipu-cli/src/quipu/cli/tui.py
~~~~~
~~~~~old_string
    def on_mount(self) -> None:
        """Loads the first page of data."""
        self.engine = create_engine(self.work_dir, lazy=True)
        current_hash = self.engine.git_db.get_tree_hash()
        self.view_model = GraphViewModel(reader=self.engine.reader, current_hash=current_hash)
        self.view_model.initialize()
        self._load_page(1)

    def on_unmount(self) -> None:
        if self.engine:
            self.engine.close()

    def _load_page(self, page_number: int) -> None:
        """Loads and displays a specific page of nodes."""
        nodes = self.view_model.load_page(page_number)
        if not nodes and page_number > 1:
            self.bell()  # Give feedback on boundary
            return
~~~~~
~~~~~new_string
    def on_mount(self) -> None:
        """Loads the first page of data."""
        logger.debug("TUI: on_mount started.")
        try:
            logger.debug("TUI: Creating engine...")
            self.engine = create_engine(self.work_dir, lazy=True)
            
            logger.debug("TUI: Getting current hash...")
            current_hash = self.engine.git_db.get_tree_hash()
            
            logger.debug("TUI: Initializing ViewModel...")
            self.view_model = GraphViewModel(reader=self.engine.reader, current_hash=current_hash)
            self.view_model.initialize()
            
            logger.debug("TUI: Loading first page...")
            self._load_page(1)
        except Exception as e:
            logger.exception("Error in TUI on_mount")
            raise e

    def on_unmount(self) -> None:
        logger.debug("TUI: on_unmount called, closing engine.")
        if self.engine:
            self.engine.close()

    def _load_page(self, page_number: int) -> None:
        """Loads and displays a specific page of nodes."""
        logger.debug(f"TUI: Loading page {page_number}")
        nodes = self.view_model.load_page(page_number)
        logger.debug(f"TUI: Page {page_number} loaded with {len(nodes)} nodes.")
        
        if not nodes and page_number > 1:
            self.bell()  # Give feedback on boundary
            return
~~~~~

### 下一步建议
请再次运行 `quipu ui`。这次即使界面卡住，你也可以查看 `.quipu/tui.debug.log` 来获取详细的错误信息。请将日志内容反馈给我，以便进行精准修复。
