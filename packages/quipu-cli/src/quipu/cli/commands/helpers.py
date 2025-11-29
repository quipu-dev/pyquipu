import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Generator, Optional

import typer
from quipu.interfaces.models import QuipuNode
from quipu.engine.state_machine import Engine

from ..factory import create_engine
from ..logger_config import setup_logging


@contextmanager
def engine_context(work_dir: Path) -> Generator[Engine, None, None]:
    """Context manager to set up logging, create, and automatically close a Quipu engine."""
    setup_logging()
    engine = None
    try:
        engine = create_engine(work_dir)
        yield engine
    finally:
        if engine:
            engine.close()


def _find_current_node(engine: Engine, graph: Dict[str, QuipuNode]) -> Optional[QuipuNode]:
    """在图中查找与当前工作区状态匹配的节点"""
    current_hash = engine.git_db.get_tree_hash()
    # 修复：直接从 graph 中通过 output_tree hash 查找
    for node in graph.values():
        if node.output_tree == current_hash:
            return node

    typer.secho("⚠️  当前工作区状态未在历史中找到，或存在未保存的变更。", fg=typer.colors.YELLOW, err=True)
    typer.secho("💡  请先运行 'quipu save' 创建一个快照，再进行导航。", fg=typer.colors.YELLOW, err=True)
    return None


def _execute_visit(ctx: typer.Context, engine: Engine, target_hash: str, description: str):
    """辅助函数：执行 engine.visit 并处理结果"""
    typer.secho(f"🚀 {description}", err=True)
    try:
        engine.visit(target_hash)
        typer.secho(f"✅ 已成功切换到状态 {target_hash[:7]}。", fg=typer.colors.GREEN, err=True)
    except Exception as e:
        logger.error(f"导航操作失败 (目标哈希: {target_hash[:12]})", exc_info=True)
        typer.secho(f"❌ 导航操作失败: {e}", fg=typer.colors.RED, err=True)
        ctx.exit(1)
