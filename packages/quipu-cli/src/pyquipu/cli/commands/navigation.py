import logging
from pathlib import Path
from typing import Annotated

import typer
from pyquipu.common.messaging import bus

from ..config import DEFAULT_WORK_DIR
from ..ui_utils import prompt_for_confirmation
from .helpers import _execute_visit, _find_current_node, engine_context

logger = logging.getLogger(__name__)


def register(app: typer.Typer):
    @app.command()
    def checkout(
        ctx: typer.Context,
        hash_prefix: Annotated[str, typer.Argument(help="目标状态节点 output_tree 的哈希前缀。")],
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

            matches = [node for node in graph.values() if node.output_tree.startswith(hash_prefix)]
            if not matches:
                bus.error("navigation.checkout.error.notFound", hash_prefix=hash_prefix)
                ctx.exit(1)
            if len(matches) > 1:
                bus.error("navigation.checkout.error.notUnique", hash_prefix=hash_prefix, count=len(matches))
                ctx.exit(1)
            target_node = matches[0]
            target_output_tree_hash = target_node.output_tree

            current_hash = engine.git_db.get_tree_hash()
            if current_hash == target_output_tree_hash:
                bus.success("navigation.checkout.info.noAction", short_hash=target_node.short_hash)
                ctx.exit(0)

            is_dirty = engine.current_node is None or engine.current_node.output_tree != current_hash
            if is_dirty:
                bus.warning("navigation.checkout.info.capturingDrift")
                engine.capture_drift(current_hash)
                bus.success("navigation.checkout.success.driftCaptured")
                current_hash = engine.git_db.get_tree_hash()

            diff_stat_str = engine.git_db.get_diff_stat(current_hash, target_output_tree_hash)

            if not force:
                prompt = bus.get(
                    "navigation.checkout.prompt.confirm",
                    short_hash=target_node.short_hash,
                    timestamp=target_node.timestamp,
                )
                if not prompt_for_confirmation(prompt, diff_lines=diff_stat_str.splitlines(), default=False):
                    bus.warning("common.prompt.cancel")
                    raise typer.Abort()

            _execute_visit(
                ctx,
                engine,
                target_output_tree_hash,
                "navigation.info.navigating",
                short_hash=target_node.short_hash,
            )

    @app.command()
    def undo(
        ctx: typer.Context,
        count: Annotated[int, typer.Option("--count", "-n", help="向上移动的步数。")] = 1,
        work_dir: Annotated[Path, typer.Option("--work-dir", "-w", help="工作区根目录。")] = DEFAULT_WORK_DIR,
    ):
        with engine_context(work_dir) as engine:
            graph = engine.history_graph
            current_node = _find_current_node(engine, graph)
            if not current_node:
                ctx.exit(1)
            target_node = current_node
            for i in range(count):
                if not target_node.parent:
                    if i > 0:
                        bus.success("navigation.undo.reachedRoot", steps=i)
                    else:
                        bus.success("navigation.undo.atRoot")
                    if target_node == current_node:
                        ctx.exit(0)
                    break
                target_node = target_node.parent

            _execute_visit(
                ctx,
                engine,
                target_node.output_tree,
                "navigation.info.navigating",
                short_hash=target_node.short_hash,
            )

    @app.command()
    def redo(
        ctx: typer.Context,
        count: Annotated[int, typer.Option("--count", "-n", help="向下移动的步数。")] = 1,
        work_dir: Annotated[Path, typer.Option("--work-dir", "-w", help="工作区根目录。")] = DEFAULT_WORK_DIR,
    ):
        with engine_context(work_dir) as engine:
            graph = engine.history_graph
            current_node = _find_current_node(engine, graph)
            if not current_node:
                ctx.exit(1)
            target_node = current_node
            for i in range(count):
                if not target_node.children:
                    if i > 0:
                        bus.success("navigation.redo.reachedEnd", steps=i)
                    else:
                        bus.success("navigation.redo.atEnd")
                    if target_node == current_node:
                        ctx.exit(0)
                    break
                target_node = target_node.children[-1]
                if len(current_node.children) > 1:
                    bus.info("navigation.redo.info.multiBranch", short_hash=target_node.short_hash)

            _execute_visit(
                ctx,
                engine,
                target_node.output_tree,
                "navigation.info.navigating",
                short_hash=target_node.short_hash,
            )

    @app.command()
    def prev(
        ctx: typer.Context,
        work_dir: Annotated[Path, typer.Option("--work-dir", "-w", help="工作区根目录。")] = DEFAULT_WORK_DIR,
    ):
        with engine_context(work_dir) as engine:
            graph = engine.history_graph
            current_node = _find_current_node(engine, graph)
            if not current_node:
                ctx.exit(1)
            siblings = current_node.siblings
            if len(siblings) <= 1:
                bus.success("navigation.prev.noSiblings")
                ctx.exit(0)
            try:
                idx = siblings.index(current_node)
                if idx == 0:
                    bus.success("navigation.prev.atOldest")
                    ctx.exit(0)
                target_node = siblings[idx - 1]
                _execute_visit(
                    ctx,
                    engine,
                    target_node.output_tree,
                    "navigation.info.navigating",
                    short_hash=target_node.short_hash,
                )
            except ValueError:
                pass

    @app.command()
    def next(
        ctx: typer.Context,
        work_dir: Annotated[Path, typer.Option("--work-dir", "-w", help="工作区根目录。")] = DEFAULT_WORK_DIR,
    ):
        with engine_context(work_dir) as engine:
            graph = engine.history_graph
            current_node = _find_current_node(engine, graph)
            if not current_node:
                ctx.exit(1)
            siblings = current_node.siblings
            if len(siblings) <= 1:
                bus.success("navigation.next.noSiblings")
                ctx.exit(0)
            try:
                idx = siblings.index(current_node)
                if idx == len(siblings) - 1:
                    bus.success("navigation.next.atNewest")
                    ctx.exit(0)
                target_node = siblings[idx + 1]
                _execute_visit(
                    ctx,
                    engine,
                    target_node.output_tree,
                    "navigation.info.navigating",
                    short_hash=target_node.short_hash,
                )
            except ValueError:
                pass

    @app.command()
    def back(
        ctx: typer.Context,
        work_dir: Annotated[Path, typer.Option("--work-dir", "-w", help="工作区根目录。")] = DEFAULT_WORK_DIR,
    ):
        with engine_context(work_dir) as engine:
            try:
                result_hash = engine.back()
                if result_hash:
                    bus.success("navigation.back.success", short_hash=result_hash[:7])
                else:
                    bus.warning("navigation.back.atStart")
            except Exception as e:
                logger.error("后退操作失败", exc_info=True)
                bus.error("navigation.back.error", error=str(e))
                ctx.exit(1)

    @app.command()
    def forward(
        ctx: typer.Context,
        work_dir: Annotated[Path, typer.Option("--work-dir", "-w", help="工作区根目录。")] = DEFAULT_WORK_DIR,
    ):
        with engine_context(work_dir) as engine:
            try:
                result_hash = engine.forward()
                if result_hash:
                    bus.success("navigation.forward.success", short_hash=result_hash[:7])
                else:
                    bus.warning("navigation.forward.atEnd")
            except Exception as e:
                logger.error("前进操作失败", exc_info=True)
                bus.error("navigation.forward.error", error=str(e))
                ctx.exit(1)
