import logging
import difflib
import typer
import shlex
import sys
from pathlib import Path
from typing import Dict, Callable, List, Any
from .types import Statement
from .exceptions import ExecutionError

logger = logging.getLogger(__name__)

# Act 函数签名定义: (executor_instance, args) -> None
ActFunction = Callable[['Executor', List[str]], None]

class Executor:
    """
    执行器：负责管理可用的 Act 并执行解析后的语句。
    维护文件操作的安全边界。
    """

    def __init__(self, root_dir: Path, yolo: bool = False):
        self.root_dir = root_dir.resolve()
        self.yolo = yolo
        # 存储结构变更为: name -> (func, arg_mode)
        # arg_mode: "hybrid", "smart", "block_only"
        self._acts: Dict[str, tuple[ActFunction, str]] = {}
        
        # 确保根目录存在
        if not self.root_dir.exists():
            try:
                self.root_dir.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                logger.warning(f"无法创建根目录 {self.root_dir}: {e}")

    def register(self, name: str, func: ActFunction, arg_mode: str = "hybrid"):
        """
        注册一个新的操作
        :param arg_mode: 参数解析模式
                         - "hybrid": (默认) 合并行内参数和块内容 (inline + blocks)
                         - "exclusive": 互斥模式。优先使用行内参数；若无行内参数，则使用块内容。绝不混合。
                         - "block_only": 仅使用块内容，强制忽略行内参数。
        """
        valid_modes = {"hybrid", "exclusive", "block_only"}
        if arg_mode not in valid_modes:
            raise ValueError(f"Invalid arg_mode: {arg_mode}. Must be one of {valid_modes}")
            
        self._acts[name] = (func, arg_mode)
        logger.debug(f"注册 Act: {name} (Mode: {arg_mode})")

    def get_registered_acts(self) -> Dict[str, str]:
        """获取所有已注册的 Act 及其文档字符串"""
        return {name: data[0].__doc__ for name, data in self._acts.items()}

    def resolve_path(self, rel_path: str) -> Path:
        """
        将相对路径转换为基于 root_dir 的绝对路径。
        包含基本的路径逃逸检查。
        """
        # 清理路径中的空白字符
        clean_rel = rel_path.strip()
        
        # 拼接路径
        abs_path = (self.root_dir / clean_rel).resolve()
        
        # 简单的安全检查：确保最终路径在 root_dir 内部
        # 注意：在某些 symlink 场景下可能需要更复杂的判断，这里做基础防护
        if not str(abs_path).startswith(str(self.root_dir)):
            raise ExecutionError(f"安全警告：路径 '{clean_rel}' 试图访问工作区外部: {abs_path}")
            
        return abs_path

    def request_confirmation(self, file_path: Path, old_content: str, new_content: str) -> bool:
        """
        生成 diff 并请求用户确认。
        如果 self.yolo 为 True，则自动返回 True。
        """
        if self.yolo:
            return True

        # 生成 Diff
        diff = list(difflib.unified_diff(
            old_content.splitlines(keepends=True),
            new_content.splitlines(keepends=True),
            fromfile=f"a/{file_path.name}",
            tofile=f"b/{file_path.name}",
        ))

        if not diff:
            logger.info("⚠️  内容无变化")
            return True

        # 打印 Diff (手动简单的着色)
        typer.echo("\n🔍 变更预览:")
        for line in diff:
            if line.startswith('+'):
                typer.secho(line.strip('\n'), fg=typer.colors.GREEN)
            elif line.startswith('-'):
                typer.secho(line.strip('\n'), fg=typer.colors.RED)
            elif line.startswith('^'):
                typer.secho(line.strip('\n'), fg=typer.colors.BLUE)
            else:
                typer.echo(line.strip('\n'))
        
        typer.echo("") # 空行

        prompt = f"❓ 是否对 {file_path.name} 执行上述修改?"

        # 处理交互输入：
        # 如果 STDIN 是终端，直接使用 Typer (Click) 的标准 confirm
        if sys.stdin.isatty():
            return typer.confirm(prompt, default=True)
        
        # 如果 STDIN 被管道占用 (如 echo "..." | axon)，我们需要尝试打开 /dev/tty 来获取用户输入
        # 注意：这主要适用于 Linux/macOS。Windows 上可能需要 CONIN$ 处理，但 Axon 目前主要针对 Unix 风格环境。
        try:
            # explicitly open the controlling terminal for reading
            with open("/dev/tty", "r") as tty:
                typer.echo(f"{prompt} [Y/n]: ", nl=False)
                answer = tty.readline().strip().lower()
                if not answer:
                    return True # Default Yes
                return answer in ("y", "yes")
        except Exception as e:
            # 如果无法打开终端进行交互（例如在完全无头的 CI 环境中且没开 YOLO），为了安全，默认拒绝
            logger.error(f"❌ 无法获取交互输入 (非 TTY 环境且无法访问 /dev/tty): {e}")
            logger.warning("提示: 在非交互式环境中使用，请考虑添加 --yolo 参数以自动确认。")
            return False

    def execute(self, statements: List[Statement]):
        """执行语句序列"""
        logger.info(f"开始执行 {len(statements)} 个操作...")
        
        for i, stmt in enumerate(statements):
            raw_act_line = stmt["act"]
            block_contexts = stmt["contexts"]
            
            # 1. 解析 Act 行：分离命令名和行内参数
            try:
                # 使用 shlex 支持引号，例如: write_file "my file.txt"
                tokens = shlex.split(raw_act_line)
            except ValueError as e:
                # 通常是引号未闭合
                raise ExecutionError(f"Act 命令行解析错误: {raw_act_line} ({e})")
            
            if not tokens:
                logger.warning(f"跳过空指令 [{i+1}/{len(statements)}]")
                continue
                
            act_name = tokens[0]
            inline_args = tokens[1:]
            
            if act_name not in self._acts:
                logger.warning(f"跳过未知操作 [{i+1}/{len(statements)}]: {act_name}")
                continue

            func, arg_mode = self._acts[act_name]

            # 2. 参数合并策略 (ArgMode Protocol)
            final_args = []
            
            if arg_mode == "hybrid":
                # 贪婪模式：合并所有来源
                final_args = inline_args + block_contexts
                
            elif arg_mode == "exclusive":
                # 互斥模式：有行内用行内，否则用块
                if inline_args:
                    final_args = inline_args
                    if block_contexts:
                        logger.debug(f"ℹ️  [{act_name} - Exclusive] 检测到行内参数，已忽略随后的 {len(block_contexts)} 个 Block。")
                else:
                    final_args = block_contexts
                    
            elif arg_mode == "block_only":
                # 严格模式：只看块
                if inline_args:
                    logger.warning(f"⚠️  [{act_name} - BlockOnly] 忽略了非法的行内参数: {inline_args}")
                final_args = block_contexts
            
            else:
                # Fallback (不应发生，register 已校验)
                final_args = inline_args + block_contexts

            try:
                logger.info(f"执行操作 [{i+1}/{len(statements)}]: {act_name} (Mode: {arg_mode}, Args: {len(final_args)})")
                func(self, final_args)
            except Exception as e:
                logger.error(f"执行失败 '{act_name}': {e}")
                # 根据策略，这里可以选择抛出异常终止整个流程，或者继续
                raise ExecutionError(f"在执行 '{act_name}' 时发生错误: {e}") from e