import inspect
import logging
import sys
from pathlib import Path
from typing import Annotated, List, Optional

import typer
import click
from quipu.acts import register_core_acts
from quipu.interfaces.exceptions import ExecutionError
from quipu.runtime.executor import Executor
from quipu.runtime.parser import detect_best_parser, get_parser

from ..config import DEFAULT_ENTRY_FILE, DEFAULT_WORK_DIR
from ..logger_config import setup_logging
from ..plugin_manager import PluginManager

logger = logging.getLogger(__name__)


def register(app: typer.Typer):
    @app.command(name="axon")
    def axon_command(
        ctx: typer.Context,
        file: Annotated[
            Optional[Path], typer.Argument(help="包含 Markdown 指令的文件路径。", resolve_path=True)
        ] = None,
        work_dir: Annotated[
            Path,
            typer.Option(
                "--work-dir", "-w", help="操作执行的根目录（工作区）", file_okay=False, dir_okay=True, resolve_path=True
            ),
        ] = DEFAULT_WORK_DIR,
        parser_name: Annotated[str, typer.Option("--parser", "-p", help="选择解析器语法。默认为 'auto'。")] = "auto",
        yolo: Annotated[
            bool, typer.Option("--yolo", "-y", help="跳过所有确认步骤，直接执行 (You Only Look Once)。")
        ] = False,
        list_acts: Annotated[bool, typer.Option("--list-acts", "-l", help="列出所有可用的操作指令及其说明。")] = False,
    ):
        """
        Axon: 无状态的 Markdown 任务执行器 (不记录历史)。
        """
        setup_logging()

        # 1. 配置执行器的 UI 确认回调
        def typer_confirmation_handler(diff_lines: List[str], prompt: str) -> bool:
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
            typer.echo("", err=True)

            typer.secho(f"{prompt} [Y/n]: ", nl=False, err=True)
            try:
                char = click.getchar(echo=False)
                click.echo(char, err=True)
                return char.lower() != "n"
            except (OSError, EOFError):
                click.echo(" (non-interactive)", err=True)
                logger.warning("无法在当前环境中获取用户确认，操作已跳过。")
                return False

        # 2. 初始化无状态 Executor
        # 注意：这里不初始化 Engine，因此没有历史记录功能
        executor = Executor(
            root_dir=work_dir,
            yolo=yolo,
            confirmation_handler=typer_confirmation_handler,
        )
        register_core_acts(executor)

        # 3. 加载插件
        # PluginManager 会尝试查找 Git 根目录加载项目级插件，如果找不到 Git 根目录则跳过，符合无状态设计
        PluginManager().load_from_sources(executor, work_dir)

        # 4. 处理 --list-acts
        if list_acts:
            typer.secho("\n📋 可用的 Axon 指令列表:\n", fg=typer.colors.GREEN, bold=True, err=True)
            acts = executor.get_registered_acts()
            for name in sorted(acts.keys()):
                doc = acts[name]
                clean_doc = inspect.cleandoc(doc) if doc else "暂无说明"
                indented_doc = "\n".join(f"   {line}" for line in clean_doc.splitlines())
                typer.secho(f"🔹 {name}", fg=typer.colors.CYAN, bold=True)
                typer.echo(f"{indented_doc}\n")
            ctx.exit(0)

        # 5. 获取输入内容 (文件 或 STDIN 或 默认文件)
        content = ""
        source_desc = ""
        if file:
            if not file.exists():
                typer.secho(f"❌ 错误: 找不到指令文件: {file}", fg=typer.colors.RED, err=True)
                ctx.exit(1)
            content = file.read_text(encoding="utf-8")
            source_desc = f"文件 ({file.name})"
        elif not sys.stdin.isatty():
            try:
                stdin_content = sys.stdin.read()
                if stdin_content:
                    content = stdin_content
                    source_desc = "STDIN (管道流)"
            except Exception:
                pass

        # 如果没有指定文件且没有 STDIN，尝试读取当前目录下的默认入口文件 (如 o.md)
        if not content and not file and DEFAULT_ENTRY_FILE.exists():
            content = DEFAULT_ENTRY_FILE.read_text(encoding="utf-8")
            source_desc = f"默认文件 ({DEFAULT_ENTRY_FILE.name})"

        if not content.strip():
            typer.secho("⚠️  提示: 未提供输入 (文件或管道)，且未找到默认文件。", fg=typer.colors.YELLOW, err=True)
            ctx.exit(0)

        logger.info(f"Axon 启动 | 源: {source_desc} | 工作区: {work_dir}")

        # 6. 解析
        final_parser_name = parser_name
        if parser_name == "auto":
            final_parser_name = detect_best_parser(content)

        try:
            parser = get_parser(final_parser_name)
            statements = parser.parse(content)

            if not statements:
                typer.secho(
                    f"⚠️  未解析到任何有效指令 (Parser: {final_parser_name})。", fg=typer.colors.YELLOW, err=True
                )
                ctx.exit(0)

            # 7. 执行
            executor.execute(statements)
            typer.secho("\n✨ Axon 执行完成。", fg=typer.colors.GREEN, err=True)

        except ExecutionError as e:
            typer.secho(f"\n❌ 执行失败: {e}", fg=typer.colors.RED, err=True)
            ctx.exit(1)
        except Exception as e:
            logger.error(f"系统错误: {e}", exc_info=True)
            typer.secho(f"\n❌ 系统错误: {e}", fg=typer.colors.RED, err=True)
            ctx.exit(1)
