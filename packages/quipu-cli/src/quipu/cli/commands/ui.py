import logging
from pathlib import Path
from typing import Annotated

import typer

from .helpers import engine_context, _execute_visit
from ..config import DEFAULT_WORK_DIR
from ..factory import create_engine
from ..logger_config import configure_file_logging

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
            typer.secho("❌ TUI 依赖 'textual' 未安装。", fg=typer.colors.RED, err=True)
            typer.secho("💡 请运行: pip install 'textual>=0.58.0'", err=True)
            ctx.exit(1)

        log_file = work_dir / ".quipu" / "tui.debug.log"
        configure_file_logging(log_file)
        logging.info("Starting Quipu UI command...")

        temp_engine = create_engine(work_dir, lazy=True)
        try:
            count = temp_engine.reader.get_node_count()
            if count == 0:
                typer.secho("📜 历史记录为空，无需启动 UI。", fg=typer.colors.YELLOW, err=True)
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
                    typer.secho(f"\n> TUI 请求检出到: {target_hash[:7]}", err=True)
                    _execute_visit(ctx, action_engine, target_hash, f"正在导航到 TUI 选定节点: {target_hash[:7]}")

            elif action == "dump":
                print(data)
                ctx.exit(0)
