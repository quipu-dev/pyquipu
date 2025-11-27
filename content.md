按需加载，动态隔离。

## fix: resolve TUI sqlite threading issue by isolating engine lifecycle

### 错误分析
当前架构中，`Engine` 和 `ViewModel` 在 `main.py` 的 CLI 主线程中被初始化，这建立了一个绑定到该线程的 SQLite 连接。随后，这些对象被注入到 `QuipuUiApp` 中。当 `QuipuUiApp` 启动（可能接管主线程或在异步循环中运行）并在其生命周期方法（如 `on_mount` 或后续的事件回调）中尝试使用该连接时，可能会触发 SQLite 的线程安全检查（`ProgrammingError`）或导致 GIL/锁竞争，表现为界面卡死且无法响应中断。

### 用户需求
用户需要 `quipu ui` 命令能够稳定启动和运行，避免因数据库资源竞争导致的崩溃或无响应。

### 评论
这是一个典型的资源生命周期管理问题。UI 组件应当拥有其所需的数据库连接的所有权，而不是依赖外部注入的、可能跨越了线程/协程边界的连接。将 `Engine` 的创建推迟到 TUI 的 `on_mount` 阶段可以确保连接是在实际使用它的上下文中创建的。

### 目标
1.  **资源隔离**：修改 `tui.py`，使其在内部管理 `Engine` 和 `ViewModel` 的生命周期，确保 SQLite 连接在 UI 线程中创建。
2.  **生命周期管理**：在 UI 退出时正确关闭数据库连接。
3.  **启动流程优化**：修改 `main.py`，仅在启动 UI 前使用一个临时的 `Engine` 进行“空历史”检查，然后彻底释放资源，再启动 UI。

### 基本原理
**Thread-Local Storage / Resource Ownership**: SQLite 连接通常不是线程安全的（或者在跨线程使用时需要非常小心）。最佳实践是遵循“谁使用，谁创建”的原则。通过在 Textual 的 `on_mount` 钩子中初始化数据库连接，我们保证了该连接与处理 UI 事件的循环处于同一上下文，消除了并发访问的隐患。

### 标签
#intent/fix #flow/ready #priority/critical
#comp/cli #concept/ui #concept/config
#scope/ux
#task/domain/ui #task/object/tui #task/action/stabilize #task/state/continue

---

### Script

#### Acts 1: TUI 内部接管 Engine 生命周期

在 `tui.py` 中，修改 `QuipuUiApp` 的构造函数，不再接收 `view_model`，而是接收 `work_dir`。在 `on_mount` 中执行初始化，并添加 `on_unmount` 进行清理。同时补充缺失的导入。

~~~~~act
patch_file
~~~~~
~~~~~path
packages/quipu-cli/src/quipu/cli/tui.py
~~~~~
~~~~~old_string
import sys
from datetime import datetime
from typing import List, Optional, Set, Dict, Callable, Tuple
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, DataTable, Markdown, Static
from textual.containers import Horizontal, Vertical
~~~~~
~~~~~new_string
import sys
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Set, Dict, Callable, Tuple
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, DataTable, Markdown, Static
from textual.containers import Horizontal, Vertical
~~~~~

~~~~~act
patch_file
~~~~~
~~~~~path
packages/quipu-cli/src/quipu/cli/tui.py
~~~~~
~~~~~old_string
from textual.coordinate import Coordinate
from textual import on

from quipu.core.models import QuipuNode
from .view_model import GraphViewModel

# 定义 UI 返回类型: (动作类型, 数据)
~~~~~
~~~~~new_string
from textual.coordinate import Coordinate
from textual import on

from quipu.core.models import QuipuNode
from quipu.core.state_machine import Engine
from .view_model import GraphViewModel
from .factory import create_engine

# 定义 UI 返回类型: (动作类型, 数据)
~~~~~

~~~~~act
patch_file
~~~~~
~~~~~path
packages/quipu-cli/src/quipu/cli/tui.py
~~~~~
~~~~~old_string
    BINDINGS = [
        Binding("q", "quit", "退出"),
        Binding("c", "checkout_node", "检出节点"),
~~~~~
~~~~~new_string
    BINDINGS = [
        Binding("q", "quit", "退出"),
        Binding("c", "checkout_node", "检出节点"),
~~~~~

~~~~~act
patch_file
~~~~~
~~~~~path
packages/quipu-cli/src/quipu/cli/tui.py
~~~~~
~~~~~old_string
    def __init__(self, view_model: GraphViewModel):
        super().__init__()
        self.view_model = view_model

        # 状态
        self.show_unreachable = True
        self.is_split_mode = False
        self.current_selected_node: Optional[QuipuNode] = None

    def compose(self) -> ComposeResult:
~~~~~
~~~~~new_string
    def __init__(self, work_dir: Path):
        super().__init__()
        self.work_dir = work_dir
        self.engine: Optional[Engine] = None
        self.view_model: Optional[GraphViewModel] = None

        # 状态
        self.show_unreachable = True
        self.is_split_mode = False
        self.current_selected_node: Optional[QuipuNode] = None

    def compose(self) -> ComposeResult:
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
        # The ViewModel is now initialized in main.py before the app is run.
        self._load_page(1)

    def _load_page(self, page_number: int) -> None:
~~~~~
~~~~~new_string
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
~~~~~

#### Acts 2: 修正 Main 入口逻辑

修改 `main.py` 中的 `ui` 命令，使用临时 Engine 检查状态后即关闭，然后启动拥有独立 Engine 的 `QuipuUiApp`。

~~~~~act
patch_file
~~~~~
~~~~~path
packages/quipu-cli/src/quipu/cli/main.py
~~~~~
~~~~~old_string
    setup_logging()

    # 使用懒加载模式创建 Engine，避免启动时加载全量数据
    engine = create_engine(work_dir, lazy=True)
    current_hash = engine.git_db.get_tree_hash()

    # 实例化 ViewModel
    view_model = GraphViewModel(reader=engine.reader, current_hash=current_hash)

    # ViewModel 初始化时会快速检查节点总数
    # view_model.initialize() # <--- 移除此处的预初始化，让 TUI 自己在其线程中完成
    
    engine_closed = False
    try:
        # ViewModel 初始化时会快速检查节点总数
        view_model.initialize()
        if view_model.total_nodes == 0:
            typer.secho("📜 历史记录为空，无需启动 UI。", fg=typer.colors.YELLOW, err=True)
            ctx.exit(0)

        # 注入 ViewModel 到 UI
        app_instance = QuipuUiApp(view_model=view_model)
        result = app_instance.run()

        # 处理 UI 返回结果
        if result:
            action, data = result

            if action == "checkout":
                target_hash = data
                # 我们相信从 UI 返回的 hash 是有效的
                typer.secho(f"\n> TUI 请求检出到: {target_hash[:7]}", err=True)
                _execute_visit(ctx, engine, target_hash, f"正在导航到 TUI 选定节点: {target_hash[:7]}")

            elif action == "dump":
                # 直接将内容打印到 stdout，方便用户通过管道处理 (e.g. quipu ui | less)
                print(data)
                ctx.exit(0)
                
    finally:
        if engine and not engine_closed:
            engine.close()
            engine_closed = True
~~~~~
~~~~~new_string
    setup_logging()

    # 1. 预检查阶段：使用临时 Engine 快速检查历史是否为空
    temp_engine = create_engine(work_dir, lazy=True)
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
    if result:
        action, data = result

        if action == "checkout":
            target_hash = data
            # 重新创建 Engine 执行导航操作
            action_engine = create_engine(work_dir, lazy=True)
            try:
                typer.secho(f"\n> TUI 请求检出到: {target_hash[:7]}", err=True)
                _execute_visit(ctx, action_engine, target_hash, f"正在导航到 TUI 选定节点: {target_hash[:7]}")
            finally:
                action_engine.close()

        elif action == "dump":
            # 直接将内容打印到 stdout
            print(data)
            ctx.exit(0)
~~~~~

### 下一步建议
运行 `quipu ui` 验证启动速度和稳定性。此时应该不会再出现闪烁卡死现象。如果一切正常，可以继续完善 UI 的细节功能。
