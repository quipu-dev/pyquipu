import typer
import logging
import inspect
import sys
from pathlib import Path
from typing import Annotated, Optional

from logger_config import setup_logging
from core.parser import get_parser, list_parsers, detect_best_parser
from core.executor import Executor
from acts.basic import register_basic_acts
from acts.check import register_check_acts
from acts.git import register_git_acts
from acts.shell import register_shell_acts
from acts.read import register_read_acts
from acts.refactor import register_refactor_acts
from acts.memory import register_memory_acts
from config import DEFAULT_WORK_DIR, DEFAULT_ENTRY_FILE

# 初始化日志
setup_logging()
logger = logging.getLogger(__name__)

def main(
    ctx: typer.Context,
    file: Annotated[
        Optional[Path], 
        typer.Argument(
            help=f"包含 Markdown 指令的文件路径。若省略则尝试读取 STDIN 或默认文件 {DEFAULT_ENTRY_FILE.name}",
            resolve_path=True
        )
    ] = None,
    work_dir: Annotated[
        Path, 
        typer.Option(
            "--work-dir", "-w",
            help="操作执行的根目录（工作区）",
            file_okay=False,
            dir_okay=True,
            resolve_path=True
        )
    ] = DEFAULT_WORK_DIR,
    parser_name: Annotated[
        str,
        typer.Option(
            "--parser", "-p",
            help=f"选择解析器语法。默认为 'auto' (自动检测)。可用: {['auto'] + list_parsers()}",
        )
    ] = "auto",
    yolo: Annotated[
        bool,
        typer.Option(
            "--yolo", "-y",
            help="跳过所有确认步骤，直接执行 (You Only Look Once)。",
        )
    ] = False,
    list_acts: Annotated[
        bool,
        typer.Option(
            "--list-acts", "-l",
            help="列出所有可用的操作指令及其说明。",
        )
    ] = False
):
    """
    Axon: 执行 Markdown 文件中的操作指令。
    支持从文件参数、管道 (STDIN) 或默认文件中读取指令。
    """
    if list_acts:
        # 初始化一个临时 Executor 用于获取注册表
        executor = Executor(root_dir=Path("."), yolo=True)
        
        register_basic_acts(executor)
        register_check_acts(executor)
        register_git_acts(executor)
        register_shell_acts(executor)
        register_read_acts(executor)
        register_refactor_acts(executor)
        register_memory_acts(executor)
        
        typer.secho("\n📋 可用的 Axon 指令列表:\n", fg=typer.colors.GREEN, bold=True)
        
        acts = executor.get_registered_acts()
        for name in sorted(acts.keys()):
            doc = acts[name]
            clean_doc = inspect.cleandoc(doc) if doc else "暂无说明"
            indented_doc = "\n".join(f"   {line}" for line in clean_doc.splitlines())
            
            typer.secho(f"🔹 {name}", fg=typer.colors.CYAN, bold=True)
            typer.echo(f"{indented_doc}\n")
            
        raise typer.Exit()

    # --- 输入源处理逻辑 ---
    
    content = ""
    source_desc = ""

    # 1. 优先检查显式文件参数
    if file:
        if not file.exists():
            typer.secho(f"❌ 错误: 找不到指令文件: {file}", fg=typer.colors.RED)
            raise typer.Exit(code=1)
        if not file.is_file():
            typer.secho(f"❌ 错误: 路径不是文件: {file}", fg=typer.colors.RED)
            raise typer.Exit(code=1)
        
        content = file.read_text(encoding="utf-8")
        source_desc = f"文件 ({file.name})"

    # 2. 检查 STDIN (管道/重定向)
    elif not sys.stdin.isatty():
        # 当 sys.stdin.isatty() 为 False 时，说明有数据被 pipe 进来
        logger.info("正在从 STDIN (管道) 读取指令...")
        content = sys.stdin.read()
        source_desc = "STDIN (管道流)"

    # 3. 回退到默认文件
    elif DEFAULT_ENTRY_FILE.exists():
        content = DEFAULT_ENTRY_FILE.read_text(encoding="utf-8")
        source_desc = f"默认文件 ({DEFAULT_ENTRY_FILE.name})"
        
    # 4. 无输入 -> 显示帮助
    else:
        typer.secho(f"⚠️  提示: 未提供输入，且当前目录下未找到默认文件 '{DEFAULT_ENTRY_FILE.name}'。", fg=typer.colors.YELLOW)
        typer.echo("\n用法示例:")
        typer.echo("  axon my_plan.md       # 指定文件")
        typer.echo("  cat plan.md | axon    # 管道输入")
        typer.echo("  axon < plan.md        # 重定向输入")
        typer.echo("\n更多选项请使用 --help")
        raise typer.Exit(code=0)

    if not content.strip():
        typer.secho("❌ 错误: 输入内容为空。", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    logger.info(f"已加载指令源: {source_desc}")
    logger.info(f"工作区根目录: {work_dir}")
    
    if yolo:
        logger.warning("⚠️  YOLO 模式已开启：将自动确认所有修改。")

    try:
        # 解析
        final_parser_name = parser_name
        if parser_name == "auto":
            final_parser_name = detect_best_parser(content)
            if final_parser_name != "backtick":
                logger.info(f"🔍 自动检测到解析器: {final_parser_name}")

        parser = get_parser(final_parser_name)
        statements = parser.parse(content)
        
        if not statements:
            typer.echo(f"⚠️  使用 '{final_parser_name}' 解析器未找到任何有效的 'act' 操作块。")
            raise typer.Exit()

        # 初始化执行器
        executor = Executor(root_dir=work_dir, yolo=yolo)
        register_basic_acts(executor)
        register_check_acts(executor)
        register_git_acts(executor)
        register_shell_acts(executor)
        register_read_acts(executor)
        register_refactor_acts(executor)
        register_memory_acts(executor)

        # 执行
        executor.execute(statements)
        
        typer.echo("\n✨ 所有操作执行完毕。")

    except Exception as e:
        logger.error(f"运行时错误: {e}")
        typer.secho(f"❌ 错误: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

if __name__ == "__main__":
    typer.run(main)