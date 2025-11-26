# refactor: Decouple Executor from UI framework (typer)

## 用户需求
根据代码审查，`quipu-runtime` 包中的 `Executor` 类对 `typer` UI 框架存在直接依赖。这违反了分层架构原则，使得 `runtime` 模块无法在非 CLI 环境 (如测试、Web 服务) 中独立使用，并增加了测试的复杂性。

你需要通过依赖注入的方式解除此耦合。

## 评论
这是一个经典的跨层依赖问题。通过依赖注入，我们可以将 UI 交互的责任从核心的 `runtime` 模块移回它本应在的 `cli` 模块，同时保持 `Executor` 的功能不变。这不仅是良好的架构实践，也极大地提升了 `runtime` 模块的可测试性和可重用性。

## 目标
1.  移除 `quipu-runtime` 包中 `executor.py` 对 `typer` 的所有引用。
2.  修改 `Executor` 的构造函数，使其可以接受一个可选的 `confirmation_handler` 回调函数。
3.  `Executor` 的 `request_confirmation` 方法将调用此回调函数来处理用户交互，而不是直接调用 `typer`。
4.  在 `quipu-cli` 包的 `controller.py` 中，创建一个使用 `typer` 实现的确认处理器，并将其注入到 `Executor` 实例中。

## 基本原理
本次重构的核心是 **依赖注入 (Dependency Injection)** 和 **控制反转 (Inversion of Control)**。

-   **之前**: `Executor` (低层模块) **主动**依赖并**控制**了 `typer` (高层 UI 细节)。
-   **之后**: `Executor` 只定义了一个它需要的**接口** (一个可调用的 `confirmation_handler`)。创建 `Executor` 的高层模块 (`controller.py`) 负责提供符合该接口的具体**实现**。

这样，控制权就从低层模块反转到了高层模块。`Executor` 不再关心确认是如何获得的 (无论是通过 `typer`、一个 Web 表单还是在测试中自动返回 `True`)，它只关心能否得到一个布尔值结果。

## 标签
#intent/refine #flow/ready #priority/high
#comp/runtime #comp/cli #concept/executor
#scope/api #scope/core
#ai/instruct

---

## Script

### Acts 1: 重构 Executor 以接受依赖注入

我们将完全重写 `executor.py`，移除 `typer` 依赖，并引入 `confirmation_handler`。使用 `write_file` 是最安全的方式，可以确保所有导入和方法签名都正确更新。

~~~~~act
write_file packages/quipu-runtime/src/quipu/core/executor.py
~~~~~
~~~~~python
import logging
import difflib
from pathlib import Path
from typing import Dict, List, Any, Optional, Callable
import shlex

from quipu.core.types import Statement, ActFunction, ActContext
from quipu.core.exceptions import ExecutionError

logger = logging.getLogger(__name__)


# 定义确认处理器的签名: (diff_lines: List[str], prompt_message: str) -> bool
ConfirmationHandler = Callable[[List[str], str], bool]


class Executor:
    """
    执行器：负责管理可用的 Act 并执行解析后的语句。
    维护文件操作的安全边界。
    """

    def __init__(
        self,
        root_dir: Path,
        yolo: bool = False,
        confirmation_handler: Optional[ConfirmationHandler] = None,
    ):
        self.root_dir = root_dir.resolve()
        self.yolo = yolo
        self.confirmation_handler = confirmation_handler
        # Map: name -> (func, arg_mode, summarizer)
        self._acts: Dict[str, tuple[ActFunction, str, Any]] = {}

        if not self.root_dir.exists():
            try:
                self.root_dir.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                logger.warning(f"无法创建根目录 {self.root_dir}: {e}")

    def register(self, name: str, func: ActFunction, arg_mode: str = "hybrid", summarizer: Any = None):
        """
        注册一个新的操作
        :param arg_mode: 参数解析模式
                         - "hybrid": (默认) 合并行内参数和块内容 (inline + blocks)
                         - "exclusive": 互斥模式。优先使用行内参数；若无行内参数，则使用块内容。绝不混合。
                         - "block_only": 仅使用块内容，强制忽略行内参数。
        :param summarizer: 可选的 Summarizer 函数 (args, context_blocks) -> str
        """
        valid_modes = {"hybrid", "exclusive", "block_only"}
        if arg_mode not in valid_modes:
            raise ValueError(f"Invalid arg_mode: {arg_mode}. Must be one of {valid_modes}")

        self._acts[name] = (func, arg_mode, summarizer)
        logger.debug(f"注册 Act: {name} (Mode: {arg_mode})")

    def get_registered_acts(self) -> Dict[str, str]:
        """获取所有已注册的 Act 及其文档字符串"""
        return {name: data.__doc__ for name, data in self._acts.items()}

    def summarize_statement(self, stmt: Statement) -> str | None:
        """
        尝试为给定的语句生成摘要。
        如果找不到 Act 或 Act 没有 summarizer，返回 None。
        """
        raw_act_line = stmt["act"]
        try:
            tokens = shlex.split(raw_act_line)
        except ValueError:
            return None

        if not tokens:
            return None

        act_name = tokens
        inline_args = tokens[1:]
        contexts = stmt["contexts"]

        if act_name not in self._acts:
            return None

        _, _, summarizer = self._acts[act_name]

        if not summarizer:
            return None

        try:
            return summarizer(inline_args, contexts)
        except Exception as e:
            logger.warning(f"Summarizer for '{act_name}' failed: {e}")
            return None

    def resolve_path(self, rel_path: str) -> Path:
        """
        将相对路径转换为基于 root_dir 的绝对路径。
        包含基本的路径逃逸检查。
        """
        clean_rel = rel_path.strip()
        abs_path = (self.root_dir / clean_rel).resolve()

        if not str(abs_path).startswith(str(self.root_dir)):
            raise ExecutionError(f"安全警告：路径 '{clean_rel}' 试图访问工作区外部: {abs_path}")

        return abs_path

    def request_confirmation(self, file_path: Path, old_content: str, new_content: str) -> bool:
        """
        生成 diff 并请求用户确认。
        如果 self.yolo 为 True,则自动返回 True。
        如果没有提供 confirmation_handler，则安全地返回 False。
        """
        if self.yolo:
            return True

        diff = list(
            difflib.unified_diff(
                old_content.splitlines(keepends=True),
                new_content.splitlines(keepends=True),
                fromfile=f"a/{file_path.name}",
                tofile=f"b/{file_path.name}",
            )
        )

        if not diff:
            logger.info("⚠️  内容无变化")
            return True

        if not self.confirmation_handler:
            logger.warning("无确认处理器，已跳过需要用户确认的操作。")
            return False

        prompt = f"❓ 是否对 {file_path.name} 执行上述修改?"
        return self.confirmation_handler(diff, prompt)

    def execute(self, statements: List[Statement]):
        """执行一系列语句"""
        logger.info(f"Starting execution of {len(statements)} operations...")

        # 创建一个可重用的上下文对象
        ctx = ActContext(self)

        for i, stmt in enumerate(statements):
            raw_act_line = stmt["act"]
            block_contexts = stmt["contexts"]

            try:
                tokens = shlex.split(raw_act_line)
            except ValueError as e:
                raise ExecutionError(f"Error parsing Act command line: {raw_act_line} ({e})")

            if not tokens:
                logger.warning(f"Skipping empty instruction [{i + 1}/{len(statements)}]")
                continue

            act_name = tokens
            inline_args = tokens[1:]

            if act_name not in self._acts:
                logger.warning(f"Skipping unknown operation [{i + 1}/{len(statements)}]: {act_name}")
                continue

            func, arg_mode, _ = self._acts[act_name]

            final_args = []
            if arg_mode == "hybrid":
                final_args = inline_args + block_contexts
            elif arg_mode == "exclusive":
                if inline_args:
                    final_args = inline_args
                    if block_contexts:
                        logger.debug(
                            f"ℹ️  [{act_name} - Exclusive] Inline args detected, ignoring {len(block_contexts)} subsequent Block(s)."
                        )
                else:
                    final_args = block_contexts
            elif arg_mode == "block_only":
                if inline_args:
                    logger.warning(f"⚠️  [{act_name} - BlockOnly] Ignoring illegal inline arguments: {inline_args}")
                final_args = block_contexts

            try:
                logger.info(
                    f"Executing operation [{i + 1}/{len(statements)}]: {act_name} (Mode: {arg_mode}, Args: {len(final_args)})"
                )
                # 传递上下文对象，而不是 executor 实例
                func(ctx, final_args)
            except Exception as e:
                logger.error(f"Execution failed for '{act_name}': {e}")
                raise ExecutionError(f"An error occurred while executing '{act_name}': {e}") from e
~~~~~

### Acts 2: 在 Controller 中注入 Typer 处理器

现在，我们在 `controller.py` 中创建 `Executor` 的地方，定义一个基于 `typer` 的处理器并将其注入。

~~~~~act
replace packages/quipu-cli/src/quipu/cli/controller.py
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
~~~~~
~~~~~python
import logging
import sys
from pathlib import Path
from typing import List
import typer

from quipu.core.exceptions import ExecutionError as CoreExecutionError
from quipu.core.executor import Executor
from quipu.core.parser import detect_best_parser, get_parser
from quipu.core.result import QuipuResult
from quipu.core.state_machine import Engine
from quipu.acts import register_core_acts
from .factory import create_engine
from .plugin_manager import PluginManager

logger = logging.getLogger(__name__)
~~~~~

~~~~~act
replace packages/quipu-cli/src/quipu/cli/controller.py
~~~~~
~~~~~python
    def _setup_executor(self) -> Executor:
        """创建、配置并返回一个 Executor 实例。"""
        executor = Executor(root_dir=self.work_dir, yolo=self.yolo)

        # 加载核心 acts
        register_core_acts(executor)

        # 加载外部插件
        plugin_manager = PluginManager()
        plugin_manager.load_from_sources(executor, self.work_dir)

        return executor
~~~~~
~~~~~python
    def _setup_executor(self) -> Executor:
        """创建、配置并返回一个 Executor 实例，并注入 UI 依赖。"""

        def typer_confirmation_handler(diff_lines: List[str], prompt: str) -> bool:
            """一个封装了 Typer UI 逻辑的确认处理器。"""
            typer.echo("\n🔍 变更预览:")
            for line in diff_lines:
                if line.startswith("+"):
                    typer.secho(line.strip("\n"), fg=typer.colors.GREEN)
                elif line.startswith("-"):
                    typer.secho(line.strip("\n"), fg=typer.colors.RED)
                elif line.startswith("^"):
                    typer.secho(line.strip("\n"), fg=typer.colors.BLUE)
                else:
                    typer.echo(line.strip("\n"))
            typer.echo("")

            # 处理非交互式环境
            if not sys.stdin.isatty():
                logger.warning("非交互式环境，自动跳过确认。使用 --yolo 参数可自动批准。")
                return False

            return typer.confirm(prompt, default=True)

        executor = Executor(
            root_dir=self.work_dir,
            yolo=self.yolo,
            confirmation_handler=typer_confirmation_handler,
        )

        # 加载核心 acts
        register_core_acts(executor)

        # 加载外部插件
        plugin_manager = PluginManager()
        plugin_manager.load_from_sources(executor, self.work_dir)

        return executor
~~~~~
