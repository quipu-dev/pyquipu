import logging
from pathlib import Path
from typing import Annotated

import typer

from .helpers import engine_context, _prompt_for_confirmation
from ..config import DEFAULT_WORK_DIR
from ..logger_config import setup_logging

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
    typer.secho("💧 正在执行增量数据补水...", fg=typer.colors.BLUE, err=True)
    try:
        with engine_context(work_dir):
            pass
        typer.secho("✅ 数据同步完成。", fg=typer.colors.GREEN, err=True)
    except Exception as e:
        typer.secho(f"❌ 数据同步失败: {e}", fg=typer.colors.RED, err=True)
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
        typer.secho("🤷 数据库文件不存在，将直接创建。无需重建。", fg=typer.colors.YELLOW, err=True)
        cache_sync(ctx, work_dir)
        return

    if not force:
        prompt = f"🚨 即将删除并重建数据库 {db_path}。\n此操作不可逆。是否继续？"
        if not _prompt_for_confirmation(prompt, default=False):
            typer.secho("\n🚫 操作已取消。", fg=typer.colors.YELLOW, err=True)
            raise typer.Abort()

    try:
        db_path.unlink()
        typer.secho("🗑️  旧数据库已删除。", err=True)
    except Exception as e:
        typer.secho(f"❌ 删除旧数据库失败: {e}", fg=typer.colors.RED, err=True)
        ctx.exit(1)

    cache_sync(ctx, work_dir)
