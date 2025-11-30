import logging
from pathlib import Path
from typing import Annotated

import typer

from .helpers import engine_context
from ..config import DEFAULT_WORK_DIR
from ..logger_config import setup_logging
from ..ui_utils import prompt_for_confirmation
from pyquipu.common.messaging import bus

logger = logging.getLogger(__name__)

cache_app = typer.Typer(name="cache", help="管理本地 SQLite 缓存。")


@cache_app.command("sync")
def cache_sync(
    ctx: typer.Context,
    work_dir: Annotated[
        Path,
        typer.Option(
            "--work-dir", "-w", help="操作执行的根目录（工作区）", file_okay=False, dir_okay=True, resolve_path=True
        ),
    ] = DEFAULT_WORK_DIR,
):
    """
    将 Git 历史增量同步到 SQLite 缓存。
    """
    bus.info("cache.sync.info.hydrating")
    try:
        with engine_context(work_dir):
            pass
        bus.success("cache.sync.success")
    except Exception as e:
        logger.error("数据同步失败", exc_info=True)
        bus.error("cache.sync.error", error=str(e))
        ctx.exit(1)


@cache_app.command("rebuild")
def cache_rebuild(
    ctx: typer.Context,
    force: Annotated[bool, typer.Option("--force", "-f", help="强制执行，跳过确认提示。")] = False,
    work_dir: Annotated[
        Path,
        typer.Option(
            "--work-dir", "-w", help="操作执行的根目录（工作区）", file_okay=False, dir_okay=True, resolve_path=True
        ),
    ] = DEFAULT_WORK_DIR,
):
    """
    强制全量重建 SQLite 缓存。
    """
    setup_logging()
    db_path = work_dir.resolve() / ".quipu" / "history.sqlite"
    if not db_path.exists():
        bus.warning("cache.rebuild.info.dbNotFound")
        cache_sync(ctx, work_dir)
        return

    if not force:
        prompt = f"🚨 即将删除并重建数据库 {db_path}。\n此操作不可逆。是否继续？"
        if not prompt_for_confirmation(prompt, default=False):
            bus.warning("common.prompt.cancel")
            raise typer.Abort()

    try:
        db_path.unlink()
        bus.info("cache.rebuild.info.deleting")
    except (OSError, PermissionError) as e:
        logger.error(f"删除旧数据库文件 '{db_path}' 失败", exc_info=True)
        bus.error("cache.rebuild.error.deleteFailed", error=str(e))
        ctx.exit(1)

    cache_sync(ctx, work_dir)
