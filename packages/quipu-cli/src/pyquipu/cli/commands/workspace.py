from pathlib import Path
from typing import Annotated, Optional

import typer
from pyquipu.common.messaging import bus

from ..config import DEFAULT_WORK_DIR
from ..ui_utils import prompt_for_confirmation
from .helpers import engine_context


def register(app: typer.Typer):
    @app.command()
    def save(
        ctx: typer.Context,
        message: Annotated[Optional[str], typer.Argument(help="本次快照的简短描述。")] = None,
        work_dir: Annotated[
            Path,
            typer.Option(
                "--work-dir", "-w", help="操作执行的根目录（工作区）", file_okay=False, dir_okay=True, resolve_path=True
            ),
        ] = DEFAULT_WORK_DIR,
    ):
        with engine_context(work_dir) as engine:
            current_tree_hash = engine.git_db.get_tree_hash()
            is_node_clean = (engine.current_node is not None) and (engine.current_node.output_tree == current_tree_hash)
            EMPTY_TREE_HASH = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
            is_genesis_clean = (not engine.history_graph) and (current_tree_hash == EMPTY_TREE_HASH)

            if is_node_clean or is_genesis_clean:
                bus.success("workspace.save.noChanges")
                ctx.exit(0)

            try:
                node = engine.capture_drift(current_tree_hash, message=message)
                msg_suffix = f" ({message})" if message else ""
                bus.success("workspace.save.success", short_hash=node.short_hash, msg_suffix=msg_suffix)
            except Exception as e:
                bus.error("workspace.save.error", error=str(e))
                ctx.exit(1)

    @app.command()
    def discard(
        ctx: typer.Context,
        work_dir: Annotated[
            Path,
            typer.Option(
                "--work-dir", "-w", help="操作执行的根目录（工作区）", file_okay=False, dir_okay=True, resolve_path=True
            ),
        ] = DEFAULT_WORK_DIR,
        force: Annotated[bool, typer.Option("--force", "-f", help="强制执行，跳过确认提示。")] = False,
    ):
        with engine_context(work_dir) as engine:
            graph = engine.history_graph
            if not graph:
                bus.error("workspace.discard.error.noHistory")
                ctx.exit(1)

            target_tree_hash = engine._read_head()
            latest_node = None
            if target_tree_hash:
                for node in graph.values():
                    if node.output_tree == target_tree_hash:
                        latest_node = node
                        break

            if not latest_node:
                latest_node = max(graph.values(), key=lambda n: n.timestamp)
                target_tree_hash = latest_node.output_tree
                bus.warning("workspace.discard.warning.headMissing", short_hash=latest_node.short_hash)

            current_hash = engine.git_db.get_tree_hash()
            if current_hash == target_tree_hash:
                bus.success("workspace.discard.noChanges", short_hash=latest_node.short_hash)
                ctx.exit(0)

            diff_stat_str = engine.git_db.get_diff_stat(target_tree_hash, current_hash)

            if not force:
                prompt = bus.get("workspace.discard.prompt.confirm", short_hash=latest_node.short_hash)
                if not prompt_for_confirmation(prompt, diff_lines=diff_stat_str.splitlines(), default=False):
                    bus.warning("common.prompt.cancel")
                    raise typer.Abort()

            try:
                engine.visit(target_tree_hash)
                bus.success("workspace.discard.success", short_hash=latest_node.short_hash)
            except Exception as e:
                bus.error("workspace.discard.error.generic", error=str(e))
                ctx.exit(1)
