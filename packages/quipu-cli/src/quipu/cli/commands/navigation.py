from pathlib import Path
from typing import Annotated

import typer

from .helpers import engine_context, _find_current_node, _execute_visit
from ..config import DEFAULT_WORK_DIR
from ..ui_utils import prompt_for_confirmation


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
        """
        将工作区恢复到指定的历史节点状态。
        """
        with engine_context(work_dir) as engine:
            graph = engine.history_graph

            matches = [node for output_tree, node in graph.items() if output_tree.startswith(hash_prefix)]
            if not matches:
                typer.secho(
                    f"❌ 错误: 未找到 output_tree 哈希前缀为 '{hash_prefix}' 的历史节点。",
                    fg=typer.colors.RED,
                    err=True,
                )
                ctx.exit(1)
            if len(matches) > 1:
                typer.secho(
                    f"❌ 错误: 哈希前缀 '{hash_prefix}' 不唯一，匹配到 {len(matches)} 个节点。",
                    fg=typer.colors.RED,
                    err=True,
                )
                ctx.exit(1)
            target_node = matches[0]
            target_output_tree_hash = target_node.output_tree

            current_hash = engine.git_db.get_tree_hash()
            if current_hash == target_output_tree_hash:
                typer.secho(
                    f"✅ 工作区已处于目标状态 ({target_node.short_hash})，无需操作。", fg=typer.colors.GREEN, err=True
                )
                ctx.exit(0)

            is_dirty = engine.current_node is None or engine.current_node.output_tree != current_hash
            if is_dirty:
                typer.secho(
                    "⚠️  检测到当前工作区存在未记录的变更，将自动创建捕获节点...", fg=typer.colors.YELLOW, err=True
                )
                engine.capture_drift(current_hash)
                typer.secho("✅ 变更已捕获。", fg=typer.colors.GREEN, err=True)
                current_hash = engine.git_db.get_tree_hash()

            diff_stat = engine.git_db.get_diff_stat(current_hash, target_output_tree_hash)
            if diff_stat:
                typer.secho("\n以下是将要发生的变更:", fg=typer.colors.YELLOW, err=True)
                typer.secho("-" * 20, err=True)
                typer.echo(diff_stat, err=True)
                typer.secho("-" * 20, err=True)

            if not force:
                prompt = f"🚨 即将重置工作区到状态 {target_node.short_hash} ({target_node.timestamp})。\n此操作会覆盖未提交的更改。是否继续？"
                if not prompt_for_confirmation(prompt, default=False):
                    typer.secho("\n🚫 操作已取消。", fg=typer.colors.YELLOW, err=True)
                    raise typer.Abort()

            _execute_visit(ctx, engine, target_output_tree_hash, f"正在导航到节点: {target_node.short_hash}")

    @app.command()
    def undo(
        ctx: typer.Context,
        count: Annotated[int, typer.Option("--count", "-n", help="向上移动的步数。")] = 1,
        work_dir: Annotated[Path, typer.Option("--work-dir", "-w", help="工作区根目录。")] = DEFAULT_WORK_DIR,
    ):
        """
        [结构化导航] 向上移动到当前状态的父节点。
        """
        with engine_context(work_dir) as engine:
            graph = engine.history_graph
            current_node = _find_current_node(engine, graph)
            if not current_node:
                ctx.exit(1)
            target_node = current_node
            for i in range(count):
                if not target_node.parent:
                    msg = f"已到达历史根节点 (移动了 {i} 步)。" if i > 0 else "已在历史根节点。"
                    typer.secho(f"✅ {msg}", fg=typer.colors.GREEN, err=True)
                    if target_node == current_node:
                        ctx.exit(0)
                    break
                target_node = target_node.parent

            _execute_visit(ctx, engine, target_node.output_tree, f"正在撤销到父节点: {target_node.short_hash}")

    @app.command()
    def redo(
        ctx: typer.Context,
        count: Annotated[int, typer.Option("--count", "-n", help="向下移动的步数。")] = 1,
        work_dir: Annotated[Path, typer.Option("--work-dir", "-w", help="工作区根目录。")] = DEFAULT_WORK_DIR,
    ):
        """
        [结构化导航] 向下移动到子节点 (默认最新)。
        """
        with engine_context(work_dir) as engine:
            graph = engine.history_graph
            current_node = _find_current_node(engine, graph)
            if not current_node:
                ctx.exit(1)
            target_node = current_node
            for i in range(count):
                if not target_node.children:
                    msg = f"已到达分支末端 (移动了 {i} 步)。" if i > 0 else "已在分支末端。"
                    typer.secho(f"✅ {msg}", fg=typer.colors.GREEN, err=True)
                    if target_node == current_node:
                        ctx.exit(0)
                    break
                target_node = target_node.children[-1]
                if len(current_node.children) > 1:
                    typer.secho(
                        f"💡 当前节点有多个分支，已自动选择最新分支 -> {target_node.short_hash}",
                        fg=typer.colors.YELLOW,
                        err=True,
                    )

            _execute_visit(ctx, engine, target_node.output_tree, f"正在重做到子节点: {target_node.short_hash}")

    @app.command()
    def prev(
        ctx: typer.Context,
        work_dir: Annotated[Path, typer.Option("--work-dir", "-w", help="工作区根目录。")] = DEFAULT_WORK_DIR,
    ):
        """
        [结构化导航] 切换到上一个兄弟分支。
        """
        with engine_context(work_dir) as engine:
            graph = engine.history_graph
            current_node = _find_current_node(engine, graph)
            if not current_node:
                ctx.exit(1)
            siblings = current_node.siblings
            if len(siblings) <= 1:
                typer.secho("✅ 当前节点没有兄弟分支。", fg=typer.colors.GREEN, err=True)
                ctx.exit(0)
            try:
                idx = siblings.index(current_node)
                if idx == 0:
                    typer.secho("✅ 已在最旧的兄弟分支。", fg=typer.colors.GREEN, err=True)
                    ctx.exit(0)
                target_node = siblings[idx - 1]
                _execute_visit(
                    ctx, engine, target_node.output_tree, f"正在切换到上一个兄弟节点: {target_node.short_hash}"
                )
            except ValueError:
                pass

    @app.command()
    def next(
        ctx: typer.Context,
        work_dir: Annotated[Path, typer.Option("--work-dir", "-w", help="工作区根目录。")] = DEFAULT_WORK_DIR,
    ):
        """
        [结构化导航] 切换到下一个兄弟分支。
        """
        with engine_context(work_dir) as engine:
            graph = engine.history_graph
            current_node = _find_current_node(engine, graph)
            if not current_node:
                ctx.exit(1)
            siblings = current_node.siblings
            if len(siblings) <= 1:
                typer.secho("✅ 当前节点没有兄弟分支。", fg=typer.colors.GREEN, err=True)
                ctx.exit(0)
            try:
                idx = siblings.index(current_node)
                if idx == len(siblings) - 1:
                    typer.secho("✅ 已在最新的兄弟分支。", fg=typer.colors.GREEN, err=True)
                    ctx.exit(0)
                target_node = siblings[idx + 1]
                _execute_visit(
                    ctx, engine, target_node.output_tree, f"正在切换到下一个兄弟节点: {target_node.short_hash}"
                )
            except ValueError:
                pass

    @app.command()
    def back(
        ctx: typer.Context,
        work_dir: Annotated[Path, typer.Option("--work-dir", "-w", help="工作区根目录。")] = DEFAULT_WORK_DIR,
    ):
        """
        [时序性导航] 后退：回到上一次访问的历史状态。
        """
        with engine_context(work_dir) as engine:
            try:
                result_hash = engine.back()
                if result_hash:
                    typer.secho(f"✅ 已后退到状态: {result_hash[:7]}", fg=typer.colors.GREEN, err=True)
                else:
                    typer.secho("⚠️  已到达访问历史的起点。", fg=typer.colors.YELLOW, err=True)
            except Exception as e:
                logger.error("后退操作失败", exc_info=True)
                typer.secho(f"❌ 后退操作失败: {e}", fg=typer.colors.RED, err=True)
                ctx.exit(1)

    @app.command()
    def forward(
        ctx: typer.Context,
        work_dir: Annotated[Path, typer.Option("--work-dir", "-w", help="工作区根目录。")] = DEFAULT_WORK_DIR,
    ):
        """
        [时序性导航] 前进：撤销后退操作。
        """
        with engine_context(work_dir) as engine:
            try:
                result_hash = engine.forward()
                if result_hash:
                    typer.secho(f"✅ 已前进到状态: {result_hash[:7]}", fg=typer.colors.GREEN, err=True)
                else:
                    typer.secho("⚠️  已到达访问历史的终点。", fg=typer.colors.YELLOW, err=True)
            except Exception as e:
                logger.error("前进操作失败", exc_info=True)
                typer.secho(f"❌ 前进操作失败: {e}", fg=typer.colors.RED, err=True)
                ctx.exit(1)
