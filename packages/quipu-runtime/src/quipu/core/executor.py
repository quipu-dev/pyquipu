import logging
import difflib
import typer
import shlex
import sys
from pathlib import Path
from typing import Dict, List, Any
from quipu.core.types import Statement, ActFunction, ActContext
from quipu.core.exceptions import ExecutionError

logger = logging.getLogger(__name__)


class Executor:
    """
    执行器：负责管理可用的 Act 并执行解析后的语句。
    维护文件操作的安全边界。
    """

    def __init__(self, root_dir: Path, yolo: bool = False):
        self.root_dir = root_dir.resolve()
        self.yolo = yolo
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
        return {name: data[0].__doc__ for name, data in self._acts.items()}

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

        typer.echo("\n🔍 变更预览:")
        for line in diff:
            if line.startswith("+"):
                typer.secho(line.strip("\n"), fg=typer.colors.GREEN)
            elif line.startswith("-"):
                typer.secho(line.strip("\n"), fg=typer.colors.RED)
            elif line.startswith("^"):
                typer.secho(line.strip("\n"), fg=typer.colors.BLUE)
            else:
                typer.echo(line.strip("\n"))

        typer.echo("")
        prompt = f"❓ 是否对 {file_path.name} 执行上述修改?"

        if sys.stdin.isatty():
            return typer.confirm(prompt, default=True)

        try:
            with open("/dev/tty", "r") as tty:
                typer.echo(f"{prompt} [Y/n]: ", nl=False)
                answer = tty.readline().strip().lower()
                return not answer or answer in ("y", "yes")
        except Exception as e:
            logger.error(f"❌ 无法获取交互输入 (非 TTY 环境且无法访问 /dev/tty): {e}")
            logger.warning("提示: 在非交互式环境中使用，请考虑添加 --yolo 参数以自动确认。")
            return False

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

            act_name = tokens[0]
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
