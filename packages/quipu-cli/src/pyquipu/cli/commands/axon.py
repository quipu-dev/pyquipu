import inspect
import logging
import sys
from pathlib import Path
from typing import Annotated, Optional

import typer
from pyquipu.acts import register_core_acts
from pyquipu.application.plugin_manager import PluginManager
from pyquipu.common.messaging import bus
from pyquipu.interfaces.exceptions import ExecutionError
from pyquipu.runtime.executor import Executor
from pyquipu.runtime.parser import detect_best_parser, get_parser

from ..config import DEFAULT_ENTRY_FILE, DEFAULT_WORK_DIR
from ..logger_config import setup_logging
from ..ui_utils import confirmation_handler_for_executor

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
        setup_logging()
        logger.debug(f"axon started with file={file}, work_dir={work_dir}, parser={parser_name}, yolo={yolo}")

        # 1. 初始化无状态 Executor, 复用 controller 中的标准确认处理器
        # 注意：这里不初始化 Engine，因此没有历史记录功能
        executor = Executor(
            root_dir=work_dir,
            yolo=yolo,
            confirmation_handler=confirmation_handler_for_executor,
        )
        register_core_acts(executor)

        # 3. 加载插件
        # PluginManager 会尝试查找 Git 根目录加载项目级插件，如果找不到 Git 根目录则跳过，符合无状态设计
        PluginManager().load_from_sources(executor, work_dir)

        # 4. 处理 --list-acts
        if list_acts:
            bus.info("axon.listActs.ui.header")
            acts = executor.get_registered_acts()
            for name in sorted(acts.keys()):
                doc = acts[name]
                clean_doc = inspect.cleandoc(doc) if doc else "暂无说明"
                indented_doc = "\n".join(f"   {line}" for line in clean_doc.splitlines())
                bus.info("axon.listActs.ui.actItem", name=name)
                bus.data(f"{indented_doc}\n")
            ctx.exit(0)

        # 5. 获取输入内容 (文件 或 STDIN 或 默认文件)
        content = ""
        source_desc = ""
        if file:
            if not file.exists():
                bus.error("common.error.fileNotFound", path=file)
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
            bus.warning("axon.warning.noInput")
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
                bus.warning("axon.warning.noStatements", parser=final_parser_name)
                ctx.exit(0)

            # 7. 执行
            executor.execute(statements)
            bus.success("axon.success")

        except ExecutionError as e:
            bus.error("axon.error.executionFailed", error=str(e))
            ctx.exit(1)
        except ValueError as e:
            logger.error(f"无效的参数或配置: {e}", exc_info=True)
            bus.error("common.error.invalidConfig", error=str(e))
            ctx.exit(1)
        except Exception as e:
            logger.error(f"未预期的系统错误: {e}", exc_info=True)
            bus.error("common.error.generic", error=str(e))
            ctx.exit(1)
