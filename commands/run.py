import typer
from pathlib import Path
from typing import Annotated
import logging

from core.parser import MarkdownParser
from core.executor import Executor
from acts.basic import register_basic_acts
from config import DEFAULT_WORK_DIR

app = typer.Typer()
logger = logging.getLogger(__name__)

@app.command()
def execute(
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
    ],
    work_dir: Annotated[
        Path, 
        typer.Option(
            "--work-dir", "-w",
            help="操作执行的根目录（工作区）",
            file_okay=False,
            dir_okay=True,
            resolve_path=True
        )
    ] = DEFAULT_WORK_DIR
):
    """
    读取 Markdown 文件并执行其中定义的 'act' 操作。
    """
    logger.info(f"正在加载指令文件: {file}")
    logger.info(f"工作区根目录: {work_dir}")

    try:
        # 1. 读取内容
        content = file.read_text(encoding="utf-8")

        # 2. 解析
        parser = MarkdownParser()
        statements = parser.parse(content)
        
        if not statements:
            typer.echo("⚠️  未在文件中找到任何有效的 'act' 操作块。")
            raise typer.Exit()

        # 3. 初始化执行器并注册能力
        executor = Executor(root_dir=work_dir)
        register_basic_acts(executor)

        # 4. 执行
        executor.execute(statements)
        
        typer.echo("\n✨ 所有操作执行完毕。")

    except Exception as e:
        logger.error(f"运行时错误: {e}")
        typer.secho(f"❌ 错误: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)
