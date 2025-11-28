import subprocess
from pathlib import Path
from typing import Annotated, Optional

import typer
from quipu.common.identity import get_user_id_from_email
from quipu.core.config import ConfigManager
from quipu.core.git_db import GitDB

from ..config import DEFAULT_WORK_DIR
from ..logger_config import setup_logging
from ..utils import find_git_repository_root


def register(app: typer.Typer):
    @app.command()
    def sync(
        ctx: typer.Context,
        work_dir: Annotated[
            Path,
            typer.Option(
                "--work-dir", "-w", help="操作执行的根目录（工作区）", file_okay=False, dir_okay=True, resolve_path=True
            ),
        ] = DEFAULT_WORK_DIR,
        remote_option: Annotated[
            Optional[str], typer.Option("--remote", "-r", help="Git 远程仓库的名称 (覆盖配置文件)。")
        ] = None,
    ):
        """
        与远程仓库同步 Quipu 历史图谱。
        """
        setup_logging()
        sync_dir = find_git_repository_root(work_dir) or work_dir
        config = ConfigManager(sync_dir)
        remote = remote_option or config.get("sync.remote_name", "origin")

        final_user_id = config.get("sync.user_id")
        if not final_user_id:
            typer.secho("🤝 首次使用 sync 功能，正在自动配置用户身份...", fg=typer.colors.BLUE, err=True)
            try:
                result = subprocess.run(
                    ["git", "config", "user.email"], cwd=sync_dir, capture_output=True, text=True, check=True
                )
                email = result.stdout.strip()
                if not email:
                    raise ValueError("Git user.email is empty.")

                final_user_id = get_user_id_from_email(email)
                config.set("sync.user_id", final_user_id)
                config.save()
                typer.secho(
                    f"✅ 已根据你的 Git 邮箱 '{email}' 生成并保存用户 ID: {final_user_id}",
                    fg=typer.colors.GREEN,
                    err=True,
                )

            except (subprocess.CalledProcessError, ValueError, FileNotFoundError):
                typer.secho("❌ 错误：无法获取你的 Git 用户邮箱。", fg=typer.colors.RED, err=True)
                typer.secho("💡 请先运行以下命令进行设置:", fg=typer.colors.YELLOW, err=True)
                typer.echo('  git config --global user.email "you@example.com"')
                ctx.exit(1)

        try:
            git_db = GitDB(sync_dir)

            # --- Stage 1: Fetch ---
            subscriptions = config.get("sync.subscriptions", [])
            target_ids_to_fetch = set(subscriptions)
            target_ids_to_fetch.add(final_user_id)

            if target_ids_to_fetch:
                typer.secho(
                    f"⬇️  正在从 '{remote}' 拉取 {len(target_ids_to_fetch)} 个用户的历史...",
                    fg=typer.colors.BLUE,
                    err=True,
                )
                for target_id in sorted(list(target_ids_to_fetch)):
                    git_db.fetch_quipu_refs(remote, target_id)

            # --- Stage 2: Reconcile ---
            typer.secho(f"🤝 正在将远程历史与本地进行调和...", fg=typer.colors.BLUE, err=True)
            git_db.reconcile_local_with_remote(remote, final_user_id)

            # --- Stage 3: Push ---
            typer.secho(f"⬆️  正在向 '{remote}' 推送合并后的本地历史...", fg=typer.colors.BLUE, err=True)
            git_db.push_quipu_refs(remote, final_user_id)

            typer.secho("\n✅ Quipu 双向同步完成。", fg=typer.colors.GREEN, err=True)
            typer.secho(
                "\n💡 提示: 运行 `quipu cache sync` 来更新本地数据库和 UI 视图。", fg=typer.colors.YELLOW, err=True
            )

        except RuntimeError as e:
            typer.secho(f"\n❌ 同步操作失败: {e}", fg=typer.colors.RED, err=True)
            ctx.exit(1)
