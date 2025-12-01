import logging
from pathlib import Path
from typing import Annotated

import typer
from pyquipu.application.factory import create_engine
from pyquipu.common.messaging import bus

from ..config import DEFAULT_WORK_DIR, LOG_LEVEL
from ..logger_config import configure_file_logging, setup_logging
from .helpers import _execute_visit, engine_context

logger = logging.getLogger(__name__)


def register(app: typer.Typer):
    @app.command()
    def ui(
        ctx: typer.Context,
        work_dir: Annotated[
            Path,
            typer.Option(
                "--work-dir", "-w", help="操作执行的根目录（工作区）", file_okay=False, dir_okay=True, resolve_path=True
            ),
        ] = DEFAULT_WORK_DIR,
        raw: Annotated[bool, typer.Option("--raw", help="默认以纯文本模式启动，禁用 Markdown 渲染。")] = False,
    ):
        """
        以交互式 TUI 模式显示 Quipu 历史图谱。
        """
        try:
            from ..tui import QuipuUiApp
        except ImportError:
            bus.error("ui.error.depMissing")
            bus.info("ui.info.depHint")
            ctx.exit(1)

        if LOG_LEVEL == "DEBUG":
            log_file = work_dir / ".quipu" / "tui.debug.log"
            configure_file_logging(log_file)
        else:
            setup_logging()  # Use standard stderr logging for INFO level and above

        logging.info("Starting Quipu UI command...")

        temp_engine = create_engine(work_dir, lazy=True)
        try:
            count = temp_engine.reader.get_node_count()
            if count == 0:
                bus.info("ui.info.emptyHistory")
                ctx.exit(0)
        finally:
            temp_engine.close()

        app_instance = QuipuUiApp(work_dir=work_dir, initial_raw_mode=raw)
        result = app_instance.run()

        if result:
            action, data = result
            if action == "checkout":
                target_hash = data
                with engine_context(work_dir) as action_engine:
                    bus.info("ui.info.checkoutRequest", short_hash=target_hash[:7])
                    _execute_visit(
                        ctx, action_engine, target_hash, "navigation.info.navigating", short_hash=target_hash[:7]
                    )

            elif action == "dump":
                print(data)
                ctx.exit(0)
