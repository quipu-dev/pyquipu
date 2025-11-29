from pathlib import Path
from typing import Annotated, Optional

import typer

from .helpers import engine_context
from ..config import DEFAULT_WORK_DIR
from ..ui_utils import prompt_for_confirmation


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
        """
        捕获当前工作区的状态，创建一个“微提交”快照。
        """
        with engine_context(work_dir) as engine:
            current_tree_hash = engine.git_db.get_tree_hash()
            is_node_clean = (engine.current_node is not None) and (engine.current_node.output_tree == current_tree_hash)
            EMPTY_TREE_HASH = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
            is_genesis_clean = (not engine.history_graph) and (current_tree_hash == EMPTY_TREE_HASH)

            if is_node_clean or is_genesis_clean:
                typer.secho("✅ 工作区状态未发生变化，无需创建快照。", fg=typer.colors.GREEN, err=True)
                ctx.exit(0)

            try:
                node = engine.capture_drift(current_tree_hash, message=message)
                msg_suffix = f" ({message})" if message else ""
                typer.secho(f"📸 快照已保存: {node.short_hash}{msg_suffix}", fg=typer.colors.GREEN, err=True)
            except Exception as e:
                typer.secho(f"❌ 创建快照失败: {e}", fg=typer.colors.RED, err=True)
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
        """
        丢弃工作区所有未记录的变更，恢复到上一个干净状态。
        """
        with engine_context(work_dir) as engine:
            graph = engine.history_graph
            if not graph:
                typer.secho("❌ 错误: 找不到任何历史记录，无法确定要恢复到哪个状态。", fg=typer.colors.RED, err=True)
                ctx.exit(1)

            target_tree_hash = engine._read_head()
            if not target_tree_hash or target_tree_hash not in graph:
                latest_node = max(graph.values(), key=lambda n: n.timestamp)
                target_tree_hash = latest_node.output_tree
                typer.secho(
                    f"⚠️  HEAD 指针丢失或无效，将恢复到最新历史节点: {latest_node.short_hash}",
                    fg=typer.colors.YELLOW,
                    err=True,
                )
            else:
                latest_node = graph[target_tree_hash]

            current_hash = engine.git_db.get_tree_hash()
            if current_hash == target_tree_hash:
                typer.secho(
                    f"✅ 工作区已经是干净状态 ({latest_node.short_hash})，无需操作。", fg=typer.colors.GREEN, err=True
                )
                ctx.exit(0)

            diff_stat = engine.git_db.get_diff_stat(target_tree_hash, current_hash)
            typer.secho("\n以下是即将被丢弃的变更:", fg=typer.colors.YELLOW, err=True)
            typer.secho("-" * 20, err=True)
            typer.echo(diff_stat, err=True)
            typer.secho("-" * 20, err=True)

            if not force:
                prompt = f"🚨 即将丢弃上述所有变更，并恢复到状态 {latest_node.short_hash}。\n此操作不可逆。是否继续？"
                if not prompt_for_confirmation(prompt, default=False):
                    typer.secho("\n🚫 操作已取消。", fg=typer.colors.YELLOW, err=True)
                    raise typer.Abort()

            try:
                engine.visit(target_tree_hash)
                typer.secho(f"✅ 工作区已成功恢复到节点 {latest_node.short_hash}。", fg=typer.colors.GREEN, err=True)
            except Exception as e:
                typer.secho(f"❌ 恢复状态失败: {e}", fg=typer.colors.RED, err=True)
                ctx.exit(1)
