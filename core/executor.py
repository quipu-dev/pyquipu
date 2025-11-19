import logging
import difflib
import typer
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
        self._acts: Dict[str, ActFunction] = {}
        
        # 确保根目录存在
        if not self.root_dir.exists():
            try:
                self.root_dir.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                logger.warning(f"无法创建根目录 {self.root_dir}: {e}")

    def register(self, name: str, func: ActFunction):
        """注册一个新的操作"""
        self._acts[name] = func
        logger.debug(f"注册 Act: {name}")

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

        return typer.confirm(f"❓ 是否对 {file_path.name} 执行上述修改?", default=True)

    def execute(self, statements: List[Statement]):
        """执行语句序列"""
        logger.info(f"开始执行 {len(statements)} 个操作...")
        
        for i, stmt in enumerate(statements):
            act_name = stmt["act"]
            contexts = stmt["contexts"]
            
            if act_name not in self._acts:
                logger.warning(f"跳过未知操作 [{i+1}/{len(statements)}]: {act_name}")
                continue

            try:
                logger.info(f"执行操作 [{i+1}/{len(statements)}]: {act_name}")
                self._acts[act_name](self, contexts)
            except Exception as e:
                logger.error(f"执行失败 '{act_name}': {e}")
                # 根据策略，这里可以选择抛出异常终止整个流程，或者继续
                raise ExecutionError(f"在执行 '{act_name}' 时发生错误: {e}") from e
