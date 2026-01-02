import inspect
import logging
import sys
from pathlib import Path
from typing import Annotated, Optional

import typer
from pyquipu.application.controller import run_quipu
from pyquipu.common.messaging import bus
from pyquipu.runtime.executor import Executor

from ..config import DEFAULT_ENTRY_FILE, DEFAULT_WORK_DIR
from ..logger_config import setup_logging
from ..ui_utils import confirmation_handler_for_executor

logger = logging.getLogger(__name__)


def register(app: typer.Typer):
    @app.command(name="run", help="执行 Plan 文件并记录到 Quipu 历史。")
    def run_command(
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
        if list_acts:
            from pyquipu.acts import register_core_acts
            from pyquipu.application.plugin_manager import PluginManager

            executor = Executor(root_dir=work_dir, yolo=True)
            register_core_acts(executor)
            PluginManager().load_from_sources(executor, work_dir)

            bus.info("run.listActs.ui.header")
            acts = executor.get_registered_acts()
            for name in sorted(acts.keys()):
                doc = acts[name]
                clean_doc = inspect.cleandoc(doc) if doc else "暂无说明"
                indented_doc = "\n".join(f"   {line}" for line in clean_doc.splitlines())
                bus.info("run.listActs.ui.actItem", name=name)
                bus.data(f"{indented_doc}\n")
            ctx.exit(0)

        content = ""
        source_desc = ""
        if file:
            if not file.exists():
                bus.error("common.error.fileNotFound", path=file)
                ctx.exit(1)
            if not file.is_file():
                bus.error("common.error.pathNotFile", path=file)
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
        if not content and DEFAULT_ENTRY_FILE.exists():
            content = DEFAULT_ENTRY_FILE.read_text(encoding="utf-8")
            source_desc = f"默认文件 ({DEFAULT_ENTRY_FILE.name})"
        if file and not file.exists() and file.name in ["log", "checkout", "sync", "init", "ui", "find"]:
            bus.error("common.error.fileNotFound", path=file)
            bus.warning("run.error.ambiguousCommand", command=file.name)
            ctx.exit(1)
        if not content.strip():
            if not file:
                bus.warning("run.warning.noInput", filename=DEFAULT_ENTRY_FILE.name)
                bus.info("run.info.usageHint")
                ctx.exit(0)

        logger.info(f"已加载指令源: {source_desc}")
        logger.info(f"工作区根目录: {work_dir}")
        if yolo:
            bus.warning("run.warning.yoloEnabled")
        result = run_quipu(
            content=content,
            work_dir=work_dir,
            parser_name=parser_name,
            yolo=yolo,
            confirmation_handler=confirmation_handler_for_executor,
        )

        if result.message:
            kwargs = result.msg_kwargs or {}
            if result.exit_code == 2:  # OperationCancelledError
                bus.warning(result.message, **kwargs)
            elif not result.success:
                bus.error(result.message, **kwargs)
            else:
                bus.success(result.message, **kwargs)

        if result.data:
            bus.data(result.data)
        ctx.exit(result.exit_code)
