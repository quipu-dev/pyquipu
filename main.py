import typer
import logging
from pathlib import Path
from typing import Annotated

from logger_config import setup_logging
from core.parser import get_parser, list_parsers
from core.executor import Executor
from acts.basic import register_basic_acts
from acts.check import register_check_acts
from config import DEFAULT_WORK_DIR

# 初始化日志
setup_logging()
logger = logging.getLogger(__name__)

def main(
    file: Annotated[
        Path, 
        typer.Argument(
            help="包含 Markdown 指令的文件路径",
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
            resolve_path=True
        )
    ] = Path("o.md"),
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
            help=f"选择解析器语法。可用: {list_parsers()}",
        )
    ] = "backtick",
    yolo: Annotated[
        bool,
        typer.Option(
            "--yolo", "-y",
            help="跳过所有确认步骤，直接执行 (You Only Look Once)。",
        )
    ] = False
):
    """
    Axon: 执行 Markdown 文件中的操作指令。
    """
    logger.info(f"正在加载指令文件: {file}")
    logger.info(f"工作区根目录: {work_dir}")
    logger.info(f"使用解析器: {parser_name}")
    if yolo:
        logger.warning("⚠️  YOLO 模式已开启：将自动确认所有修改。")

    try:
        # 1. 读取内容
        content = file.read_text(encoding="utf-8")

        # 2. 获取解析器并解析
        parser = get_parser(parser_name)
        statements = parser.parse(content)
        
        if not statements:
            typer.echo(f"⚠️  使用 '{parser_name}' 解析器未找到任何有效的 'act' 操作块。")
            typer.echo(f"提示: 如果文件中使用了不同的分隔符（如 ~~~），请尝试使用 --parser tilde")
            raise typer.Exit()

        # 3. 初始化执行器并注册能力
        executor = Executor(root_dir=work_dir, yolo=yolo)
        register_basic_acts(executor)
        register_check_acts(executor)

        # 4. 执行
        executor.execute(statements)
        
        typer.echo("\n✨ 所有操作执行完毕。")

    except Exception as e:
        logger.error(f"运行时错误: {e}")
        typer.secho(f"❌ 错误: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

if __name__ == "__main__":
    # 使用 typer.run 直接运行函数，无需子命令
    typer.run(main)
