import subprocess
from enum import Enum
from pathlib import Path
from typing import Annotated, Optional

import typer
from pyquipu.common.identity import get_user_id_from_email
from pyquipu.common.messaging import bus
from pyquipu.application.utils import find_git_repository_root
from pyquipu.engine.config import ConfigManager
from pyquipu.engine.git_db import GitDB

from ..config import DEFAULT_WORK_DIR
from ..logger_config import setup_logging


class SyncMode(str, Enum):
    BIDIRECTIONAL = "bidirectional"
    PUSH_FORCE = "push-force"
    PUSH_ONLY = "push-only"
    PULL_PRUNE = "pull-prune"
    PULL_ONLY = "pull-only"


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
        mode: Annotated[
            SyncMode,
            typer.Option(
                "--mode",
                "-m",
                help="同步模式: 'bidirectional' (默认), 'push-force', 'push-only', 'pull-prune', 'pull-only'",
                case_sensitive=False,
            ),
        ] = SyncMode.BIDIRECTIONAL,
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
            bus.info("sync.setup.firstUse")
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
                bus.success("sync.setup.success", email=email, user_id=final_user_id)

            except (subprocess.CalledProcessError, ValueError, FileNotFoundError):
                bus.error("sync.setup.error.noEmail")
                bus.warning("sync.setup.info.emailHint")
                ctx.exit(1)

        try:
            git_db = GitDB(sync_dir)
            subscriptions = config.get("sync.subscriptions", [])
            target_ids_to_fetch = set(subscriptions)
            target_ids_to_fetch.add(final_user_id)

            bus.info("sync.run.info.mode", mode=mode.value)

            # --- Operation Dispatch based on Mode ---
            match mode:
                case SyncMode.BIDIRECTIONAL:
                    bus.info("sync.run.info.pulling")
                    for target_id in sorted(list(target_ids_to_fetch)):
                        git_db.fetch_quipu_refs(remote, target_id)
                    bus.info("sync.run.info.reconciling")
                    git_db.reconcile_local_with_remote(remote, final_user_id)
                    bus.info("sync.run.info.pushing")
                    git_db.push_quipu_refs(remote, final_user_id)
                    bus.success("sync.run.success.bidirectional")

                case SyncMode.PULL_ONLY:
                    bus.info("sync.run.info.pulling")
                    for target_id in sorted(list(target_ids_to_fetch)):
                        git_db.fetch_quipu_refs(remote, target_id)
                    bus.info("sync.run.info.reconciling")
                    git_db.reconcile_local_with_remote(remote, final_user_id)
                    bus.success("sync.run.success.pullOnly")

                case SyncMode.PULL_PRUNE:
                    bus.info("sync.run.info.pullingPrune")
                    for target_id in sorted(list(target_ids_to_fetch)):
                        git_db.fetch_quipu_refs(remote, target_id)
                    bus.info("sync.run.info.reconciling")
                    git_db.reconcile_local_with_remote(remote, final_user_id)
                    bus.info("sync.run.info.pruning")
                    git_db.prune_local_from_remote(remote, final_user_id)
                    bus.success("sync.run.success.pullPrune")

                case SyncMode.PUSH_ONLY:
                    bus.info("sync.run.info.pushing")
                    git_db.push_quipu_refs(remote, final_user_id, force=False)
                    bus.success("sync.run.success.pushOnly")

                case SyncMode.PUSH_FORCE:
                    bus.info("sync.run.info.pushingForce")
                    git_db.push_quipu_refs(remote, final_user_id, force=True)
                    bus.success("sync.run.success.pushForce")

            bus.info("sync.run.info.cacheHint")

        except RuntimeError as e:
            bus.error("sync.run.error.generic", error=str(e))
            ctx.exit(1)
