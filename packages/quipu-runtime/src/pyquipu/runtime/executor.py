import difflib
import logging
import shlex
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from pyquipu.common.messaging import bus
from pyquipu.interfaces.exceptions import ExecutionError, OperationCancelledError
from pyquipu.interfaces.types import ActContext, ActFunction, Statement

logger = logging.getLogger(__name__)


# 定义确认处理器的签名: (diff_lines: List[str], prompt_message: str) -> bool
ConfirmationHandler = Callable[[List[str], str], bool]


class Executor:
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
                bus.warning("runtime.executor.warning.createRootDirFailed", path=self.root_dir, error=e)

    def register(self, name: str, func: ActFunction, arg_mode: str = "hybrid", summarizer: Any = None):
        valid_modes = {"hybrid", "exclusive", "block_only"}
        if arg_mode not in valid_modes:
            raise ValueError(f"Invalid arg_mode: {arg_mode}. Must be one of {valid_modes}")

        self._acts[name] = (func, arg_mode, summarizer)
        logger.debug(f"注册 Act: {name} (Mode: {arg_mode})")

    def get_registered_acts(self) -> Dict[str, str]:
        return {name: data[0].__doc__ for name, data in self._acts.items()}

    def summarize_statement(self, stmt: Statement) -> str | None:
        raw_act_line = stmt["act"]
        try:
            tokens = shlex.split(raw_act_line)
        except ValueError:
            return None

        if not tokens:
            return None

        act_name = tokens[0]
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
            # Summarizer 失败不应影响主流程，仅记录日志
            logger.warning(f"Summarizer for '{act_name}' failed: {e}")
            return None

    def resolve_path(self, rel_path: str) -> Path:
        clean_rel = rel_path.strip()
        abs_path = (self.root_dir / clean_rel).resolve()

        if not str(abs_path).startswith(str(self.root_dir)):
            raise ExecutionError(f"安全警告：路径 '{clean_rel}' 试图访问工作区外部: {abs_path}")

        return abs_path

    def request_confirmation(self, file_path: Path, old_content: str, new_content: str):
        if self.yolo:
            return

        diff = list(
            difflib.unified_diff(
                old_content.splitlines(keepends=True),
                new_content.splitlines(keepends=True),
                fromfile=f"a/{file_path.name}",
                tofile=f"b/{file_path.name}",
            )
        )

        if not diff:
            bus.info("runtime.executor.info.noChange")
            return

        if not self.confirmation_handler:
            bus.warning("runtime.executor.warning.noConfirmHandler")
            raise OperationCancelledError("No confirmation handler is configured.")

        prompt = f"❓ 是否对 {file_path.name} 执行上述修改?"
        # 此调用现在要么成功返回，要么抛出 OperationCancelledError
        self.confirmation_handler(diff, prompt)

    def execute(self, statements: List[Statement]):
        bus.info("runtime.executor.info.starting", count=len(statements))

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
                bus.warning("runtime.executor.warning.skipEmpty", current=i + 1, total=len(statements))
                continue

            act_name = tokens[0]
            inline_args = tokens[1:]

            if act_name not in self._acts:
                bus.warning(
                    "runtime.executor.warning.skipUnknown",
                    current=i + 1,
                    total=len(statements),
                    act_name=act_name,
                )
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
                            f"ℹ️  [{act_name} - Exclusive] Inline args detected,"
                            f" ignoring {len(block_contexts)} subsequent Block(s)."
                        )
                else:
                    final_args = block_contexts
            elif arg_mode == "block_only":
                if inline_args:
                    bus.warning("runtime.executor.warning.ignoreInlineArgs", act_name=act_name, args=inline_args)
                final_args = block_contexts

            try:
                bus.info(
                    "runtime.executor.info.executing",
                    current=i + 1,
                    total=len(statements),
                    act_name=act_name,
                    mode=arg_mode,
                    arg_count=len(final_args),
                )
                # 传递上下文对象，而不是 executor 实例
                func(ctx, final_args)
            except OperationCancelledError:
                # 显式地重新抛出，以确保它能被上层捕获
                raise
            except Exception as e:
                # 记录详细日志供调试，同时抛出标准错误供上层展示
                logger.error(f"Execution failed for '{act_name}': {e}")
                raise ExecutionError(f"An error occurred while executing '{act_name}': {e}") from e
