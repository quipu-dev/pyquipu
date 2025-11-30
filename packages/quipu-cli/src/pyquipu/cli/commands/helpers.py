import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Generator, Optional

import typer
from pyquipu.interfaces.models import QuipuNode
from pyquipu.engine.state_machine import Engine

from ..factory import create_engine
from ..logger_config import setup_logging
from pyquipu.common.messaging import bus


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

    bus.warning("navigation.warning.workspaceDirty")
    bus.info("navigation.info.saveHint")
    return None


def _execute_visit(ctx: typer.Context, engine: Engine, target_hash: str, msg_id: str, **kwargs):
    """辅助函数：执行 engine.visit 并处理结果"""
    bus.info(msg_id, **kwargs)
    try:
        engine.visit(target_hash)
        bus.success("navigation.success.visit", short_hash=target_hash[:7])
    except Exception as e:
        logger.error(f"导航操作失败 (目标哈希: {target_hash[:12]})", exc_info=True)
        bus.error("navigation.error.generic", error=str(e))
        ctx.exit(1)
